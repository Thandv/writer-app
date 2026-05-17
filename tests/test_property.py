"""Property-based tests using Hypothesis.

These verify invariants that should hold across arbitrary inputs, not
specific examples. They catch edge cases (empty inputs, extreme values,
unicode boundaries, etc.) that hand-written examples miss.
"""

import re
import string
import tempfile
from pathlib import Path

from hypothesis import given, strategies as st, settings
import pytest

from writer_app.shared.memory  import BookProject, BookState, ChapterState
from writer_app.shared.rubric  import (
    CRITIC_RUBRIC, READER_RUBRIC, weighted_average,
)
from writer_app.export         import _slugify
from writer_app.humanizer      import _heuristic_scan
from writer_app.plotter        import parse_chapters


# ── Rubric weighted_average invariants ────────────────────────────────────

@given(st.dictionaries(
    keys=st.sampled_from(list(CRITIC_RUBRIC.keys())),
    values=st.integers(min_value=-50, max_value=50),
    min_size=1, max_size=len(CRITIC_RUBRIC),
))
def test_weighted_average_always_in_1_to_10(scores):
    """Result is always clamped into [1.0, 10.0] regardless of input."""
    result = weighted_average(scores, CRITIC_RUBRIC)
    assert 1.0 <= result <= 10.0, f"out of range for {scores}: got {result}"


@given(st.dictionaries(
    keys=st.sampled_from(list(READER_RUBRIC.keys())),
    values=st.floats(allow_nan=False, allow_infinity=False,
                     min_value=-1000, max_value=1000),
    min_size=1, max_size=len(READER_RUBRIC),
))
def test_weighted_average_handles_arbitrary_floats(scores):
    """Floats are coerced and clamped; never raises."""
    result = weighted_average(scores, READER_RUBRIC)
    assert 1.0 <= result <= 10.0


@given(st.integers(min_value=1, max_value=10))
def test_weighted_average_uniform_returns_that_value(value):
    """When every category has the same score, the average IS that score."""
    scores = {k: value for k in CRITIC_RUBRIC}
    assert weighted_average(scores, CRITIC_RUBRIC) == float(value)


# ── slugify invariants ────────────────────────────────────────────────────

@given(st.text())
@settings(max_examples=300)
def test_slugify_only_contains_safe_chars(text):
    """Slug consists only of lowercase ASCII alphanumerics and hyphens."""
    slug = _slugify(text)
    assert re.fullmatch(r"[a-z0-9-]+", slug), f"unsafe chars in {slug!r} from {text!r}"


@given(st.text())
@settings(max_examples=300)
def test_slugify_never_empty(text):
    """Slug is never the empty string; falls back to 'untitled' when needed."""
    slug = _slugify(text)
    assert len(slug) >= 1


@given(st.text())
def test_slugify_no_leading_or_trailing_hyphens(text):
    slug = _slugify(text)
    assert not slug.startswith("-")
    assert not slug.endswith("-")


# ── Humanizer heuristic_scan invariants ───────────────────────────────────

@given(st.text(min_size=0, max_size=1000))
@settings(max_examples=200, deadline=None)
def test_heuristic_scan_returns_valid_shape(text):
    """The scan returns the expected keys and ai_score in [1.0, 10.0]."""
    result = _heuristic_scan(text)
    assert set(result.keys()) >= {"hits", "samples", "ai_score", "n_words"}
    assert 1.0 <= result["ai_score"] <= 10.0
    assert isinstance(result["hits"], dict)
    assert isinstance(result["samples"], dict)
    assert result["n_words"] >= 1


@given(st.text(alphabet=string.ascii_letters + " .,\n", min_size=0, max_size=500))
def test_heuristic_scan_handles_plain_ascii_text(text):
    """No crash on plain ASCII text of any composition."""
    _heuristic_scan(text)  # just verify no exception


# ── Plotter parse_chapters invariants ─────────────────────────────────────

