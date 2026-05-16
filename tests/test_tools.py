"""Tests for shared.tools — file ops + corpus retrieval."""

from pathlib import Path
import pytest
from writer_app.shared import tools as tools_mod
from writer_app.shared.tools import (
    read_file, write_file, append_file, list_files,
    retrieve_corpus, make_tool,
    _keywords, _tokenize,
)


# ── File ops ──────────────────────────────────────────────────────────────

def test_read_file_returns_content(tmp_path):
    p = tmp_path / "hello.txt"
    p.write_text("hello world", encoding="utf-8")
    assert read_file(str(p)) == "hello world"


def test_read_file_missing(tmp_path):
    result = read_file(str(tmp_path / "nope.txt"))
    assert "File not found" in result


def test_read_file_truncates_large_content(tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("x" * 50_000, encoding="utf-8")
    text = read_file(str(p))
    assert "[truncated" in text
    assert len(text) < 50_000


def test_read_file_respects_max_chars_override(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("abcdef" * 100, encoding="utf-8")
    text = read_file(str(p), max_chars=10)
    assert "truncated" in text
    # First 10 chars present
    assert text.startswith("abcdef")


def test_write_file_creates_parent_dirs(tmp_path):
    p = tmp_path / "a" / "b" / "c.md"
    msg = write_file(str(p), "content")
    assert p.exists()
    assert p.read_text() == "content"
    assert "Written" in msg


def test_write_file_overwrites(tmp_path):
    p = tmp_path / "x.md"
    write_file(str(p), "first")
    write_file(str(p), "second")
    assert p.read_text() == "second"


def test_append_file_appends(tmp_path):
    p = tmp_path / "log.txt"
    append_file(str(p), "line1\n")
    append_file(str(p), "line2\n")
    assert p.read_text() == "line1\nline2\n"


def test_append_file_creates_if_missing(tmp_path):
    p = tmp_path / "new.txt"
    append_file(str(p), "hi")
    assert p.read_text() == "hi"


def test_list_files_returns_sorted(tmp_path):
    for name in ("c.md", "a.md", "b.md"):
        (tmp_path / name).write_text("x")
    result = list_files(str(tmp_path / "*.md"))
    lines = result.strip().split("\n")
    assert lines == sorted(lines)
    assert len(lines) == 3


def test_list_files_no_match(tmp_path):
    result = list_files(str(tmp_path / "*.zzz"))
    assert "No files matching" in result


# ── Tokenizer / keyword extraction ────────────────────────────────────────

def test_tokenize_lowercases_and_strips_short():
    toks = _tokenize("Quickly, the QUICK fox a")
    # "a" too short, others kept lower
    assert "quickly" in toks
    assert "quick" in toks
    assert "fox" in toks
    assert "a" not in toks


def test_keywords_filters_stopwords_and_dedupes():
    text = "the lighthouse and the cottage with the lantern"
    kws = _keywords(text)
    # Stopwords and short words are removed
    assert "the" not in kws
    assert "and" not in kws
    # 4+ char content words survive
    assert "lighthouse" in kws or "cottage" in kws or "lantern" in kws


def test_keywords_returns_at_most_n():
    text = " ".join(f"word{i:02d}" for i in range(50))
    kws = _keywords(text, n=5)
    assert len(kws) <= 5


# ── retrieve_corpus ───────────────────────────────────────────────────────

def test_retrieve_corpus_no_dir(tmp_path, monkeypatch):
    """Missing corpus dir returns a helpful message, doesn't crash."""
    fake = tmp_path / "nothing-here"
    monkeypatch.setattr(tools_mod, "CORPUS_DIR", fake)
    result = retrieve_corpus("anything")
    assert "Corpus directory not found" in result


def test_retrieve_corpus_finds_matching_paragraph(tmp_path, monkeypatch):
    """Build a tiny corpus, search it, verify match."""
    cards_dir = tmp_path / "style_cards"
    cards_dir.mkdir()
    (cards_dir / "test.md").write_text(
        "# Style: dragonblade\n\n"
        "This paragraph mentions dragons and blades many times. "
        "Dragons breathe fire and the blade sings. "
        "More dragons. More blades. The dragon blade legend continues. "
        "Dragons of the highest order. Blade craft requires dedication.\n\n"
        "Unrelated: cooking eggs in the morning.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tools_mod, "CORPUS_DIR", tmp_path)
    result = retrieve_corpus("dragon blade fantasy combat", kinds="style_cards")
    # Should find the first paragraph with multiple keyword hits
    assert "dragon" in result.lower() or "blade" in result.lower()


def test_retrieve_corpus_empty_query():
    result = retrieve_corpus("a the and or")  # all stopwords/too short
    assert "No usable keywords" in result or "Corpus directory not found" in result


def test_retrieve_corpus_kinds_filter(tmp_path, monkeypatch):
    """Only the requested kind is searched."""
    (tmp_path / "style_cards").mkdir()
    (tmp_path / "craft").mkdir()
    (tmp_path / "style_cards" / "a.md").write_text(
        "ABC " * 20 + "dragonish dragonish dragonish" + " ABC " * 20, encoding="utf-8")
    (tmp_path / "craft" / "b.md").write_text(
        "DEF " * 20 + "fakeword fakeword fakeword" + " DEF " * 20, encoding="utf-8")
    monkeypatch.setattr(tools_mod, "CORPUS_DIR", tmp_path)

    r1 = retrieve_corpus("dragonish dragonish dragonish dragonish", kinds="craft")
    r2 = retrieve_corpus("dragonish dragonish dragonish dragonish", kinds="style_cards")
    # craft has no "dragonish"; style_cards does
    assert "dragonish" not in r1.lower() or "No corpus passages" in r1
    # style_cards search should hit
    assert ("dragonish" in r2.lower()) or ("score" in r2)


def test_retrieve_corpus_caps_at_k(tmp_path, monkeypatch):
    """k limits the number of returned hits."""
    d = tmp_path / "style_cards"; d.mkdir()
    # Create 5 files each with the same matching paragraph
    for i in range(5):
        (d / f"f{i}.md").write_text(
            "alpha beta gamma alpha beta gamma alpha beta gamma " * 20 + "\n\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(tools_mod, "CORPUS_DIR", tmp_path)
    result = retrieve_corpus("alpha beta gamma alpha", kinds="style_cards", k=2)
    # Hit-cap should keep result manageable; verify by counting headers
    assert result.count("### ") <= 2 or "No corpus passages" in result


# ── Tool schema builder ───────────────────────────────────────────────────

def test_make_tool_produces_ollama_schema():
    t = make_tool(
        "foo",
        "Does foo.",
        {"x": {"type": "string"}, "y": {"type": "integer"}},
        ["x"],
    )
    assert t["type"] == "function"
    assert t["function"]["name"] == "foo"
    assert t["function"]["description"] == "Does foo."
    assert t["function"]["parameters"]["properties"]["x"]["type"] == "string"
    assert t["function"]["parameters"]["required"] == ["x"]


def test_handlers_dict_complete():
    """Every tool schema name must have a handler."""
    from writer_app.shared.tools import HANDLERS
    expected = {"read_file", "write_file", "append_file", "list_files",
                "retrieve_corpus"}
    assert expected.issubset(HANDLERS.keys())
    for name, fn in HANDLERS.items():
        assert callable(fn), f"Handler {name} is not callable"
