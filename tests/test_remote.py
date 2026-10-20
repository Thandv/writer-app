"""Tests for shared.remote — provider routing, circuit breaker, internet check."""

import json
import os
import socket
from unittest.mock import patch, MagicMock
import urllib.error
import pytest

from writer_app.shared import remote as remote_mod
from writer_app.shared.remote import (
    PROVIDERS, RemoteUnavailable,
    resolve_role, describe_routing, circuit_open,
    reset_circuit_breaker, set_force_local, force_local,
    internet_available, chat,
    CIRCUIT_OPEN_AT,
)


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Reset circuit breaker, force-local, and remove relevant env vars
    before every test so they don't leak between cases."""
    reset_circuit_breaker()
    set_force_local(False)
    for var in ("WRITER_DRAFT_PROVIDER", "WRITER_JUDGE_PROVIDER",
                "WRITER_DRAFT_REMOTE_MODEL", "WRITER_JUDGE_REMOTE_MODEL",
                "GROQ_API_KEY", "CEREBRAS_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    yield


# ── PROVIDERS table integrity ─────────────────────────────────────────────

def test_providers_table_has_groq_and_cerebras():
    assert "groq" in PROVIDERS
    assert "cerebras" in PROVIDERS


def test_each_provider_has_required_keys():
    for name, cfg in PROVIDERS.items():
        for required in ("base_url", "env_key", "tos_url", "privacy_url",
                         "default_models", "supports_response_format_json"):
            assert required in cfg, f"{name} missing {required}"
        assert "draft" in cfg["default_models"]
        assert "judge" in cfg["default_models"]


# ── resolve_role: env-driven decisions ────────────────────────────────────

def test_resolve_role_returns_none_with_no_env():
    assert resolve_role("draft") is None
    assert resolve_role("judge") is None


def test_resolve_role_returns_none_for_invalid_role():
    assert resolve_role("nonsense") is None


def test_resolve_role_returns_none_when_provider_is_local(monkeypatch):
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "local")
    assert resolve_role("draft") is None


def test_resolve_role_returns_none_when_provider_unknown(monkeypatch):
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "made-up")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    assert resolve_role("draft") is None


def test_resolve_role_returns_none_when_api_key_missing(monkeypatch):
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    # No GROQ_API_KEY set
    assert resolve_role("draft") is None


def test_resolve_role_with_groq_set(monkeypatch):
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_fake")
    cfg = resolve_role("draft")
    assert cfg is not None
    assert cfg["provider"] == "groq"
    assert cfg["api_key"] == "gsk_fake"
    assert cfg["model"].startswith("llama")
    assert cfg["base_url"] == PROVIDERS["groq"]["base_url"]


def test_resolve_role_with_cerebras_set(monkeypatch):
    monkeypatch.setenv("WRITER_JUDGE_PROVIDER", "cerebras")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk-fake")
    cfg = resolve_role("judge")
    assert cfg["provider"] == "cerebras"
    assert cfg["api_key"] == "csk-fake"


def test_resolve_role_honours_model_override(monkeypatch):
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("WRITER_DRAFT_REMOTE_MODEL", "llama-special-1")
    cfg = resolve_role("draft")
    assert cfg["model"] == "llama-special-1"


def test_resolve_role_returns_none_when_circuit_open(monkeypatch):
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    # Force circuit open
    for _ in range(CIRCUIT_OPEN_AT):
        remote_mod._record_failure("groq", "test")
    assert circuit_open("groq")
    assert resolve_role("draft") is None


# ── describe_routing ──────────────────────────────────────────────────────

def test_describe_routing_no_env_both_local():
    r = describe_routing()
    assert r["draft"]["provider"] == "local"
    assert r["judge"]["provider"] == "local"


def test_describe_routing_with_groq_draft(monkeypatch):
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    r = describe_routing()
    assert r["draft"]["provider"] == "groq"
    assert "model" in r["draft"]
    assert "tos_url" in r["draft"]


def test_describe_routing_reports_missing_key(monkeypatch):
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    # No key → falls back to local
    r = describe_routing()
    assert r["draft"]["provider"] == "local"
    assert r["draft"]["configured"] == "groq"
    assert r["draft"]["key_set"] is False


# ── Circuit breaker ───────────────────────────────────────────────────────

