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


class ModelUnavailableError(RuntimeError):
    """Ollama is up but no usable chat model is pulled."""

    def __init__(self, missing: list[str]):
        pulls = "  ".join(f"`ollama pull {m}`" for m in missing)
        super().__init__(
            f"No usable chat model is pulled in Ollama "
            f"(missing: {', '.join(missing)}). Run {pulls}."
        )


def _available_models() -> set[str]:
    """Names of the models pulled in Ollama. Raises OllamaUnreachableError
    when the daemon cannot be reached (an empty set means nothing is pulled)."""
    try:
        with urllib.request.urlopen(TAGS_URL, timeout=5) as r:
            data = json.loads(r.read())
    except OSError as e:  # URLError, refused connection, timeout
        raise OllamaUnreachableError(str(getattr(e, "reason", e))) from e
    return {m["name"] for m in data.get("models", [])}


def _is_chat_model(name: str) -> bool:
    """Embedding and vision models can't draft or judge prose. Decided by
    name only: 'embed' anywhere, or a base name ending in 'vl' (qwen2.5vl)."""
    base = name.split(":")[0].lower()
    return "embed" not in name.lower() and not base.endswith("vl")


def resolve_models() -> tuple[str, str]:
    """Resolve the configured local models against what's pulled in Ollama.

    Per role, in order: the preferred model; a pulled model of the same
    family; FALLBACK; otherwise the first usable model in sorted order, so
    every process makes the same choice. Raises ModelUnavailableError when
    no usable chat model is pulled."""
    usable = sorted(m for m in _available_models() if _is_chat_model(m))
    if not usable:
        raise ModelUnavailableError(sorted({DRAFT_MODEL, JUDGE_MODEL}))

    def pick(preferred: str, fallback: str) -> str:
        if preferred in usable:
            return preferred
        family = preferred.split(":")[0]
        for name in usable:
            if name.split(":")[0] == family:
                return name
        return fallback if fallback in usable else usable[0]

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
