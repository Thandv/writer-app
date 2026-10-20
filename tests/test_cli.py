"""CLI subprocess tests — exercise every `writer` subcommand end-to-end
without invoking any LLM.

Each test runs `python -m writer_app.cli ...` as a subprocess so we exercise
the same argparse + entry-point path users hit.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"


def _writer(*args, cwd=None, env=None, input_text=None, timeout=30):
    """Run `python -m writer_app.cli <args>` and return (returncode, stdout, stderr)."""
    full_env = {"PYTHONPATH": str(SRC)}
    if env:
        full_env.update(env)
    # Need PATH so subprocess can find python (passthrough current PATH)
    import os
    full_env["PATH"] = os.environ.get("PATH", "")

    r = subprocess.run(
        [sys.executable, "-m", "writer_app.cli", *args],
        cwd=cwd, env=full_env, capture_output=True, text=True,
        input=input_text, timeout=timeout,
    )
    return r.returncode, r.stdout, r.stderr


# ── --help paths ──────────────────────────────────────────────────────────

def test_top_level_help():
    rc, out, _ = _writer("--help")
    assert rc == 0
    assert "writer" in out
    # All subcommands should be listed
    for cmd in ("init", "corpus", "start", "status", "config",
                "export", "disclosure", "providers", "humanize", "ui"):
        assert cmd in out


@pytest.mark.parametrize("sub", [
    "init", "corpus", "start", "status", "config",
    "export", "disclosure", "providers", "humanize", "ui",
])
def test_subcommand_help(sub):
    rc, out, err = _writer(sub, "--help")
    assert rc == 0, f"{sub} --help failed: {err}"
    assert sub in out.lower() or "usage" in out.lower()


# ── init ──────────────────────────────────────────────────────────────────

def test_init_creates_project(tmp_path):
    out_dir = tmp_path / "myseries"
    rc, out, err = _writer(
        "init", "My Series",
        "--out", str(out_dir),
        "--chapters", "5",
        "--words", "1500",
        "--threshold", "6.5",
        "--author", "Real Name",
        "--pen-name", "Pen Name",
    )
    assert rc == 0, err
    assert out_dir.exists()
    assert (out_dir / "STATE.json").exists()
    assert (out_dir / "bible").exists()
    # STATE.json contents
    state = json.loads((out_dir / "STATE.json").read_text())
    assert state["title"] == "My Series"
    assert state["target_chapters_per_book"] == 5
    assert state["target_words_per_chapter"] == 1500
    assert state["min_chapter_score"] == 6.5
    assert state["author_name"] == "Real Name"
    assert state["author_pen_name"] == "Pen Name"


def test_init_writes_bible_readme(tmp_path):
    out_dir = tmp_path / "x"
    rc, _, _ = _writer("init", "X", "--out", str(out_dir))
    assert rc == 0
    readme = out_dir / "bible" / "README.md"
    assert readme.exists()
    assert "bible" in readme.read_text().lower()


def test_init_refuses_to_overwrite_existing(tmp_path):
    out_dir = tmp_path / "x"
    _writer("init", "X", "--out", str(out_dir))
    rc, out, err = _writer("init", "X again", "--out", str(out_dir))
    assert rc == 0   # exits cleanly with a message, not an error
    assert "already exists" in out or "already exists" in err


# ── status ────────────────────────────────────────────────────────────────

def test_status_on_fresh_project(tmp_path):
    out_dir = tmp_path / "s"
    _writer("init", "S", "--out", str(out_dir))
    rc, out, err = _writer("status", str(out_dir))
    assert rc == 0
    assert "S" in out
    # Stage should be init for a fresh project
    assert "init" in out


def test_status_missing_project_exits_nonzero(tmp_path):
    rc, _, _ = _writer("status", str(tmp_path / "nowhere"))
    assert rc != 0


# ── config ────────────────────────────────────────────────────────────────

def test_config_shows_current_when_no_flags(tmp_path):
    out_dir = tmp_path / "c"
    _writer("init", "C", "--out", str(out_dir), "--chapters", "5")
    rc, out, _ = _writer("config", str(out_dir))
    assert rc == 0
    # Output is JSON
    data = json.loads(out)
    assert data["title"] == "C"
    assert data["chapters_per_book"] == 5


def test_config_updates_values(tmp_path):
    out_dir = tmp_path / "c"
    _writer("init", "C", "--out", str(out_dir))
    rc, out, err = _writer("config", str(out_dir),
                            "--chapters", "20",
                            "--threshold", "8.0",
                            "--author", "New Name")
    assert rc == 0, err
    # Verify persisted
    state = json.loads((out_dir / "STATE.json").read_text())
    assert state["target_chapters_per_book"] == 20
    assert state["min_chapter_score"] == 8.0
    assert state["author_name"] == "New Name"


def test_config_humanize_off(tmp_path):
    out_dir = tmp_path / "c"
    _writer("init", "C", "--out", str(out_dir))
    rc, _, err = _writer("config", str(out_dir), "--humanize", "n")
    assert rc == 0, err
    state = json.loads((out_dir / "STATE.json").read_text())
    assert state["humanize"] is False


# ── disclosure ────────────────────────────────────────────────────────────

def test_disclosure_creates_file_and_prints(tmp_path):
    out_dir = tmp_path / "d"
    _writer("init", "D", "--out", str(out_dir))
    rc, out, err = _writer("disclosure", str(out_dir))
    assert rc == 0, err
    assert (out_dir / "KDP_DISCLOSURE.md").exists()
    # Stdout includes the disclosure text
    assert "AI-generated" in out or "AI-Generated" in out or "yes" in out.lower()


# ── providers ─────────────────────────────────────────────────────────────

@pytest.fixture
def providers_cli(monkeypatch, capsys):
    """Run `writer providers` in-process with Ollama's model list and the
    internet probe stubbed, so the result doesn't depend on a live daemon."""
    from writer_app import cli
    from writer_app.shared import llm as llm_mod
    from writer_app.shared import remote as remote_mod
    monkeypatch.setattr(llm_mod, "_available_models",
                        lambda: {"mistral-nemo:12b", "qwen2.5:7b"})
    monkeypatch.setattr(remote_mod, "internet_available", lambda: True)
    for var in ("WRITER_DRAFT_PROVIDER", "WRITER_JUDGE_PROVIDER",
                "GROQ_API_KEY", "CEREBRAS_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sys, "argv", ["writer", "providers"])

    def run(env=None):
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)
        try:
            cli.main()
            rc = 0
        except SystemExit as e:
            rc = e.code
        captured = capsys.readouterr()
        return rc, captured.out, captured.err
    return run


