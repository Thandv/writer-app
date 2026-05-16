"""Tests for the export module — DOCX, EPUB, MD; revision overrides; slugify."""

import zipfile
from pathlib import Path
import pytest

from writer_app.shared.memory import BookProject, BookState, ChapterState
from writer_app import export as export_mod
from writer_app.export import _slugify, _resolve_chapter_text, _build_intermediate_markdown


# ── Setup helper ──────────────────────────────────────────────────────────

def _make_project(tmp_path, *, chapters: list[tuple[int, str, str]] = None,
                  with_revisions: dict[int, str] = None,
                  author_name="Real Name", pen_name="Pen Name"):
    chapters = chapters or [(1, "First", "First chapter prose.\n\nSecond paragraph.")]
    with_revisions = with_revisions or {}

    project = BookProject(
        title="Test Series",
        output_dir=tmp_path,
        target_chapters_per_book=len(chapters),
        author_name=author_name,
        author_pen_name=pen_name,
    )
    book = BookState(number=1, title="Test Book", status="done")
    project.upsert_book(book)

    for n, title, body in chapters:
        ch_dir = project.chapter_dir(1, n)
        ch_dir.mkdir(parents=True, exist_ok=True)
        (ch_dir / "final.md").write_text(body, encoding="utf-8")
        book.upsert_chapter(ChapterState(
            number=n, title=title, status="done",
            final_path=str(ch_dir / "final.md"),
        ))

    if with_revisions:
        rev_dir = project.book_dir(1) / "revisions"
        rev_dir.mkdir(parents=True, exist_ok=True)
        for n, body in with_revisions.items():
            (rev_dir / f"chapter-{n:02d}.md").write_text(body, encoding="utf-8")

    project.upsert_book(book)
    project.save()
    return project


# ── Slugify ───────────────────────────────────────────────────────────────

def test_slugify_basic():
    assert _slugify("The Bone Empire") == "the-bone-empire"


def test_slugify_strips_punctuation():
    assert _slugify("Hello, World!") == "hello-world"


def test_slugify_empty_falls_back_to_untitled():
    assert _slugify("") == "untitled"
    assert _slugify("!!!") == "untitled"


def test_slugify_collapses_multiple_separators():
    assert _slugify("A    B  ___   C") == "a-b-c"


# ── _resolve_chapter_text — revision precedence ───────────────────────────

def test_user_revision_wins_over_final(tmp_path):
    project = _make_project(
        tmp_path,
        chapters=[(1, "T", "AI version")],
        with_revisions={1: "USER REVISION"},
    )
    text = _resolve_chapter_text(project, 1, {"number": 1, "title": "T"})
    assert text == "USER REVISION"


def test_falls_back_to_ai_final_when_no_revision(tmp_path):
    project = _make_project(tmp_path, chapters=[(1, "T", "AI body")])
    text = _resolve_chapter_text(project, 1, {"number": 1, "title": "T"})
    assert text == "AI body"


def test_returns_empty_when_no_files(tmp_path):
    project = BookProject(title="T", output_dir=tmp_path)
    project.upsert_book(BookState(number=1, status="done"))
    text = _resolve_chapter_text(project, 1, {"number": 7, "title": "Missing"})
    assert text == ""


# ── Markdown intermediate ─────────────────────────────────────────────────

def test_intermediate_md_contains_title_and_disclosure(tmp_path):
    project = _make_project(tmp_path)
    md = _build_intermediate_markdown(project, 1)
    assert "Test Book" in md
    assert "Pen Name" in md
    assert "Real Name" in md
    assert "AI Disclosure" in md
    assert "Copyright" in md


def test_intermediate_md_includes_all_chapters(tmp_path):
    project = _make_project(tmp_path, chapters=[
        (1, "Ch one", "body one"),
        (2, "Ch two", "body two"),
        (3, "Ch three", "body three"),
    ])
    md = _build_intermediate_markdown(project, 1)
    for word in ("Ch one", "Ch two", "Ch three", "body one", "body two", "body three"):
        assert word in md


def test_intermediate_md_uses_user_revision_when_present(tmp_path):
    project = _make_project(tmp_path,
                            chapters=[(1, "T", "AI version body text here.")],
                            with_revisions={1: "USER REVISED BODY"})
    md = _build_intermediate_markdown(project, 1)
    assert "USER REVISED BODY" in md
    assert "AI version body text here." not in md


# ── DOCX ──────────────────────────────────────────────────────────────────

def test_docx_export_creates_valid_zip(tmp_path):
    project = _make_project(tmp_path)
    [docx] = export_mod.export_book(project, 1, ["docx"])
    assert docx.suffix == ".docx"
    with zipfile.ZipFile(docx) as z:
        names = z.namelist()
    assert "[Content_Types].xml" in names
    assert "word/document.xml" in names
    assert "word/styles.xml" in names


