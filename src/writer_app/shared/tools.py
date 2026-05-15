"""
File and corpus tools for the writer agents.

Mirrors the standard read/write/list pattern, plus `retrieve_corpus` which
surfaces passages from the local fantasy corpus (Gutenberg classics +
style cards + craft notes) as RAG context for drafting.
"""

import glob as _glob
import re
import subprocess
from pathlib import Path
from typing import Optional

from .corpus import CORPUS_DIR

MAX_OUTPUT = 12_000  # chars


# ── File ops ───────────────────────────────────────────────────────────────

def read_file(path: str, max_chars: int = MAX_OUTPUT) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"File not found: {path}"
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n[truncated — {len(text)} chars total]"
        return text
    except Exception as e:
        return f"Error reading {path}: {e}"


def write_file(path: str, content: str) -> str:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Written: {path} ({len(content)} chars)"


def append_file(path: str, content: str) -> str:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(content)
    return f"Appended {len(content)} chars to {path}"


def list_files(pattern: str) -> str:
    matches = _glob.glob(str(Path(pattern).expanduser()), recursive=True)
    return "\n".join(sorted(matches)) if matches else f"No files matching: {pattern}"


# ── Corpus retrieval ───────────────────────────────────────────────────────

_PARA_RE = re.compile(r"\n\s*\n")
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "have",
    "was", "were", "are", "but", "you", "your", "they", "their", "them",
    "she", "her", "him", "his", "had", "has", "not", "all", "one", "two",
    "would", "could", "should", "what", "when", "where", "which", "who",
    "been", "being", "than", "then", "there", "these", "those", "about",
}


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z']{2,}", text)]


def _keywords(text: str, n: int = 12) -> list[str]:
    freq: dict[str, int] = {}
    for w in _tokenize(text):
        if w in _STOP or len(w) < 4:
            continue
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (-len(kv[0]), kv[1]))
    return [w for w, _ in ranked[:n]]


def retrieve_corpus(query: str, kinds: str = "all", k: int = 5) -> str:
    """Return up to k passages from the corpus matching the query.
    kinds: all | gutenberg | style_cards | craft"""
    kinds_list: list[str]
    if kinds == "all":
        kinds_list = ["style_cards", "craft", "gutenberg"]
    else:
        kinds_list = [kinds]

    if not CORPUS_DIR.exists():
        return ("Corpus directory not found. Run `writer corpus` to build the "
                "public-domain corpus and generate style cards.")

    kws = _keywords(query)
    if not kws:
        return "No usable keywords in query."

    hits = []
    for kind in kinds_list:
        base = CORPUS_DIR / kind
        if not base.exists():
            continue
        for fpath in sorted(base.rglob("*")):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in {".md", ".txt"}:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            paragraphs = _PARA_RE.split(text)
            for para in paragraphs:
                if len(para) < 120 or len(para) > 1800:
                    continue
                lower = para.lower()
                score = sum(1 for kw in kws if kw in lower)
                if score >= 2:
                    hits.append((score, fpath, para.strip()))

    if not hits:
        return f"No corpus passages matched. Keywords: {', '.join(kws)}"

    hits.sort(key=lambda t: -t[0])
    chosen = []
    for score, fpath, para in hits:
        rel = fpath.relative_to(CORPUS_DIR)
        same = sum(1 for c in chosen if c[1] == rel)
        if same >= 2:
            continue
        chosen.append((score, rel, para))
        if len(chosen) >= k:
            break

    return "\n\n".join(
        f"### {rel}  (match score {score})\n{para}"
        for score, rel, para in chosen
    )


# ── Tool schemas (Ollama format) ───────────────────────────────────────────

def make_tool(name: str, description: str, properties: dict, required: list) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


READ_FILE = make_tool(
    "read_file", "Read a file's contents.",
    {"path": {"type": "string"}}, ["path"],
)
WRITE_FILE = make_tool(
    "write_file", "Write content to a file (creates parent dirs).",
    {"path": {"type": "string"}, "content": {"type": "string"}},
    ["path", "content"],
)
APPEND_FILE = make_tool(
    "append_file", "Append content to a file (creates if missing).",
    {"path": {"type": "string"}, "content": {"type": "string"}},
    ["path", "content"],
)
LIST_FILES = make_tool(
    "list_files", "List files matching a glob pattern.",
    {"pattern": {"type": "string"}}, ["pattern"],
)
RETRIEVE_CORPUS = make_tool(
    "retrieve_corpus",
    ("Retrieve passages from the local fantasy corpus (Project Gutenberg classics, "
     "style cards describing modern bestseller voices, and craft notes). "
     "Use this to find concrete prose examples and structural references."),
    {"query": {"type": "string",
               "description": "Natural-language description of what you want examples of."},
     "kinds": {"type": "string",
               "description": "all | gutenberg | style_cards | craft (default: all)"},
     "k":     {"type": "integer",
               "description": "Max passages to return (default 5)."}},
    ["query"],
)

HANDLERS = {
    "read_file":       read_file,
    "write_file":      write_file,
    "append_file":     append_file,
    "list_files":      list_files,
    "retrieve_corpus": retrieve_corpus,
}