@given(numbers=st.lists(
    st.integers(min_value=1, max_value=99),
    min_size=1, max_size=10, unique=True,
))
@settings(max_examples=100)
def test_parse_chapters_extracts_all_chapter_numbers(numbers):
    """A synthetic outline with N chapter headers parses to N chapters with
    the same numbers (in order of appearance)."""
    import tempfile
    sorted_numbers = sorted(numbers)
    outline = "# Book 1: Generated\n\n"
    for n in sorted_numbers:
        outline += f"## Chapter {n} — Generated\n- body for ch {n}\n\n"
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                      encoding="utf-8") as f:
        f.write(outline)
        path = Path(f.name)
    try:
        chs = parse_chapters(path)
        assert [c["number"] for c in chs] == sorted_numbers
    finally:
        path.unlink(missing_ok=True)


@given(title=st.text(min_size=0, max_size=50,
                      alphabet=string.ascii_letters + " "))
@settings(max_examples=50)
def test_parse_chapters_title_extracted_verbatim(title):
    """Whatever title text appears after the dash gets returned as title."""
    import tempfile
    if not title.strip():
        return
    if any(ch in title for ch in ("##", "\n")):
        return
    outline = f"## Chapter 1 — {title}\nbody\n"
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                      encoding="utf-8") as f:
        f.write(outline)
        path = Path(f.name)
    try:
        chs = parse_chapters(path)
        assert len(chs) == 1
        assert chs[0]["title"] == title.strip()
    finally:
        path.unlink(missing_ok=True)


# ── BookProject save/load round-trip ──────────────────────────────────────

@st.composite
def project_params(draw):
    return {
        "title":                     draw(st.text(min_size=1, max_size=30,
                                                  alphabet=string.printable)),
        "target_books_in_series":    draw(st.integers(min_value=1, max_value=10)),
        "target_chapters_per_book":  draw(st.integers(min_value=1, max_value=50)),
        "target_words_per_chapter":  draw(st.integers(min_value=500, max_value=10000)),
        "min_chapter_score":         draw(st.floats(min_value=1.0, max_value=10.0,
                                                    allow_nan=False)),
        "max_revisions_per_chapter": draw(st.integers(min_value=0, max_value=10)),
        "humanize":                  draw(st.booleans()),
        "humanizer_target":          draw(st.floats(min_value=1.0, max_value=10.0,
                                                    allow_nan=False)),
        "humanizer_max_passes":      draw(st.integers(min_value=0, max_value=5)),
        "author_name":               draw(st.text(max_size=50, alphabet=string.printable)),
        "author_pen_name":           draw(st.text(max_size=50, alphabet=string.printable)),
    }


@given(params=project_params())
@settings(max_examples=50)
def test_book_project_round_trip(params):
    """For any valid config, save → load preserves every field."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        project = BookProject(output_dir=out_dir, **params)
        project.save()

        loaded = BookProject.load(out_dir)
        for k, v in params.items():
            actual = getattr(loaded, k)
            assert actual == v, f"{k}: expected {v!r}, got {actual!r}"


@given(
    book_n=st.integers(min_value=1, max_value=12),
    chapter_n=st.integers(min_value=1, max_value=50),
)
def test_chapter_dir_format_is_zero_padded(book_n, chapter_n):
    """The chapter dir path always has 2-digit zero-padded book/chapter numbers."""
    p = BookProject(title="T", output_dir=Path("/tmp/x"))
    d = p.chapter_dir(book_n, chapter_n)
    # Verify both pad to 2 digits
    assert f"book-{book_n:02d}" in str(d)
    assert f"chapter-{chapter_n:02d}" in str(d)


# ── BookState upsert is idempotent + order-preserving ─────────────────────

@given(st.lists(
    st.integers(min_value=1, max_value=20),
    min_size=1, max_size=10,
))
def test_book_state_upsert_unique_by_number(numbers):
    """After upserting a set of chapter numbers (with duplicates), each
    unique number appears exactly once."""
    book = BookState(number=1)
    for n in numbers:
        book.upsert_chapter(ChapterState(number=n, title=f"ch-{n}"))

    final_numbers = [c["number"] for c in book.chapters]
    assert len(final_numbers) == len(set(final_numbers))
    assert set(final_numbers) == set(numbers)
