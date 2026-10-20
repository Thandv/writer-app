"""Deterministic local model resolution (shared.llm.resolve_models) and how
the CLI reports it. Ollama is never contacted: _available_models or urlopen
is stubbed in every test."""

import os
import subprocess
import sys
import textwrap
import urllib.error
from pathlib import Path

import pytest

from writer_app import cli
from writer_app.shared import corpus as corpus_mod
from writer_app.shared import llm as llm_mod
from writer_app.shared import remote as remote_mod
from writer_app.shared.memory import BookProject

SRC = Path(__file__).resolve().parent.parent / "src"
INSTALLED = {"qwen3-embedding:0.6b", "lfm2.5:8b-a1b", "qwen3.5:9b"}
ONLY_UNUSABLE = {"qwen3-embedding:0.6b", "nomic-embed-text:latest", "qwen2.5vl:3b"}


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(llm_mod, "DRAFT_MODEL", "mistral-nemo:12b")
    monkeypatch.setattr(llm_mod, "JUDGE_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(llm_mod, "FALLBACK", "qwen2.5:7b")
    monkeypatch.setattr(remote_mod, "internet_available", lambda: False)
    for var in ("WRITER_DRAFT_PROVIDER", "WRITER_JUDGE_PROVIDER"):
        monkeypatch.delenv(var, raising=False)


def _installed(monkeypatch, names):
    monkeypatch.setattr(llm_mod, "_available_models", lambda: set(names))


# ── resolve_models ────────────────────────────────────────────────────────

def test_same_choice_in_20_processes_with_different_hash_seeds():
    script = textwrap.dedent(f"""
        from writer_app.shared import llm
        llm._available_models = lambda: set({sorted(INSTALLED)!r})
        print(llm.resolve_models())
    """)
    env = {k: v for k, v in os.environ.items()
           if k not in ("WRITER_DRAFT_MODEL", "WRITER_JUDGE_MODEL")}
    env["PYTHONPATH"] = str(SRC)
    results = set()
    for seed in range(20):
        env["PYTHONHASHSEED"] = str(seed)
        out = subprocess.run([sys.executable, "-c", script], env=env,
                             capture_output=True, text=True, check=True)
        results.add(out.stdout.strip())
    assert results == {"('lfm2.5:8b-a1b', 'lfm2.5:8b-a1b')"}


def test_embedding_and_vision_models_never_chosen_even_when_sorted_first(monkeypatch):
    _installed(monkeypatch, {"aaa-embedding:1b", "aaavl:3b", "zeta-chat:7b"})
    assert llm_mod.resolve_models() == ("zeta-chat:7b", "zeta-chat:7b")


def test_pulled_preferred_model_beats_sorted_pick(monkeypatch):
    _installed(monkeypatch, INSTALLED | {"mistral-nemo:12b"})
    assert llm_mod.resolve_models() == ("mistral-nemo:12b", "lfm2.5:8b-a1b")


def test_exact_preferred_beats_same_family_model_that_sorts_first(monkeypatch):
    _installed(monkeypatch, {"qwen2.5:14b", "qwen2.5:7b"})
    assert llm_mod.resolve_models()[1] == "qwen2.5:7b"


def test_only_embedding_or_vision_models_raises_with_pull_hint(monkeypatch):
    _installed(monkeypatch, ONLY_UNUSABLE)
    with pytest.raises(llm_mod.ModelUnavailableError) as exc:
        llm_mod.resolve_models()
    msg = str(exc.value)
    assert "ollama pull mistral-nemo:12b" in msg
    assert "ollama pull qwen2.5:7b" in msg


def test_daemon_down_during_resolution_is_unreachable_not_unavailable(monkeypatch):
    def refuse(*a, **k):
        raise urllib.error.URLError("Connection refused")
    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", refuse)
    with pytest.raises(llm_mod.OllamaUnreachableError, match="brew services start ollama"):
        llm_mod.resolve_models()


# ── CLI ───────────────────────────────────────────────────────────────────

def _run_cli(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["writer", *argv])
    try:
        cli.main()
    except SystemExit as e:
        return e.code
    return 0


def test_writer_providers_exits_nonzero_with_pull_hint(monkeypatch, capsys):
    _installed(monkeypatch, ONLY_UNUSABLE)
    assert _run_cli(monkeypatch, "providers") == 1
    assert "ollama pull" in capsys.readouterr().err


def test_writer_providers_exits_nonzero_when_ollama_down(monkeypatch, capsys):
    def down():
        raise llm_mod.OllamaUnreachableError("Connection refused")
    monkeypatch.setattr(llm_mod, "_available_models", down)
    assert _run_cli(monkeypatch, "providers") == 1
    assert "brew services start ollama" in capsys.readouterr().err


def test_writer_providers_names_missing_default_when_sorted_pick_used(monkeypatch, capsys):
    _installed(monkeypatch, INSTALLED)
    assert _run_cli(monkeypatch, "providers") == 0
    out = capsys.readouterr().out
    assert "draft model: lfm2.5:8b-a1b" in out
    assert "ollama pull mistral-nemo:12b" in out
    assert "ollama pull qwen2.5:7b" in out


def test_writer_start_exits_1_with_pull_hint(monkeypatch, tmp_path, capsys):
    project = BookProject(title="Invented Test Saga", output_dir=tmp_path / "book")
    project.save()
    monkeypatch.setattr(corpus_mod, "CORPUS_DIR", tmp_path / "corpus")
    _installed(monkeypatch, ONLY_UNUSABLE)
    assert _run_cli(monkeypatch, "start", str(project.output_dir)) == 1
    assert "ollama pull" in capsys.readouterr().err
