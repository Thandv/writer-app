"""Smoke tests — no network, no Ollama required."""

import os
import sys
from pathlib import Path
import pytest


def test_imports_load():
    """Every module imports without error."""
    from writer_app.shared import llm, tools, memory, rubric, corpus, remote
    from writer_app import (
        loremaster, plotter, drafter, reader_panel, critic_panel,
        reviser, continuity, humanizer, provenance, export, orchestrator, cli,
    )
    assert hasattr(cli, "main")


def test_rubric_weighted_average():
    from writer_app.shared.rubric import CRITIC_RUBRIC, weighted_average
    scores = {k: 7 for k in CRITIC_RUBRIC}
    assert weighted_average(scores, CRITIC_RUBRIC) == 7.0


def test_humanizer_heuristic_ai_sample():
    """AI-flavoured prose should score noticeably higher than human prose."""
    from writer_app.humanizer import _heuristic_scan

    ai = ("As the sun rose, Lyra felt the weight of her destiny. "
          "She wasn't just a healer. She was a warrior. She was a queen. "
          "Meanwhile, the dark lord steeled himself. He could feel the tension "
          "thick in the air, a veritable tapestry of dread. Little did he know, "
          "his time was running out. As the bell tolled, she rose. "
          "She felt the cold. She saw the malice. She heard the betrayal. "
          "Her mind raced. Her heart pounded. Her spine tingled.")
    human = ("Lyra crossed the courtyard before anyone could stop her. The "
             "dagger banged against her hip with each step. Talen waited in "
             "the stairwell. He hadn't bothered to draw his own knife. "
             "\"You should have run,\" he said. She had not. She probably should have.")

    ai_score    = _heuristic_scan(ai)["ai_score"]
    human_score = _heuristic_scan(human)["ai_score"]
    assert ai_score > human_score
    assert ai_score >= 4.0   # AI sample lands meaningfully above clean prose
    assert human_score <= 3.0


def test_remote_resolver_no_env():
    """With no env vars set, both roles resolve to local (None)."""
    from writer_app.shared import remote
    for var in ("WRITER_DRAFT_PROVIDER", "WRITER_JUDGE_PROVIDER",
                "GROQ_API_KEY", "CEREBRAS_API_KEY"):
        os.environ.pop(var, None)
    assert remote.resolve_role("draft") is None
    assert remote.resolve_role("judge") is None


def test_remote_resolver_with_key(monkeypatch):
    """With env + key set, resolves to a remote config."""
    from writer_app.shared import remote
    remote.reset_circuit_breaker()
    monkeypatch.setenv("WRITER_DRAFT_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_dummy_key_for_test")
    cfg = remote.resolve_role("draft")
    assert cfg is not None
    assert cfg["provider"] == "groq"
    assert cfg["model"].startswith("llama")
    assert cfg["api_key"].startswith("gsk_")


def test_force_local_override():
    from writer_app.shared import remote
    from writer_app.shared import llm
    remote.set_force_local(True)
    try:
        result = llm._try_remote_chat(
            "draft", [{"role": "user", "content": "hi"}],
            temperature=0.5, max_tokens=10,
        )
        assert result is None
    finally:
        remote.set_force_local(False)


def test_book_project_round_trip(tmp_path):
    """BookProject saves and loads cleanly."""
    from writer_app.shared.memory import BookProject
    p = BookProject(
        title="Test",
        output_dir=tmp_path,
        target_chapters_per_book=5,
        author_name="Author",
        author_pen_name="Pen",
    )
    p.save()
    loaded = BookProject.load(tmp_path)
    assert loaded.title == "Test"
    assert loaded.target_chapters_per_book == 5
    assert loaded.author_name == "Author"
    assert loaded.author_pen_name == "Pen"


