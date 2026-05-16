"""Tests for plotter.parse_chapters and book-title extraction."""

from pathlib import Path
import pytest
from writer_app.plotter import parse_chapters, _extract_book_title


# ── parse_chapters: dash variants ─────────────────────────────────────────

def test_parse_chapters_em_dash(tmp_path):
    outline = """# Book 1: Test

## Chapter 1 — The Start
- **POV:** Iri
- **Goal:** Open

## Chapter 2 — The Middle
- **POV:** Lev
- **Goal:** Continue
"""
    p = tmp_path / "out.md"
    p.write_text(outline, encoding="utf-8")
    chs = parse_chapters(p)
    assert len(chs) == 2
    assert chs[0]["title"] == "The Start"
    assert chs[1]["title"] == "The Middle"


def test_parse_chapters_hyphen(tmp_path):
    outline = """# Book 1: Test

## Chapter 1 - The Start
beat body

## Chapter 2 - The Middle
more body
"""
    p = tmp_path / "out.md"; p.write_text(outline, encoding="utf-8")
    chs = parse_chapters(p)
    assert len(chs) == 2
    assert chs[0]["title"] == "The Start"


def test_parse_chapters_colon(tmp_path):
    outline = """## Chapter 1: Opening
body
"""
    p = tmp_path / "out.md"; p.write_text(outline, encoding="utf-8")
    chs = parse_chapters(p)
    assert len(chs) == 1
    assert chs[0]["title"] == "Opening"


def test_parse_chapters_body_captures_until_next_header(tmp_path):
    outline = """## Chapter 1 — A
- **POV:** P1
- Beat one
- Beat two

## Chapter 2 — B
- **POV:** P2
"""
    p = tmp_path / "out.md"; p.write_text(outline, encoding="utf-8")
    chs = parse_chapters(p)
    assert "Beat one" in chs[0]["body"]
    assert "Beat two" in chs[0]["body"]
    # Body of ch 1 must not bleed into ch 2
    assert "P2" not in chs[0]["body"]


def test_parse_chapters_empty_file_returns_empty(tmp_path):
    p = tmp_path / "out.md"; p.write_text("# No chapters here", encoding="utf-8")
    assert parse_chapters(p) == []


def test_parse_chapters_numbering_preserved(tmp_path):
    outline = """## Chapter 5 — Late start
body
"""
    p = tmp_path / "out.md"; p.write_text(outline, encoding="utf-8")
    chs = parse_chapters(p)
    assert chs[0]["number"] == 5


def test_parse_chapters_handles_double_digit(tmp_path):
    outline = "\n".join(f"## Chapter {i} — t{i}\nbody{i}" for i in range(1, 13))
    p = tmp_path / "out.md"; p.write_text(outline, encoding="utf-8")
    chs = parse_chapters(p)
    assert [c["number"] for c in chs] == list(range(1, 13))


# ── _extract_book_title ───────────────────────────────────────────────────

def test_extract_book_title_colon(tmp_path):
    p = tmp_path / "outline.md"
    p.write_text("# Book 1: The Bone Empire\n\n## Chapter 1 — A\nbody", encoding="utf-8")
    assert _extract_book_title(p) == "The Bone Empire"


def test_extract_book_title_em_dash(tmp_path):
    p = tmp_path / "outline.md"
    p.write_text("# Book 1 — Crown of Salt\n\n## Chapter 1 — A\nbody", encoding="utf-8")
    assert _extract_book_title(p) == "Crown of Salt"


def test_extract_book_title_hyphen(tmp_path):
    p = tmp_path / "outline.md"
    p.write_text("# Book 1 - Sea of Glass\n", encoding="utf-8")
    assert _extract_book_title(p) == "Sea of Glass"


def test_extract_book_title_missing_returns_empty(tmp_path):
    p = tmp_path / "outline.md"
    p.write_text("just text without a book heading\n## Chapter 1 — A\n", encoding="utf-8")
    assert _extract_book_title(p) == ""


# ── Chapter body shape ────────────────────────────────────────────────────

def test_chapter_dict_has_required_keys(tmp_path):
    p = tmp_path / "outline.md"
    p.write_text("## Chapter 1 — t\nbody\n", encoding="utf-8")
    [ch] = parse_chapters(p)
    assert set(ch.keys()) == {"number", "title", "body"}
    assert isinstance(ch["number"], int)
    assert isinstance(ch["title"], str)
    assert isinstance(ch["body"], str)
