"""Tests for the provenance module — PROVENANCE.md + KDP disclosure."""

from pathlib import Path
import pytest
from writer_app.shared.memory import BookProject, BookState, ChapterState
from writer_app import provenance as provenance_mod


def _make_minimal_project(tmp_path):
    project = BookProject(
        title="The Bone Empire",
        output_dir=tmp_path,
        author_name="Jane Doe",
        author_pen_name="J. D. Bones",
        draft_model="mistral-nemo:12b",
        judge_model="qwen2.5:7b",
    )
    book = BookState(number=1, title="Salt and Steel", status="done")
    book.upsert_chapter(ChapterState(
        number=1, title="The Lighthouse", status="done",
        score=8.0, iterations=2,
        drafted_at="2026-05-15T12:00:00",
        draft_model_used="mistral-nemo:12b",
        judge_model_used="qwen2.5:7b",
        humanizer_passes=1,
        ai_score_before=7.5, ai_score_after=3.2,
        user_revised=False,
    ))
    book.upsert_chapter(ChapterState(
        number=2, title="The Bargain", status="done",
        score=7.0, iterations=1,
        drafted_at="2026-05-15T12:30:00",
        humanizer_passes=0,
        ai_score_before=4.0, ai_score_after=4.0,
        user_revised=True,
    ))
    project.upsert_book(book)
    project.save()
    return project


# ── PROVENANCE.md generation ───────────────────────────────────────────────

def test_write_book_provenance_creates_file(tmp_path):
    project = _make_minimal_project(tmp_path)
    path = provenance_mod.write_book_provenance(project, 1)
    assert path.exists()
    assert path.name == "PROVENANCE.md"
    assert path.parent.name == "book-01"


def test_provenance_contains_author_and_pen_name(tmp_path):
    project = _make_minimal_project(tmp_path)
    path = provenance_mod.write_book_provenance(project, 1)
    text = path.read_text(encoding="utf-8")
    assert "Jane Doe" in text
    assert "J. D. Bones" in text


def test_provenance_contains_model_names(tmp_path):
    project = _make_minimal_project(tmp_path)
    path = provenance_mod.write_book_provenance(project, 1)
    text = path.read_text(encoding="utf-8")
    assert "mistral-nemo:12b" in text
    assert "qwen2.5:7b" in text


def test_provenance_has_audit_table(tmp_path):
    project = _make_minimal_project(tmp_path)
    path = provenance_mod.write_book_provenance(project, 1)
    text = path.read_text(encoding="utf-8")
    assert "Per-chapter audit" in text
    # Both chapters appear with their AI-score deltas
    assert "7.5→3.2" in text or "7.5 → 3.2" in text


def test_provenance_records_user_revised_chapter(tmp_path):
    project = _make_minimal_project(tmp_path)
    path = provenance_mod.write_book_provenance(project, 1)
    text = path.read_text(encoding="utf-8")
    # One chapter has user_revised=True
    assert "yes" in text  # the column will show "yes" for ch 2


def test_provenance_counts_chapters(tmp_path):
    project = _make_minimal_project(tmp_path)
    path = provenance_mod.write_book_provenance(project, 1)
    text = path.read_text(encoding="utf-8")
    assert "Total chapters: 2" in text
    assert "Chapters with user revision file: 1" in text


def test_provenance_for_missing_author_name(tmp_path):
    project = BookProject(title="T", output_dir=tmp_path)
    project.upsert_book(BookState(number=1, status="done"))
    path = provenance_mod.write_book_provenance(project, 1)
    text = path.read_text(encoding="utf-8")
    # Should not crash; both names get a placeholder
    assert "(author name not set)" in text or "(real name not set)" in text


def test_provenance_includes_pipeline_config(tmp_path):
    project = BookProject(
        title="T", output_dir=tmp_path,
        target_chapters_per_book=42,
        target_words_per_chapter=2750,
        min_chapter_score=6.5,
        humanize=False,
    )
    project.upsert_book(BookState(number=1, status="done"))
    path = provenance_mod.write_book_provenance(project, 1)
    text = path.read_text(encoding="utf-8")
    assert "42" in text   # chapters per book
    assert "2750" in text # words per chapter
    assert "6.5" in text  # threshold
    assert "False" in text  # humanizer disabled


# ── KDP disclosure ────────────────────────────────────────────────────────

def test_write_disclosure_creates_file(tmp_path):
    project = BookProject(title="T", output_dir=tmp_path)
    path = provenance_mod.write_disclosure(project)
    assert path.exists()
    assert path.name == "KDP_DISCLOSURE.md"
    assert path.parent == tmp_path


def test_disclosure_says_yes_ai_generated(tmp_path):
    project = BookProject(title="T", output_dir=tmp_path)
    path = provenance_mod.write_disclosure(project)
    text = path.read_text(encoding="utf-8")
    assert "Yes" in text
    assert "AI-generated" in text


def test_disclosure_mentions_kdp(tmp_path):
    project = BookProject(title="T", output_dir=tmp_path)
    path = provenance_mod.write_disclosure(project)
    text = path.read_text(encoding="utf-8")
    assert "KDP" in text or "Amazon" in text