def test_docx_contains_title_author_and_chapter(tmp_path):
    project = _make_project(tmp_path)
    [docx] = export_mod.export_book(project, 1, ["docx"])
    with zipfile.ZipFile(docx) as z:
        doc = z.read("word/document.xml").decode("utf-8", errors="ignore")
    assert "Test Book" in doc
    assert "Pen Name" in doc
    assert "AI Disclosure" in doc
    assert "First" in doc  # the chapter title


def test_docx_renders_scene_break(tmp_path):
    """A chapter with a ⁂ scene break gets the SceneBreak paragraph style."""
    project = _make_project(tmp_path, chapters=[(1, "T",
        "first paragraph\n\n⁂\n\nsecond paragraph")])
    [docx] = export_mod.export_book(project, 1, ["docx"])
    with zipfile.ZipFile(docx) as z:
        doc = z.read("word/document.xml").decode("utf-8", errors="ignore")
    assert "SceneBreak" in doc


def test_docx_uses_revision(tmp_path):
    project = _make_project(tmp_path,
                            chapters=[(1, "T", "AI body")],
                            with_revisions={1: "USER REV BODY"})
    [docx] = export_mod.export_book(project, 1, ["docx"])
    with zipfile.ZipFile(docx) as z:
        doc = z.read("word/document.xml").decode("utf-8", errors="ignore")
    assert "USER REV BODY" in doc
    assert "AI body" not in doc


# ── EPUB ──────────────────────────────────────────────────────────────────

def test_epub_mimetype_is_first_and_uncompressed(tmp_path):
    project = _make_project(tmp_path)
    [epub] = export_mod.export_book(project, 1, ["epub"])
    with zipfile.ZipFile(epub) as z:
        infos = z.infolist()
        assert infos[0].filename == "mimetype"
        assert infos[0].compress_type == zipfile.ZIP_STORED
        assert z.read("mimetype") == b"application/epub+zip"


def test_epub_has_required_oebps_files(tmp_path):
    project = _make_project(tmp_path)
    [epub] = export_mod.export_book(project, 1, ["epub"])
    with zipfile.ZipFile(epub) as z:
        names = z.namelist()
    for required in ("META-INF/container.xml", "OEBPS/content.opf",
                     "OEBPS/toc.ncx", "OEBPS/styles.css",
                     "OEBPS/titlepage.xhtml", "OEBPS/frontmatter.xhtml",
                     "OEBPS/ch001.xhtml"):
        assert required in names, f"Missing: {required}"


def test_epub_uses_revision(tmp_path):
    project = _make_project(tmp_path,
                            chapters=[(1, "T", "AI body")],
                            with_revisions={1: "USER REV BODY"})
    [epub] = export_mod.export_book(project, 1, ["epub"])
    with zipfile.ZipFile(epub) as z:
        ch1 = z.read("OEBPS/ch001.xhtml").decode("utf-8", errors="ignore")
    assert "USER REV BODY" in ch1
    assert "AI body" not in ch1


def test_epub_nav_points_match_chapter_count(tmp_path):
    project = _make_project(tmp_path, chapters=[
        (1, "A", "a"), (2, "B", "b"), (3, "C", "c"),
    ])
    [epub] = export_mod.export_book(project, 1, ["epub"])
    with zipfile.ZipFile(epub) as z:
        ncx = z.read("OEBPS/toc.ncx").decode("utf-8", errors="ignore")
    # 2 frontmatter navpoints + 3 chapters = 5 total
    assert ncx.count("<navPoint") == 5


# ── MD format ──────────────────────────────────────────────────────────────

def test_md_export_writes_intermediate_markdown(tmp_path):
    project = _make_project(tmp_path)
    [md] = export_mod.export_book(project, 1, ["md"])
    assert md.suffix == ".md"
    text = md.read_text(encoding="utf-8")
    assert "# Test Book" in text
    assert "Pen Name" in text


# ── Empty-book edge case ──────────────────────────────────────────────────

def test_export_book_with_no_chapters_returns_empty(tmp_path):
    project = BookProject(title="T", output_dir=tmp_path)
    book = BookState(number=1, status="done")  # no chapters
    project.upsert_book(book)
    result = export_mod.export_book(project, 1, ["docx"])
    assert result == []


def test_unsupported_format_skipped_silently(tmp_path):
    """Without pandoc, unknown formats are skipped, not crashed."""
    project = _make_project(tmp_path)
    # 'pdf' is not in {docx, epub, md} — should be skipped
    result = export_mod.export_book(project, 1, ["pdf"])
    # If pandoc is installed it might handle it; otherwise empty list
    # Either way, no exception
    assert isinstance(result, list)