def test_circuit_starts_closed():
    assert circuit_open("groq") is False
    assert circuit_open("cerebras") is False


def test_circuit_opens_after_n_failures():
    for _ in range(CIRCUIT_OPEN_AT):
        remote_mod._record_failure("groq", "test")
    assert circuit_open("groq") is True


def test_circuit_resets_on_success():
    for _ in range(CIRCUIT_OPEN_AT - 1):
        remote_mod._record_failure("groq", "test")
    remote_mod._record_success("groq")
    # Counter reset → next failure shouldn't open immediately
    remote_mod._record_failure("groq", "test")
    assert circuit_open("groq") is False


def test_reset_circuit_breaker():
    for _ in range(CIRCUIT_OPEN_AT):
        remote_mod._record_failure("groq", "test")
    assert circuit_open("groq")
    reset_circuit_breaker()
    assert circuit_open("groq") is False


# ── force_local override ──────────────────────────────────────────────────

def test_force_local_default_off():
    assert force_local() is False


def test_force_local_set_and_clear():
    set_force_local(True)
    assert force_local() is True
    set_force_local(False)
    assert force_local() is False


# ── internet_available cache ──────────────────────────────────────────────

def test_internet_available_returns_bool(monkeypatch):
    """Don't care about result, just shape and that it doesn't crash."""
    # Clear the cache so we don't reuse a stale verdict
    monkeypatch.setattr(remote_mod, "_internet_cached", None)
    result = internet_available()
    assert isinstance(result, bool)


def test_internet_available_returns_false_when_dns_fails(monkeypatch):
    monkeypatch.setattr(remote_mod, "_internet_cached", None)

    def boom(name):
        raise socket.gaierror("nope")

    monkeypatch.setattr(socket, "gethostbyname", boom)
    assert internet_available() is False


def test_internet_available_caches_result(monkeypatch):
    """Two consecutive calls within the TTL should NOT hit DNS twice."""
    monkeypatch.setattr(remote_mod, "_internet_cached", None)
    calls = {"n": 0}

    def fake_resolve(name):
        calls["n"] += 1
        return "127.0.0.1"

    monkeypatch.setattr(socket, "gethostbyname", fake_resolve)
    internet_available()
    internet_available()
    assert calls["n"] == 1  # cached


# ── chat() failure paths ──────────────────────────────────────────────────

def test_chat_raises_when_circuit_open(monkeypatch):
    for _ in range(CIRCUIT_OPEN_AT):
        remote_mod._record_failure("groq", "test")
    cfg = {"provider": "groq", "base_url": "https://api.groq.com/openai/v1",
           "model": "x", "api_key": "k", "supports_response_format_json": True,
           "tos_url": "", "privacy_url": ""}
    with pytest.raises(RemoteUnavailable, match="circuit open"):
        chat([{"role": "user", "content": "hi"}], provider_cfg=cfg)


def test_chat_raises_when_offline(monkeypatch):
    """Simulate offline → chat fails fast without an HTTP request."""
    monkeypatch.setattr(remote_mod, "internet_available", lambda: False)
    cfg = {"provider": "groq", "base_url": "https://api.groq.com/openai/v1",
           "model": "x", "api_key": "k", "supports_response_format_json": True,
           "tos_url": "", "privacy_url": ""}
    with pytest.raises(RemoteUnavailable, match="no internet"):
        chat([{"role": "user", "content": "hi"}], provider_cfg=cfg)


# ── Remote → local fallback with local Ollama down ──────────────────────

def test_remote_failure_falls_back_to_local_then_raises_when_local_down(monkeypatch):
    """Remote failure falls through to local Ollama; if local is also down,
    OllamaUnreachableError propagates instead of the process exiting."""
    from writer_app.shared import llm as llm_mod

    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "dummy-key")
    remote_calls = []

    def remote_down(*a, **k):
        remote_calls.append(1)
        raise RemoteUnavailable("network: down")
    monkeypatch.setattr(remote_mod, "chat", remote_down)

    def local_down(*a, **k):
        raise urllib.error.URLError("Connection refused")
    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", local_down)

    with pytest.raises(llm_mod.OllamaUnreachableError):
        llm_mod.generate("sys", "user", model="m", role="draft")
    assert remote_calls == [1]
