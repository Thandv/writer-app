"""End-to-end orchestrator test with every agent mocked.

We don't invoke a real LLM. Instead, each agent's `run` function is
monkeypatched to a stub that writes the expected output files. This
verifies the orchestrator's control flow — stage ordering, resumability,
manuscript assembly, revision-loop logic — independently of model quality.
"""

import json
from pathlib import Path

import pytest

from writer_app.shared.memory import BookProject, BookState, ChapterState
from writer_app import (
    loremaster, plotter, drafter, reader_panel, critic_panel,
    reviser, continuity, humanizer, provenance,
)
from writer_app import orchestrator


# ── Stubs ─────────────────────────────────────────────────────────────────

def _stub_loremaster(project):
    """Write a minimal WORLD_BIBLE.md so the Plotter has something to read."""
    p = Path(project.output_dir) / "WORLD_BIBLE.md"
    p.write_text(
        "# WORLD_BIBLE\n\n## Premise & Tone\nA stubbed world for testing.\n"
        "## Major Characters\nIri, the protagonist.\n",
        encoding="utf-8",
    )
    project.world_bible_path = str(p)
    project.stage = "loremaster_done"
    project.save()
    return project


def _stub_plotter_book(project, book_n):
    """Write a BOOK_OUTLINE.md with exactly target_chapters_per_book entries
    in the format the parser expects."""
    book = project.book(book_n)
    book_dir = project.book_dir(book_n)
    book_dir.mkdir(parents=True, exist_ok=True)
    outline_path = book_dir / "BOOK_OUTLINE.md"

    n = project.target_chapters_per_book
    lines = [f"# Book {book_n}: Stub Book\n"]
    for i in range(1, n + 1):
        lines.append(f"\n## Chapter {i} — Stub chapter {i}")
        lines.append(f"- **POV:** Iri")
        lines.append(f"- **Goal:** stub goal {i}")
        lines.append(f"- **Conflict:** stub conflict {i}")
        lines.append(f"- **Outcome:** Yes-but — stub outcome")
        lines.append(f"- **Beats:**\n  1. Beat one\n  2. Beat two\n")
    outline_path.write_text("\n".join(lines), encoding="utf-8")

    book.outline_path = str(outline_path)
    book.title = "Stub Book"
    book.status = "writing"
    project.upsert_book(book)
    project.save()
    return project


def _stub_drafter(project, book_n, chapter_n, chapter_title, beat_body,
                  previous_chapter_text="", revision_note=""):
    """Return a deterministic stub chapter body that satisfies the strict
    success criterion (≥30 LOC equivalent in word count would be excessive
    here — just produce reasonable prose)."""
    rev_marker = "[REVISED]" if revision_note else ""
    return (
        f"This is the stub draft of chapter {chapter_n} {rev_marker}.\n\n"
        f"The POV character moves through {chapter_title.lower()}, "
        f"thinking about what {beat_body[:80] if beat_body else 'stub beat'} "
        f"means for the plot.\n\n"
        f"⁂\n\n"
        f"The chapter ends with a new question raised."
    )


def _stub_humanizer(project, text, **kw):
    """Return the text unchanged with a low ai_score so the loop doesn't iterate."""
    return {
        "text": text,
        "passes": 0,
        "ai_score_before":  2.0,
        "ai_score_after":   2.0,
        "llm_score_before": 2,
        "llm_score_after":  2,
        "tells_before": [],
        "tells_after":  [],
        "summaries":    [],
        "heuristic_hits_before": {},
        "heuristic_hits_after":  {},
    }


def _stub_reader_panel(project, chapter_text):
    """Return a high score so the chapter passes the threshold first try."""
    return {
        "reports": [
            {"persona_id": p, "persona_name": p, "scores": {},
             "weighted": 8.5, "would_keep_reading": True,
             "landed": "everything", "missed": "nothing", "verdict": "great"}
            for p in ("epic-fan", "grimdark-fan", "progression-fan", "casual-reader")
        ],
        "average_score": 8.5,
        "keep_reading_pct": 100,
    }


def _stub_critic_panel(project, chapter_text, beat_body):
    return {
        "reports": [
            {"persona_id": p, "persona_name": p, "scores": {},
             "weighted": 8.5, "strengths": [], "weaknesses": [],
             "line_notes": [], "directive": ""}
            for p in ("developmental-editor", "prose-critic", "structure-critic")
        ],
        "average_score": 8.5,
    }


