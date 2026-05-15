"""
Remote provider abstraction for the writer pipeline.

When internet is available AND an API key is configured for a role
(`draft` or `judge`), LLM calls are routed to a free-tier remote provider.
When internet is down, the call fails fast and the caller falls back to
local Ollama.

Supported providers (both expose OpenAI-compatible /chat/completions):
  - Groq      api.groq.com       (Llama 3.3 70B, fast)
  - Cerebras  api.cerebras.ai    (Llama 3.3 70B, often faster)

Configuration is entirely via environment variables:

  WRITER_DRAFT_PROVIDER  groq | cerebras | local    (default: local)
  WRITER_JUDGE_PROVIDER  groq | cerebras | local    (default: local)
  GROQ_API_KEY           your Groq key
  CEREBRAS_API_KEY       your Cerebras key
  WRITER_DRAFT_REMOTE_MODEL  (optional override)
  WRITER_JUDGE_REMOTE_MODEL  (optional override)

A simple circuit breaker stops trying a provider after 3 consecutive
failures so we don't hammer a downed endpoint mid-run. The breaker resets
on the next `writer start`.
"""

import json
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Optional


class RemoteUnavailable(Exception):
    """Raised when a remote call cannot complete. Caller should fall back to local."""


PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "env_key":  "GROQ_API_KEY",
        "tos_url":  "https://wow.groq.com/terms-of-use/",
        "privacy_url": "https://wow.groq.com/privacy-policy/",
        "default_models": {
            "draft": "llama-3.3-70b-versatile",
            "judge": "llama-3.1-8b-instant",
        },
        "supports_response_format_json": True,
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "env_key":  "CEREBRAS_API_KEY",
        "tos_url":  "https://www.cerebras.ai/terms-of-service",
        "privacy_url": "https://www.cerebras.ai/privacy",
        "default_models": {
            "draft": "llama3.3-70b",
            "judge": "llama3.1-8b",
        },
        "supports_response_format_json": True,
    },
}


# ── Circuit breaker (process-local) ──────────────────────────────────────

_failures: dict[str, int] = {}
_circuit_open: dict[str, bool] = {}

CIRCUIT_OPEN_AT = 3
NETWORK_TIMEOUT = 15


def _record_success(provider: str):
    _failures[provider] = 0
    if _circuit_open.get(provider):
        _circuit_open[provider] = False
        print(f"  [remote] {provider}: recovered.")


def _record_failure(provider: str, reason: str):
    _failures[provider] = _failures.get(provider, 0) + 1
    if _failures[provider] >= CIRCUIT_OPEN_AT and not _circuit_open.get(provider):
        _circuit_open[provider] = True
        print(f"  [remote] {provider}: 3 consecutive failures — switching to "
              f"local-only for the rest of this run. Reason: {reason[:140]}")


def circuit_open(provider: str) -> bool:
    return bool(_circuit_open.get(provider, False))


def reset_circuit_breaker():
    _failures.clear()
    _circuit_open.clear()


# ── Provider resolution ──────────────────────────────────────────────────

def resolve_role(role: str) -> Optional[dict]:
    if role not in ("draft", "judge"):
        return None
    provider_name = os.environ.get(f"WRITER_{role.upper()}_PROVIDER", "local").strip().lower()
    if provider_name in ("", "local", "ollama", "none"):
        return None
    if provider_name not in PROVIDERS:
        print(f"  [remote] Unknown provider {provider_name!r} for {role} — using local.")
        return None
    cfg = PROVIDERS[provider_name]
    api_key = os.environ.get(cfg["env_key"], "").strip()
    if not api_key:
        print(f"  [remote] {cfg['env_key']} not set — {role} role will use local.")
        return None
    if circuit_open(provider_name):
        return None
    model = os.environ.get(
        f"WRITER_{role.upper()}_REMOTE_MODEL",
        cfg["default_models"][role],
    )
    return {
        "provider": provider_name,
        "model":    model,
        "api_key":  api_key,
        "base_url": cfg["base_url"],
        "supports_response_format_json": cfg["supports_response_format_json"],
        "tos_url":     cfg["tos_url"],
        "privacy_url": cfg["privacy_url"],
    }


def describe_routing() -> dict:
    out = {}
    for role in ("draft", "judge"):
        cfg = resolve_role(role)
        if cfg is None:
            provider = os.environ.get(f"WRITER_{role.upper()}_PROVIDER", "local").lower()
            api_env  = PROVIDERS.get(provider, {}).get("env_key", "")
            key_set  = bool(os.environ.get(api_env, "")) if api_env else False
            out[role] = {
                "provider":   "local",
                "configured": provider,
                "key_set":    key_set,
                "circuit":    "open" if circuit_open(provider) else "closed",
            }
        else:
            out[role] = {
                "provider":    cfg["provider"],
                "model":       cfg["model"],
                "circuit":     "open" if circuit_open(cfg["provider"]) else "closed",
                "tos_url":     cfg["tos_url"],
                "privacy_url": cfg["privacy_url"],
            }
    return out


# ── Internet pre-check ──────────────────────────────────────────────────

_internet_cached: Optional[tuple[bool, float]] = None
_INTERNET_CACHE_TTL = 30


def internet_available() -> bool:
    global _internet_cached
    now = time.time()
    if _internet_cached and now - _internet_cached[1] < _INTERNET_CACHE_TTL:
        return _internet_cached[0]
    try:
        socket.setdefaulttimeout(3)
        socket.gethostbyname("api.groq.com")
        ok = True
    except Exception:
        ok = False
    _internet_cached = (ok, now)
    return ok


# ── Chat completion ─────────────────────────────────────────────────────

def chat(messages: list, *, provider_cfg: dict,
         temperature: float = 0.7,
         max_tokens: int = 4096,
         json_response: bool = False) -> str:
    provider = provider_cfg["provider"]
    if circuit_open(provider):
        raise RemoteUnavailable(f"{provider}: circuit open")
    if not internet_available():
        raise RemoteUnavailable("no internet")

    url = f"{provider_cfg['base_url']}/chat/completions"
    body = {
        "model":       provider_cfg["model"],
        "messages":    messages,
        "temperature": temperature,
        "max_tokens":  max_tokens,
        "stream":      False,
    }
    if json_response and provider_cfg.get("supports_response_format_json"):
        body["response_format"] = {"type": "json_object"}

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {provider_cfg['api_key']}",
            "User-Agent":    "writer-app/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=NETWORK_TIMEOUT) as r:
            payload = json.loads(r.read())
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        reason = f"HTTP {e.code}: {err_body[:200]}"
        if e.code in (401, 403):
            _failures[provider] = CIRCUIT_OPEN_AT
            _record_failure(provider, reason)
        else:
            _record_failure(provider, reason)
        raise RemoteUnavailable(reason)
    except (urllib.error.URLError, socket.timeout, socket.gaierror, OSError) as e:
        reason = f"network: {e}"
        _record_failure(provider, reason)
        raise RemoteUnavailable(reason)

    _record_success(provider)
    try:
        return payload["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise RemoteUnavailable(f"malformed response: {e}; payload={str(payload)[:200]}")


# ── Force-local override (CLI --local-only) ─────────────────────────────

_force_local = False


def set_force_local(value: bool):
    global _force_local
    _force_local = bool(value)


def force_local() -> bool:
    return _force_local
