"""Ollama-down behaviour: library code raises OllamaUnreachableError, judge
and detector catches let it through, and the CLI edge turns it into exit 1
with the start hint. No network, no real Ollama, no files outside tmp_path."""

import sys
import urllib.error

import pytest

from writer_app import cli, continuity, critic_panel, humanizer, reader_panel
from writer_app.shared import corpus as corpus_mod
from writer_app.shared import llm as llm_mod
from writer_app.shared import remote as remote_mod
from writer_app.shared.llm import OllamaUnreachableError
from writer_app.shared.memory import BookProject

HINT = "brew services start ollama"


def _down(*a, **k):
    raise OllamaUnreachableError("Connection refused")


@pytest.fixture
def project(tmp_path):
    p = BookProject(title="Invented Test Saga", output_dir=tmp_path / "book",
                    target_chapters_per_book=1, target_words_per_chapter=100)
    p.judge_model = "stub-judge"
    p.save()
    (p.output_dir / "bible").mkdir()
    return p


def test_reader_panel_propagates_ollama_down(monkeypatch, project):
    monkeypatch.setattr(reader_panel, "generate_json", _down)
    with pytest.raises(OllamaUnreachableError):
        reader_panel.run(project, "An invented chapter.")


def test_critic_panel_propagates_ollama_down(monkeypatch, project):
    monkeypatch.setattr(critic_panel, "generate_json", _down)
    with pytest.raises(OllamaUnreachableError):
        critic_panel.run(project, "An invented chapter.", "beat")


def test_humanizer_llm_detector_propagates_ollama_down(monkeypatch):
    monkeypatch.setattr(humanizer, "generate_json", _down)
    with pytest.raises(OllamaUnreachableError):
        humanizer._llm_detect("An invented chapter.", "stub-judge")


def test_continuity_propagates_ollama_down(monkeypatch, project):
    ch_dir = project.chapter_dir(1, 1)
    ch_dir.mkdir(parents=True)
    (ch_dir / "final.md").write_text("An invented chapter.", encoding="utf-8")
    monkeypatch.setattr(continuity, "generate_json", _down)
    with pytest.raises(OllamaUnreachableError):
        continuity.run(project, 1)


def test_writer_start_exits_1_with_hint_when_ollama_down(
        monkeypatch, project, tmp_path, capsys):
    """`writer start` on a tmp project with Ollama down exits 1 and prints
    the start hint to stderr."""
    def refuse(*a, **k):
        raise urllib.error.URLError("Connection refused")
    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(remote_mod, "internet_available", lambda: False)
    monkeypatch.setattr(corpus_mod, "CORPUS_DIR", tmp_path / "corpus")
    for var in ("WRITER_DRAFT_PROVIDER", "WRITER_JUDGE_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sys, "argv", ["writer", "start", str(project.output_dir)])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert HINT in capsys.readouterr().err


def test_writer_start_exits_1_when_ollama_rejects_a_draft_call(
        monkeypatch, project, tmp_path, capsys):
    """An HTTP error from a running Ollama outside the judges (here: the
    Loremaster's first call) stops the run with exit 1 and the HTTP error."""
    def rejected(*a, **k):
        raise llm_mod.OllamaRequestError("Ollama returned HTTP 500 for model m: oom")
    monkeypatch.setattr(llm_mod, "_available_models", lambda: {"stub-model:1b"})
    monkeypatch.setattr(llm_mod, "chat", rejected)
    monkeypatch.setattr(remote_mod, "internet_available", lambda: False)
    monkeypatch.setattr(corpus_mod, "CORPUS_DIR", tmp_path / "corpus")
    for var in ("WRITER_DRAFT_PROVIDER", "WRITER_JUDGE_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sys, "argv", ["writer", "start", str(project.output_dir)])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert "writer: Ollama returned HTTP 500" in capsys.readouterr().err