def _stub_continuity(project, book_n):
    """No issues, grade 9/10."""
    report = {"issues": [], "overall_grade": 9, "summary": "clean"}
    report_path = project.book_dir(book_n) / "CONTINUITY_REPORT.md"
    report_path.write_text("# Continuity Report\n\nClean.\n", encoding="utf-8")
    return report


# ── Fixture: install all stubs ────────────────────────────────────────────

@pytest.fixture
def mocked_pipeline(monkeypatch):
    monkeypatch.setattr(loremaster,   "run",      _stub_loremaster)
    monkeypatch.setattr(plotter,      "run_book", _stub_plotter_book)
    monkeypatch.setattr(drafter,      "run",      _stub_drafter)
    monkeypatch.setattr(reviser,      "revise",   _stub_drafter)
    monkeypatch.setattr(humanizer,    "run",      _stub_humanizer)
    monkeypatch.setattr(reader_panel, "run",      _stub_reader_panel)
    monkeypatch.setattr(critic_panel, "run",      _stub_critic_panel)
    monkeypatch.setattr(continuity,   "run",      _stub_continuity)
    # Don't run a real series-plotter call; we test single-book only here
    monkeypatch.setattr(plotter, "run_series",
                        lambda project: project)
    # Skip the model resolver — return canned model names
    from writer_app.shared import llm
    monkeypatch.setattr(llm, "resolve_models",
                        lambda: ("stub-draft", "stub-judge"))


# ── Tests ─────────────────────────────────────────────────────────────────

def test_full_pipeline_produces_manuscript(tmp_path, mocked_pipeline):
    """Single book with 2 chapters runs the whole pipeline to completion."""
    project = BookProject(
        title="Stub Series",
        output_dir=tmp_path,
        target_chapters_per_book=2,
        target_words_per_chapter=200,
        target_books_in_series=1,
        min_chapter_score=7.0,        # below stub's 8.5 → passes first try
        max_revisions_per_chapter=2,
    )
    project.save()

    orchestrator.run(project)

    # World bible written
    assert (tmp_path / "WORLD_BIBLE.md").exists()

    # Book outline written
    book_dir = tmp_path / "book-01"
    assert (book_dir / "BOOK_OUTLINE.md").exists()

    # Both chapters have final.md
    for n in (1, 2):
        ch_dir = book_dir / f"chapter-{n:02d}"
        assert ch_dir.exists()
        assert (ch_dir / "final.md").exists()
        assert (ch_dir / "v1.md").exists()
        assert "stub draft of chapter" in (ch_dir / "final.md").read_text()

    # Per-chapter reader/critic/humanizer reports
    for n in (1, 2):
        ch_dir = book_dir / f"chapter-{n:02d}"
        assert (ch_dir / "v1_reader.md").exists()
        assert (ch_dir / "v1_critic.md").exists()
        assert (ch_dir / "v1_humanizer.json").exists()

    # Continuity, provenance, manuscript
    assert (book_dir / "CONTINUITY_REPORT.md").exists()
    assert (book_dir / "PROVENANCE.md").exists()
    assert (book_dir / "MANUSCRIPT.md").exists()
    manuscript = (book_dir / "MANUSCRIPT.md").read_text()
    assert "Stub chapter 1" in manuscript or "Chapter 1" in manuscript
    assert "Stub chapter 2" in manuscript or "Chapter 2" in manuscript

    # Project saved with correct stage
    state = json.loads((tmp_path / "STATE.json").read_text())
    assert state["stage"] == "done"
    assert state["books"][0]["status"] == "done"
    assert len(state["books"][0]["chapters"]) == 2
    assert all(c["status"] == "done" for c in state["books"][0]["chapters"])


