"""
BookProject — shared state for a book / series being written.

Persists to STATE.json in the project dir so runs are resumable.
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime
import json
from typing import Optional


@dataclass
class ChapterState:
    number:     int                  # 1-indexed within the book
    title:      str = ""
    iterations: int = 0              # how many draft+revise passes done
    score:      float = 0.0          # last weighted average rubric score
    status:     str = "pending"      # pending | drafting | revising | done
    final_path: str = ""             # path to final chapter file

    # Humanizer telemetry (most recent pass)
    humanizer_passes:    int   = 0
    ai_score_before:     float = 0.0
    ai_score_after:      float = 0.0
    llm_ai_score_before: float = 0.0
    llm_ai_score_after:  float = 0.0

    # Provenance
    drafted_at:        str = ""        # ISO timestamp of last draft
    draft_model_used:  str = ""
    judge_model_used:  str = ""
    user_revised:      bool = False    # True if a user revision file exists


@dataclass
class BookState:
    number: int                      # 1-indexed within the series
    title:  str = ""
    outline_path: str = ""
    chapters: list = field(default_factory=list)   # list[ChapterState dicts]
    status: str = "pending"          # pending | outlining | writing | done

    def chapter(self, n: int) -> ChapterState:
        for ch in self.chapters:
            if ch["number"] == n:
                return ChapterState(**ch)
        return ChapterState(number=n)

    def upsert_chapter(self, ch: ChapterState):
        for i, existing in enumerate(self.chapters):
            if existing["number"] == ch.number:
                self.chapters[i] = asdict(ch)
                return
        self.chapters.append(asdict(ch))


@dataclass
class BookProject:
    title:      str
    output_dir: Path

    # User inputs (paths within output_dir)
    bible_dir:        str = "bible"
    user_bible_files: list = field(default_factory=list)

    # Pipeline configuration
    target_chapters_per_book: int = 30
    target_words_per_chapter: int = 3000
    target_books_in_series:   int = 1
    min_chapter_score:        float = 7.5      # rubric average to pass
    max_revisions_per_chapter: int  = 3

    # Humanizer configuration
    humanize:             bool  = True
    humanizer_target:     float = 3.5
    humanizer_max_passes: int   = 2

    # Author identity
    author_name:        str = ""
    author_pen_name:    str = ""

    # Pipeline state
    world_bible_path:    str = ""
    series_outline_path: str = ""
    books: list = field(default_factory=list)

    # Stage progress
    stage:         str = "init"
    started_at:    str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated:  str = ""

    # Models actually used at run time
    draft_model: str = ""
    judge_model: str = ""

    # ── Persistence ───────────────────────────────────────────────────────
    @property
    def state_path(self) -> Path:
        return Path(self.output_dir) / "STATE.json"

    def save(self):
        self.last_updated = datetime.now().isoformat()
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        d = asdict(self)
        d["output_dir"] = str(self.output_dir)
        self.state_path.write_text(json.dumps(d, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, output_dir: Path) -> "BookProject":
        p = Path(output_dir) / "STATE.json"
        if not p.exists():
            raise FileNotFoundError(f"No STATE.json in {output_dir}")
        d = json.loads(p.read_text(encoding="utf-8"))
        d["output_dir"] = Path(d["output_dir"])
        return cls(**d)

    # ── Book helpers ──────────────────────────────────────────────────────
    def book(self, n: int) -> BookState:
        for b in self.books:
            if b["number"] == n:
                return BookState(**b)
        return BookState(number=n)

    def upsert_book(self, b: BookState):
        for i, existing in enumerate(self.books):
            if existing["number"] == b.number:
                self.books[i] = asdict(b)
                return
        self.books.append(asdict(b))

    # ── Paths ─────────────────────────────────────────────────────────────
    def book_dir(self, n: int) -> Path:
        return Path(self.output_dir) / f"book-{n:02d}"

    def chapter_dir(self, book_n: int, ch_n: int) -> Path:
        return self.book_dir(book_n) / f"chapter-{ch_n:02d}"

    def summary(self) -> str:
        lines = [
            "",
            "=" * 60,
            f"  Project   : {self.title}",
            f"  Location  : {self.output_dir}",
            f"  Stage     : {self.stage}",
            f"  Books     : {len(self.books)} / {self.target_books_in_series}",
            f"  Models    : draft={self.draft_model}  judge={self.judge_model}",
        ]
        for b in self.books:
            done = sum(1 for c in b["chapters"] if c["status"] == "done")
            total = self.target_chapters_per_book
            lines.append(f"   • Book {b['number']:02d}: {b.get('title','(untitled)')}  "
                         f"— {done}/{total} chapters")
        lines.append("=" * 60)
        return "\n".join(lines)
