"""
LLM router for the writer pipeline.

Two model ROLES:
  draft  — generates prose (Drafter, Reviser, Humanizer rewrite)
  judge  — scores prose, outlines, JSON returns

For each role the router decides per-call:
  1. If a remote provider is configured AND has an API key AND the internet
     is reachable AND the circuit breaker is closed AND --local-only was
     not set → use the remote provider.
  2. Otherwise → use local Ollama with the configured local model.

Any remote failure falls back to local automatically.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from . import remote as _remote
from .remote import RemoteUnavailable

OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
CHAT_URL    = f"{OLLAMA_BASE}/api/chat"
TAGS_URL    = f"{OLLAMA_BASE}/api/tags"

DRAFT_MODEL = os.environ.get("WRITER_DRAFT_MODEL", "mistral-nemo:12b")
JUDGE_MODEL = os.environ.get("WRITER_JUDGE_MODEL", "qwen2.5:7b")
FALLBACK    = "qwen2.5:7b"


class OllamaUnreachableError(RuntimeError):
    """The local Ollama daemon cannot be reached. Callers at the CLI/UI edge
    report it and stop; library code lets it propagate."""

    def __init__(self, detail: str):
        super().__init__(
            f"Cannot reach Ollama at {OLLAMA_BASE}. "
            f"Run `brew services start ollama`. ({detail})"
        )


def _available_models() -> set:
    try:
        with urllib.request.urlopen(TAGS_URL, timeout=5) as r:
            data = json.loads(r.read())
        return {m["name"] for m in data.get("models", [])}
    except Exception:
        return set()


def resolve_models() -> tuple[str, str]:
    """Resolve configured local models against what's actually pulled in Ollama."""
    available = _available_models()
    if not available:
        return DRAFT_MODEL, JUDGE_MODEL

    def pick(preferred: str, fallback: str) -> str:
        if preferred in available:
            return preferred
        for name in available:
            if name.split(":")[0] == preferred.split(":")[0]:
                return name
        return fallback if fallback in available else next(iter(available))

    return pick(DRAFT_MODEL, FALLBACK), pick(JUDGE_MODEL, FALLBACK)


def chat(messages: list, model: str, tools: list = None,
         temperature: float = 0.7, num_ctx: int = 8192,
         timeout: int = 600) -> dict:
    """Local Ollama chat call. Returns the raw message dict."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "tools": tools or [],
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }).encode()
    req = urllib.request.Request(
        CHAT_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())["message"]
    except urllib.error.URLError as e:
        raise OllamaUnreachableError(str(e.reason)) from e


def _extract_tool_calls(content: str) -> Optional[list]:
    if not content:
        return None
    calls, depth, start = [], 0, None
    for i, ch in enumerate(content):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(content[start : i + 1])
                    if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                        calls.append({
                            "function": {"name": obj["name"], "arguments": obj["arguments"]}
                        })
                except json.JSONDecodeError:
                    pass
                start = None
    return calls or None


def run_agent(system: str, user: str, *, model: str,
              tools: list = None, handlers: dict = None,
              temperature: float = 0.7, num_ctx: int = 8192,
              on_tool_call=None, max_rounds: int = 12) -> str:
    """Generic agent loop with optional tools. Local Ollama only — tool-using
    agents stay local for simpler error handling."""
    tools = tools or []
    handlers = handlers or {}

    messages = [
        {"role": "system",  "content": system},
        {"role": "user",    "content": user},
    ]

    for _ in range(max_rounds):
        msg = chat(messages, model=model, tools=tools,
                   temperature=temperature, num_ctx=num_ctx)
        messages.append(msg)

        tool_calls = msg.get("tool_calls") or _extract_tool_calls(msg.get("content", ""))
        if not tool_calls:
            return (msg.get("content") or "").strip()

        for call in tool_calls:
            name = call["function"]["name"]
            raw  = call["function"].get("arguments", {})
            args = json.loads(raw) if isinstance(raw, str) else raw
            if on_tool_call:
                on_tool_call(name, args)
            handler = handlers.get(name)
            result  = handler(**args) if handler else f"Unknown tool: {name}"
            messages.append({"role": "tool", "content": result})

    return (messages[-1].get("content") or "").strip()


def _try_remote_chat(role: str, messages: list, *,
                     temperature: float, max_tokens: int = 4096,
                     json_response: bool = False) -> Optional[str]:
    """Attempt a remote call for `role`. Returns None if remote isn't configured
    or unavailable — caller should then call Ollama."""
    if _remote.force_local():
        return None
    cfg = _remote.resolve_role(role)
    if cfg is None:
        return None
    try:
        return _remote.chat(
            messages, provider_cfg=cfg,
            temperature=temperature, max_tokens=max_tokens,
            json_response=json_response,
        )
    except RemoteUnavailable as e:
        print(f"  [LLM] Remote {cfg['provider']} ({role}): {e}; falling back to local.")
        return None


def generate(system: str, user: str, *, model: str,
             role: Optional[str] = None,
             temperature: float = 0.7, num_ctx: int = 8192,
             max_tokens: int = 4096) -> str:
    """Single-turn generation. If `role` is set and a remote provider is
    configured, route there first; otherwise use Ollama with `model`."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    remote_text = _try_remote_chat(
        role, messages, temperature=temperature, max_tokens=max_tokens,
    ) if role else None
    if remote_text is not None:
        return remote_text.strip()
    msg = chat(messages, model=model, temperature=temperature, num_ctx=num_ctx)
    return (msg.get("content") or "").strip()


def generate_json(system: str, user: str, *, model: str,
                  role: Optional[str] = None,
                  temperature: float = 0.3, num_ctx: int = 8192,
                  retries: int = 2, max_tokens: int = 2048) -> dict:
    """Single-turn generation expecting a JSON object. Retries on parse failure."""
    sys_prompt = system + (
        "\n\nRespond ONLY with a valid JSON object. No prose, no markdown fences."
    )
    last_err = ""
    for attempt in range(retries + 1):
        text = None
        if role:
            text = _try_remote_chat(
                role,
                [{"role": "system", "content": sys_prompt},
                 {"role": "user",   "content": user}],
                temperature=temperature, max_tokens=max_tokens, json_response=True,
            )
        if text is None:
            text = generate(sys_prompt, user, model=model, role=None,
                            temperature=temperature, num_ctx=num_ctx,
                            max_tokens=max_tokens)
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        start = text.find("{")
        end   = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            blob = text[start : end + 1]
            try:
                return json.loads(blob)
            except json.JSONDecodeError as e:
                last_err = str(e)
        else:
            last_err = "no JSON object found"
    raise ValueError(f"Model did not return valid JSON after {retries+1} tries: {last_err}")