def test_revision_loop_kicks_in_when_score_too_low(tmp_path, monkeypatch, mocked_pipeline):
    """Force reader+critic to return a low score; verify the Reviser runs."""
    monkeypatch.setattr(reader_panel, "run",
                        lambda project, text: {
                            "reports": [{"persona_id": "x", "persona_name": "x",
                                         "scores": {}, "weighted": 4.0,
                                         "would_keep_reading": False,
                                         "landed": "", "missed": "", "verdict": ""}],
                            "average_score": 4.0, "keep_reading_pct": 0,
                        })
    monkeypatch.setattr(critic_panel, "run",
                        lambda project, text, beat: {
                            "reports": [{"persona_id": "x", "persona_name": "x",
                                         "scores": {}, "weighted": 4.0,
                                         "strengths": [], "weaknesses": [],
                                         "line_notes": [], "directive": "x"}],
                            "average_score": 4.0,
                        })

    project = BookProject(
        title="Revise Test",
        output_dir=tmp_path,
        target_chapters_per_book=1,
        target_words_per_chapter=200,
        min_chapter_score=7.0,       # well above the stubbed 4.0
        max_revisions_per_chapter=2, # → up to 3 iterations total
    )
    project.save()
    orchestrator.run(project)

    ch_dir = tmp_path / "book-01" / "chapter-01"
    # All 3 iterations should exist (initial + 2 revisions)
    assert (ch_dir / "v1.md").exists()
    assert (ch_dir / "v2.md").exists()
    assert (ch_dir / "v3.md").exists()
    # The final.md should match the highest-scoring iteration
    assert (ch_dir / "final.md").exists()

    # Iteration count is recorded
    state = json.loads((tmp_path / "STATE.json").read_text())
    ch_state = state["books"][0]["chapters"][0]
    assert ch_state["iterations"] >= 3


def test_resumability_skips_completed_chapters(tmp_path, mocked_pipeline):
    """A second run() with the same project should be a near-no-op."""
    project = BookProject(
        title="Resume Test", output_dir=tmp_path,
        target_chapters_per_book=2, target_words_per_chapter=200,
        min_chapter_score=7.0,
    )
    project.save()
    orchestrator.run(project)

    # Capture mtimes of final.md files
    final1 = tmp_path / "book-01" / "chapter-01" / "final.md"
    final2 = tmp_path / "book-01" / "chapter-02" / "final.md"
    mtime1, mtime2 = final1.stat().st_mtime_ns, final2.stat().st_mtime_ns

    # Second run on same project
    project2 = BookProject.load(tmp_path)
    orchestrator.run(project2)

    # final.md files should NOT have been rewritten (chapters already done)
    assert final1.stat().st_mtime_ns == mtime1
    assert final2.stat().st_mtime_ns == mtime2


def test_user_revisions_override_in_manuscript(tmp_path, mocked_pipeline):
    """If revisions/chapter-NN.md exists, it's used in MANUSCRIPT.md
    instead of the AI's final.md."""
    project = BookProject(
        title="Override Test", output_dir=tmp_path,
        target_chapters_per_book=2, target_words_per_chapter=200,
        min_chapter_score=7.0,
    )
    project.save()
    orchestrator.run(project)

    # Now drop a user revision and re-assemble
    book_dir = tmp_path / "book-01"
    rev_dir  = book_dir / "revisions"
    rev_dir.mkdir(parents=True, exist_ok=True)
    (rev_dir / "chapter-01.md").write_text("THIS IS THE USER VERSION", encoding="utf-8")

    project2 = BookProject.load(tmp_path)
    orchestrator._assemble_manuscript(project2, 1)

    manuscript = (book_dir / "MANUSCRIPT.md").read_text()
    assert "THIS IS THE USER VERSION" in manuscript


def test_humanize_disabled_skips_humanizer(tmp_path, mocked_pipeline, monkeypatch):
    """When project.humanize=False, the humanizer is never invoked and
    no v*_humanizer.json files are produced."""
    called = {"n": 0}

    def humanize_should_not_run(*a, **kw):
        called["n"] += 1
        return _stub_humanizer(*a, **kw)

    monkeypatch.setattr(humanizer, "run", humanize_should_not_run)

    project = BookProject(
        title="No Hum", output_dir=tmp_path,
        target_chapters_per_book=1, target_words_per_chapter=200,
        min_chapter_score=7.0, humanize=False,
    )
    project.save()
    orchestrator.run(project)

    assert called["n"] == 0
    # No humanizer side files were written
    ch_dir = tmp_path / "book-01" / "chapter-01"
    assert not (ch_dir / "v1_humanizer.json").exists()
