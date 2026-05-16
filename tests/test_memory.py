"""Tests for shared.memory — BookProject, BookState, ChapterState."""

import json
from pathlib import Path
import pytest
from writer_app.shared.memory import BookProject, BookState, ChapterState


# ── ChapterState ──────────────────────────────────────────────────────────

def test_chapter_state_defaults():
    ch = ChapterState(number=3)
    assert ch.number == 3
    assert ch.title == ""
    assert ch.iterations == 0
    assert ch.score == 0.0
    assert ch.status == "pending"
    assert ch.humanizer_passes == 0
    assert ch.user_revised is False


# ── BookState upsert ──────────────────────────────────────────────────────

def test_book_state_chapter_lookup_creates_default_if_missing():
    book = BookState(number=1)
    ch = book.chapter(7)
    # Returns a default ChapterState for unknown chapter number
    assert ch.number == 7
    assert ch.status == "pending"


def test_book_state_upsert_chapter_inserts_then_updates():
    book = BookState(number=1)
    book.upsert_chapter(ChapterState(number=1, title="First", status="done"))
    assert len(book.chapters) == 1
    assert book.chapters[0]["title"] == "First"

    # Upsert with same number → replace, not add
    book.upsert_chapter(ChapterState(number=1, title="First (v2)", status="done"))
    assert len(book.chapters) == 1
    assert book.chapters[0]["title"] == "First (v2)"

    # Different number → add
    book.upsert_chapter(ChapterState(number=2, title="Second"))
    assert len(book.chapters) == 2


# ── BookProject paths ─────────────────────────────────────────────────────

def test_project_book_dir_and_chapter_dir(tmp_path):
    p = BookProject(title="Test", output_dir=tmp_path)
    assert p.book_dir(1) == tmp_path / "book-01"
    assert p.book_dir(12) == tmp_path / "book-12"
    assert p.chapter_dir(1, 3) == tmp_path / "book-01" / "chapter-03"


def test_project_state_path(tmp_path):
    p = BookProject(title="X", output_dir=tmp_path)
    assert p.state_path == tmp_path / "STATE.json"


# ── BookProject save/load round-trip ──────────────────────────────────────

def test_project_save_creates_state_json(tmp_path):
    p = BookProject(title="Save Test", output_dir=tmp_path,
                    author_name="A", author_pen_name="B",
                    target_chapters_per_book=10,
                    humanize=False, humanizer_target=2.0)
    p.save()
    assert (tmp_path / "STATE.json").exists()
    data = json.loads((tmp_path / "STATE.json").read_text())
    assert data["title"] == "Save Test"
    assert data["author_name"] == "A"
    assert data["author_pen_name"] == "B"
    assert data["target_chapters_per_book"] == 10
    assert data["humanize"] is False
    assert data["humanizer_target"] == 2.0
    assert data["last_updated"]  # populated by save()


def test_project_load_round_trip(tmp_path):
    p = BookProject(title="Round", output_dir=tmp_path,
                    target_books_in_series=2,
                    min_chapter_score=8.0)
    p.save()
    loaded = BookProject.load(tmp_path)
    assert loaded.title == "Round"
    assert loaded.target_books_in_series == 2
    assert loaded.min_chapter_score == 8.0
    assert loaded.output_dir == tmp_path


def test_project_load_missing_state_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        BookProject.load(tmp_path)


def test_project_books_round_trip(tmp_path):
    p = BookProject(title="T", output_dir=tmp_path)
    book = BookState(number=1, title="The First", status="done")
    book.upsert_chapter(ChapterState(number=1, title="Ch 1", status="done", score=7.8))
    p.upsert_book(book)
    p.save()

    loaded = BookProject.load(tmp_path)
    assert len(loaded.books) == 1
    b = loaded.book(1)
    assert b.title == "The First"
    assert len(b.chapters) == 1
    assert b.chapters[0]["score"] == 7.8


# ── BookProject.book() lookup ──────────────────────────────────────────────

def test_project_book_lookup_unknown_returns_default(tmp_path):
    p = BookProject(title="T", output_dir=tmp_path)
    b = p.book(99)
    # Should return a default BookState rather than crash
    assert b.number == 99
    assert b.status == "pending"


# ── summary() format ──────────────────────────────────────────────────────

def test_project_summary_includes_title_and_stage(tmp_path):
    p = BookProject(title="My Story", output_dir=tmp_path,
                    target_books_in_series=3, draft_model="m",
                    judge_model="j")
    p.stage = "writing"
    s = p.summary()
    assert "My Story" in s
    assert "writing" in s
    assert "draft=m" in s
    assert "judge=j" in s
    # Counts books
    assert "0 / 3" in s


def test_project_summary_lists_books(tmp_path):
    p = BookProject(title="T", output_dir=tmp_path)
    book = BookState(number=1, title="The Bone Empire")
    book.upsert_chapter(ChapterState(number=1, status="done"))
    book.upsert_chapter(ChapterState(number=2, status="done"))
    book.upsert_chapter(ChapterState(number=3, status="pending"))
    p.upsert_book(book)
    s = p.summary()
    assert "The Bone Empire" in s
    # 2 of 30 (default) chapters done
    assert "2/30" in s


# ── upsert_book ───────────────────────────────────────────────────────────

def test_upsert_book_inserts_then_updates(tmp_path):
    p = BookProject(title="T", output_dir=tmp_path)
    p.upsert_book(BookState(number=1, title="First"))
    assert len(p.books) == 1
    p.upsert_book(BookState(number=1, title="First (v2)"))
    assert len(p.books) == 1
    assert p.books[0]["title"] == "First (v2)"
    p.upsert_book(BookState(number=2, title="Second"))
    assert len(p.books) == 2