def test_providers_no_env_shows_local_for_both(providers_cli):
    rc, out, err = providers_cli()
    assert rc == 0, err
    # Should mention both roles and say "local" for each
    assert "draft" in out
    assert "judge" in out
    assert "local" in out


def test_providers_reports_remote_when_env_set(providers_cli):
    rc, out, err = providers_cli(env={"WRITER_DRAFT_PROVIDER": "groq",
                                      "GROQ_API_KEY": "gsk_fake"})
    assert rc == 0, err
    assert "groq" in out.lower()
    assert "llama" in out.lower()  # default model name


# ── corpus ────────────────────────────────────────────────────────────────

def test_corpus_list_with_dev_corpus_present():
    """If the repo's corpus/ has style_cards, `writer corpus --list` shows them."""
    rc, out, err = _writer("corpus", "--list")
    # Should not crash regardless of corpus state
    assert rc == 0, err
    # Either reports listings or 'not built yet' — both acceptable
    assert "style_cards" in out or "not built yet" in out or len(out.strip()) > 0


def test_corpus_build_no_gutenberg_writes_style_cards(tmp_path):
    """Build only the style/craft cards (no network)."""
    rc, out, err = _writer("corpus", "--no-gutenberg",
                            env={"WRITER_CORPUS_DIR": str(tmp_path)})
    assert rc == 0, err
    assert (tmp_path / "style_cards").exists()
    assert (tmp_path / "craft").exists()
    assert len(list((tmp_path / "style_cards").iterdir())) > 0
    assert len(list((tmp_path / "craft").iterdir())) > 0


# ── export — needs a project with chapters ───────────────────────────────

def test_export_requires_chapters(tmp_path):
    """Export on a fresh project with no chapters exits cleanly with a notice."""
    out_dir = tmp_path / "e"
    _writer("init", "E", "--out", str(out_dir))
    rc, out, err = _writer("export", str(out_dir))
    # Exits non-zero because there are no books to export
    assert rc != 0
    # Helpful message
    assert "No books" in out or "No books" in err


def test_export_path_lookup_works_by_slug(tmp_path, monkeypatch):
    """`writer status <slug>` should resolve via ~/books/<slug>/ — verify
    the path resolver handles non-existent slugs cleanly."""
    rc, _, _ = _writer("status", "nonexistent-slug-12345")
    assert rc != 0   # not found


# ── humanize — needs an Ollama mock to be useful here ────────────────────

def test_humanize_requires_existing_project(tmp_path):
    """Running humanize against a missing project exits non-zero."""
    rc, _, _ = _writer("humanize", str(tmp_path / "no-such"), "/tmp/x.md")
    assert rc != 0


def test_humanize_missing_chapter_file(tmp_path):
    out_dir = tmp_path / "h"
    _writer("init", "H", "--out", str(out_dir))
    rc, _, _ = _writer("humanize", str(out_dir), str(tmp_path / "missing.md"))
    assert rc != 0
