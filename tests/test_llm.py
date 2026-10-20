"""Tests for the LLM router — no Ollama required.

The Ollama HTTP call is mocked. We verify:
  - generate() flows through to chat() and returns content
  - generate_json() retries on bad JSON and parses code-fenced JSON
  - role-based routing prefers remote when configured, falls back to local
  - _try_remote_chat returns None when force_local is set
"""

import json
import urllib.error
from unittest.mock import patch, MagicMock
import pytest

from writer_app.shared import llm as llm_mod
from writer_app.shared import remote as remote_mod


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    remote_mod.reset_circuit_breaker()
    remote_mod.set_force_local(False)
    for v in ("WRITER_DRAFT_PROVIDER", "WRITER_JUDGE_PROVIDER",
              "GROQ_API_KEY", "CEREBRAS_API_KEY"):
        monkeypatch.delenv(v, raising=False)


# ── _try_remote_chat ──────────────────────────────────────────────────────

def test_try_remote_chat_returns_none_with_no_role():
    """If no role is passed, never attempt remote."""
    result = llm_mod._try_remote_chat(None, [{"role": "user", "content": "hi"}],
                                       temperature=0.5)
    assert result is None


def test_try_remote_chat_returns_none_when_remote_not_configured():
    result = llm_mod._try_remote_chat("draft", [{"role": "user", "content": "hi"}],
                                       temperature=0.5)
    assert result is None


def test_try_remote_chat_force_local_short_circuits(monkeypatch):
    """Even with full remote config, force_local=True returns None."""
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    remote_mod.set_force_local(True)
    result = llm_mod._try_remote_chat("draft", [{"role": "user", "content": "hi"}],
                                       temperature=0.5)
    assert result is None


def test_try_remote_chat_invokes_remote_when_configured(monkeypatch):
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "x")

    def fake_chat(messages, provider_cfg, temperature, max_tokens, json_response):
        return "REMOTE-RESPONSE"

    monkeypatch.setattr(remote_mod, "chat", fake_chat)
    result = llm_mod._try_remote_chat("draft", [{"role": "user", "content": "hi"}],
                                       temperature=0.5)
    assert result == "REMOTE-RESPONSE"


def test_try_remote_chat_falls_through_on_remote_failure(monkeypatch):
    """If remote raises RemoteUnavailable, _try_remote_chat returns None
    (the caller then falls back to local)."""
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "x")

    def boom(*a, **kw):
        raise remote_mod.RemoteUnavailable("test failure")

    monkeypatch.setattr(remote_mod, "chat", boom)
    result = llm_mod._try_remote_chat("draft", [{"role": "user", "content": "hi"}],
                                       temperature=0.5)
    assert result is None


# ── generate() with mocked Ollama ─────────────────────────────────────────

def test_generate_returns_local_chat_content(monkeypatch):
    def fake_local(messages, model, temperature, num_ctx, **kw):
        # Only positional args used by generate() — accept anything
        return {"content": "  local body  "}

    monkeypatch.setattr(llm_mod, "chat", fake_local)
    out = llm_mod.generate("system prompt", "user prompt", model="m")
    assert out == "local body"   # stripped


def test_generate_prefers_remote_when_role_routes_remote(monkeypatch):
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(remote_mod, "chat", lambda *a, **k: "  REMOTE  ")

    def should_not_be_called(*a, **k):
        raise AssertionError("local should not be called when remote works")

    monkeypatch.setattr(llm_mod, "chat", should_not_be_called)
    out = llm_mod.generate("sys", "user", model="m", role="draft")
    assert out == "REMOTE"


def test_generate_falls_back_to_local_when_remote_fails(monkeypatch):
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "x")

    monkeypatch.setattr(remote_mod, "chat",
                        MagicMock(side_effect=remote_mod.RemoteUnavailable("net")))
    monkeypatch.setattr(llm_mod, "chat",
                        lambda *a, **k: {"content": "LOCAL FALLBACK"})

    out = llm_mod.generate("sys", "user", model="m", role="draft")
    assert out == "LOCAL FALLBACK"


# ── generate_json() — parsing & retries ───────────────────────────────────

def test_generate_json_parses_clean_json(monkeypatch):
    monkeypatch.setattr(llm_mod, "chat",
                        lambda *a, **k: {"content": '{"a": 1, "b": "two"}'})
    out = llm_mod.generate_json("sys", "user", model="m")
    assert out == {"a": 1, "b": "two"}


def test_generate_json_strips_code_fences(monkeypatch):
    monkeypatch.setattr(llm_mod, "chat",
        lambda *a, **k: {"content": '```json\n{"x": 42}\n```'})
    out = llm_mod.generate_json("sys", "user", model="m")
    assert out == {"x": 42}


def test_generate_json_strips_unlabelled_fence(monkeypatch):
    monkeypatch.setattr(llm_mod, "chat",
        lambda *a, **k: {"content": '```\n{"x": 42}\n```'})
    out = llm_mod.generate_json("sys", "user", model="m")
    assert out == {"x": 42}