def test_plotter_outline_parser(tmp_path):
    """Chapter beat parser correctly extracts chapters from a markdown outline."""
    from writer_app.plotter import parse_chapters
    sample = """# Book 1: Test

## Chapter 1 — The Beginning
- **POV:** Iri
- **Goal:** Start something
- **Conflict:** Inertia
- **Outcome:** Yes-but
- **Beats:**
  1. Open
  2. Middle
  3. Close

## Chapter 2 — The Middle
- **POV:** Lev
- **Goal:** Continue
- **Conflict:** Self
- **Outcome:** No-and
- **Beats:**
  1. A
  2. B
"""
    p = tmp_path / "outline.md"
    p.write_text(sample, encoding="utf-8")
    chs = parse_chapters(p)
    assert len(chs) == 2
    assert chs[0]["number"] == 1
    assert chs[0]["title"] == "The Beginning"
    assert "POV:** Iri" in chs[0]["body"]


def test_export_docx_round_trip(tmp_path):
    """End-to-end DOCX export: creates a valid zip with the expected entries."""
    import zipfile
    from writer_app.shared.memory import BookProject, BookState, ChapterState
    from writer_app import export as export_mod

    project = BookProject(
        title="Test Series",
        output_dir=tmp_path,
        target_chapters_per_book=1,
        author_name="Real Name",
        author_pen_name="Pen Name",
    )
    book = BookState(number=1, title="Test Book", status="done")
    project.upsert_book(book)

    # Write a single chapter
    ch1_dir = project.chapter_dir(1, 1)
    ch1_dir.mkdir(parents=True, exist_ok=True)
    (ch1_dir / "final.md").write_text("First paragraph.\n\nSecond paragraph.", encoding="utf-8")

    book.upsert_chapter(ChapterState(number=1, title="The First", status="done",
                                     final_path=str(ch1_dir / "final.md")))
    project.upsert_book(book)
    project.save()

    paths = export_mod.export_book(project, 1, ["docx"])
    assert paths
    docx = paths[0]
    assert docx.exists()
    assert docx.suffix == ".docx"

    with zipfile.ZipFile(docx) as z:
        names = z.namelist()
        assert "[Content_Types].xml" in names
        assert "word/document.xml" in names
        doc = z.read("word/document.xml").decode()
        assert "Test Book" in doc
        assert "AI Disclosure" in doc
        assert "Pen Name" in doc
        assert "First paragraph" in doc


def test_export_epub_uncompressed_mimetype(tmp_path):
    """EPUB spec: the mimetype entry must be the first AND uncompressed."""
    import zipfile
    from writer_app.shared.memory import BookProject, BookState, ChapterState
    from writer_app import export as export_mod

    project = BookProject(title="T", output_dir=tmp_path)
    book = BookState(number=1, status="done")
    ch1_dir = project.chapter_dir(1, 1); ch1_dir.mkdir(parents=True, exist_ok=True)
    (ch1_dir / "final.md").write_text("body", encoding="utf-8")
    book.upsert_chapter(ChapterState(number=1, title="t", status="done"))
    project.upsert_book(book); project.save()

    [epub] = export_mod.export_book(project, 1, ["epub"])
    with zipfile.ZipFile(epub) as z:
        first = z.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED


def test_provenance_writes_audit_table(tmp_path):
    from writer_app.shared.memory import BookProject, BookState, ChapterState
    from writer_app import provenance as provenance_mod

    project = BookProject(title="T", output_dir=tmp_path,
                          author_name="A", author_pen_name="B",
                          draft_model="mistral-nemo:12b",
                          judge_model="qwen2.5:7b")
    book = BookState(number=1, status="done")
    book.upsert_chapter(ChapterState(
        number=1, title="One", status="done",
        score=8.0, iterations=2,
        drafted_at="2026-05-15T12:00:00",
        draft_model_used="mistral-nemo:12b",
        judge_model_used="qwen2.5:7b",
        humanizer_passes=1,
        ai_score_before=7.5, ai_score_after=3.2,
    ))
    project.upsert_book(book); project.save()

    path = provenance_mod.write_book_provenance(project, 1)
    text = path.read_text(encoding="utf-8")
    assert "mistral-nemo:12b" in text
    assert "Per-chapter audit" in text
    assert "7.5→3.2" in text or "7.5 → 3.2" in text