def test_generate_json_extracts_object_from_surrounding_text(monkeypatch):
    monkeypatch.setattr(llm_mod, "chat",
        lambda *a, **k: {"content": 'Sure! Here is the result: {"k": "v"} Done.'})
    out = llm_mod.generate_json("sys", "user", model="m")
    assert out == {"k": "v"}


def test_generate_json_retries_on_bad_then_succeeds(monkeypatch):
    """First call returns garbage, second returns valid JSON → should succeed."""
    responses = iter([{"content": "not json at all"},
                       {"content": '{"ok": true}'}])
    monkeypatch.setattr(llm_mod, "chat",
                        lambda *a, **k: next(responses))
    out = llm_mod.generate_json("sys", "user", model="m", retries=2)
    assert out == {"ok": True}


def test_generate_json_raises_after_retries_exhausted(monkeypatch):
    monkeypatch.setattr(llm_mod, "chat",
                        lambda *a, **k: {"content": "definitely not json"})
    with pytest.raises(ValueError, match="did not return valid JSON"):
        llm_mod.generate_json("sys", "user", model="m", retries=1)


def test_generate_json_uses_remote_first(monkeypatch):
    monkeypatch.setenv("WRITER_JUDGE_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(remote_mod, "chat",
                        lambda *a, **k: '{"from": "remote"}')

    def fail(*a, **k):
        raise AssertionError("local chat should not run")

    monkeypatch.setattr(llm_mod, "chat", fail)
    out = llm_mod.generate_json("sys", "user", model="m", role="judge")
    assert out == {"from": "remote"}


# ── resolve_models() ──────────────────────────────────────────────────────

def test_resolve_models_raises_when_nothing_is_pulled(monkeypatch):
    """An empty model list means Ollama is up with nothing pulled: fail loudly
    with the pull hint instead of returning names that aren't installed."""
    monkeypatch.setattr(llm_mod, "_available_models", lambda: set())
    with pytest.raises(llm_mod.ModelUnavailableError, match="ollama pull"):
        llm_mod.resolve_models()


def test_resolve_models_picks_exact_match(monkeypatch):
    monkeypatch.setattr(llm_mod, "DRAFT_MODEL", "mistral-nemo:12b")
    monkeypatch.setattr(llm_mod, "JUDGE_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(llm_mod, "_available_models",
                        lambda: {"mistral-nemo:12b", "qwen2.5:7b"})
    draft, judge = llm_mod.resolve_models()
    assert draft == "mistral-nemo:12b"
    assert judge == "qwen2.5:7b"


def test_resolve_models_falls_back_to_same_family(monkeypatch):
    """If qwen2.5:7b is configured but only qwen2.5:14b is pulled, pick the family match."""
    monkeypatch.setattr(llm_mod, "DRAFT_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(llm_mod, "JUDGE_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(llm_mod, "_available_models",
                        lambda: {"qwen2.5:14b", "llama3:8b"})
    draft, judge = llm_mod.resolve_models()
    # Family match: "qwen2.5" → "qwen2.5:14b"
    assert draft == "qwen2.5:14b"
    assert judge == "qwen2.5:14b"


def test_resolve_models_falls_back_to_FALLBACK_when_nothing_matches(monkeypatch):
    monkeypatch.setattr(llm_mod, "DRAFT_MODEL", "nonexistent:99b")
    monkeypatch.setattr(llm_mod, "JUDGE_MODEL", "nonexistent:99b")
    monkeypatch.setattr(llm_mod, "FALLBACK", "qwen2.5:7b")
    monkeypatch.setattr(llm_mod, "_available_models", lambda: {"qwen2.5:7b"})
    draft, judge = llm_mod.resolve_models()
    assert draft == "qwen2.5:7b"
    assert judge == "qwen2.5:7b"


# ── _extract_tool_calls ───────────────────────────────────────────────────

def test_extract_tool_calls_finds_embedded_object():
    """Some local models emit tool calls inside content as JSON."""
    content = (
        'Sure, I will use the tool. '
        '{"name": "write_file", "arguments": {"path": "/tmp/x", "content": "y"}} '
        'That is the call.'
    )
    calls = llm_mod._extract_tool_calls(content)
    assert calls is not None
    assert calls[0]["function"]["name"] == "write_file"
    assert calls[0]["function"]["arguments"]["path"] == "/tmp/x"


def test_extract_tool_calls_returns_none_when_no_calls():
    assert llm_mod._extract_tool_calls("just prose, no calls") is None
    assert llm_mod._extract_tool_calls("") is None
    assert llm_mod._extract_tool_calls(None) is None


# ── Ollama unreachable ────────────────────────────────────────────────────

def test_chat_raises_typed_error_when_ollama_unreachable(monkeypatch):
    """A connection failure raises OllamaUnreachableError (not SystemExit)
    and the message carries the start hint."""
    def refuse(*a, **k):
        raise urllib.error.URLError("Connection refused")
    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", refuse)
    with pytest.raises(llm_mod.OllamaUnreachableError) as exc:
        llm_mod.chat([{"role": "user", "content": "hi"}], model="m")
    assert "brew services start ollama" in str(exc.value)
    assert "Connection refused" in str(exc.value)
