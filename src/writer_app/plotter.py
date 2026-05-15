"""
Plotter Agent

Produces:
  - SERIES_OUTLINE.md (one document covering the whole series arc)
  - book-NN/BOOK_OUTLINE.md (chapter-by-chapter beats for one book)
"""

import re
from pathlib import Path
from .shared.llm import generate, run_agent
from .shared.tools import (
    WRITE_FILE, READ_FILE, LIST_FILES, RETRIEVE_CORPUS, HANDLERS,
)
from .shared.memory import BookProject, BookState


SERIES_SYSTEM = """You are the Plotter for a fantasy book series.
Your job is to design the SERIES-LEVEL arc that book outlines will hang off.

Given the WORLD_BIBLE.md and the author's notes, produce SERIES_OUTLINE.md with:

# Series: <title>

## Premise (one paragraph)
The hook. Why this story exists. Whose journey it follows. What the world
costs them.

## Themes
Three to five themes the series is interrogating. Concrete. Not "good vs evil"
but "the price of inheritance" or "what survives translation between cultures".

## Series Arc
The shape of the whole. Status quo → inciting → midpoint → all-is-lost → climax.
Be specific about the change in protagonist and world by the end.

## Book Breakdown
For each of the {n_books} planned books, give:
- **Book N: <working title>**
- One-line logline
- Major external arc (what changes in the world)
- Major internal arc (what changes in the protagonist)
- Final image (what the last chapter leaves the reader with)

## Promise Spreadsheet
A bulleted list of major promises:
  - PROMISE → set up in Book X → paid off in Book Y

## Series Antagonist(s)
Who or what is the standing opposition? How does the threat tier escalate
across books?

Use retrieve_corpus to consult craft notes on promises/payoffs and series
structure before writing. Save SERIES_OUTLINE.md by calling write_file.
"""

BOOK_SYSTEM = """You are the Plotter, drafting the chapter-by-chapter outline
for ONE book in a series.

Output a BOOK_OUTLINE.md with this exact structure so a downstream parser can
read it:

# Book {book_n}: <Title>

## Logline
One sentence.

## Three-Act Skeleton
- **Act I (Chapters 1-{act1_end}):** setup, inciting incident, lock-in.
- **Act II (Chapters {act2_start}-{act2_end}):** rising action, midpoint reversal,
  all-is-lost.
- **Act III (Chapters {act3_start}-{n_chapters}):** climax, falling action,
  resolution.

## Major POV Characters
- Name — one-paragraph voice/agenda/wound.

## Chapter Plan

Then, for every chapter from 1 to {n_chapters}, output a block in EXACTLY this format:

## Chapter N — <Title>
- **POV:** <character name>
- **Goal:** <one sentence — what the POV wants>
- **Conflict:** <one sentence — what opposes>
- **Outcome:** <Yes-but / No-and / Yes / No> — <brief>
- **Promises set up:** <comma-separated, or "none">
- **Promises paid off:** <comma-separated, or "none">
- **Beats:**
  1. <action beat>
  2. <action beat>
  3. <action beat>
  4. <action beat>

Constraints:
- Every chapter must have POV, Goal, Conflict, Outcome.
- "Yes-but" and "No-and" outcomes are STRONGLY preferred.
- Vary POVs if multiple are listed.
- The midpoint (around chapter {midpoint}) must be a true reversal.
- Chapter {n_chapters} is the climax/resolution.

Use retrieve_corpus to pull craft notes and style references. Save by calling write_file.
"""


def _series_target_books(project: BookProject) -> int:
    return max(1, project.target_books_in_series)


def run_series(project: BookProject) -> BookProject:
    series_path = Path(project.output_dir) / "SERIES_OUTLINE.md"
    if series_path.exists() and series_path.stat().st_size > 200:
        print("  [Plotter/Series] SERIES_OUTLINE.md already exists — skipping.")
        project.series_outline_path = str(series_path)
        return project

    print("  [Plotter/Series] Designing series arc …")
    world_bible = ""
    wbp = Path(project.world_bible_path) if project.world_bible_path else None
    if wbp and wbp.exists():
        world_bible = wbp.read_text(encoding="utf-8", errors="ignore")

    n_books = _series_target_books(project)
    sys_prompt = SERIES_SYSTEM.format(n_books=n_books)
    user = f"""Project title: {project.title}

WORLD_BIBLE.md:
{world_bible}

Number of books planned: {n_books}

Save the series outline to: {series_path}
"""

    def on_call(name, args):
        if name == "write_file":
            print(f"    [write] {args.get('path','')}")
        else:
            print(f"    [{name}]")

    run_agent(
        system=sys_prompt,
        user=user,
        model=project.judge_model,
        tools=[WRITE_FILE, READ_FILE, LIST_FILES, RETRIEVE_CORPUS],
        handlers={k: HANDLERS[k] for k in
                  ("write_file", "read_file", "list_files", "retrieve_corpus")},
        on_tool_call=on_call,
        temperature=0.5,
        num_ctx=16384,
    )

    if not series_path.exists():
        print("  [Plotter/Series] Tool call missed — fallback generation.")
        body = generate(
            sys_prompt + "\nReturn ONLY the markdown content for SERIES_OUTLINE.md.",
            user, model=project.judge_model, temperature=0.5, num_ctx=16384,
        )
        series_path.write_text(body, encoding="utf-8")

    project.series_outline_path = str(series_path)
    print(f"  [Plotter/Series] Wrote {series_path.name}\n")
    return project


def run_book(project: BookProject, book_n: int) -> BookProject:
    book = project.book(book_n)
    book_dir = project.book_dir(book_n)
    book_dir.mkdir(parents=True, exist_ok=True)
    outline_path = book_dir / "BOOK_OUTLINE.md"

    if outline_path.exists() and outline_path.stat().st_size > 200:
        print(f"  [Plotter/Book {book_n:02d}] Outline already exists — skipping.")
        book.outline_path = str(outline_path)
        project.upsert_book(book)
        return project

    print(f"  [Plotter/Book {book_n:02d}] Designing chapter plan …")

    world_bible = ""
    series_outline = ""
    if project.world_bible_path and Path(project.world_bible_path).exists():
        world_bible = Path(project.world_bible_path).read_text(encoding="utf-8", errors="ignore")
    if project.series_outline_path and Path(project.series_outline_path).exists():
        series_outline = Path(project.series_outline_path).read_text(encoding="utf-8", errors="ignore")

    n = project.target_chapters_per_book
    act1_end   = max(2, n // 4)
    act2_start = act1_end + 1
    act2_end   = max(act2_start + 1, (3 * n) // 4)
    act3_start = act2_end + 1
    midpoint   = n // 2

    sys_prompt = BOOK_SYSTEM.format(
        book_n=book_n, n_chapters=n,
        act1_end=act1_end, act2_start=act2_start,
        act2_end=act2_end, act3_start=act3_start,
        midpoint=midpoint,
    )
    user = f"""Project title: {project.title}
Book number: {book_n}

WORLD_BIBLE.md:
{world_bible}

SERIES_OUTLINE.md:
{series_outline}

Save the outline to: {outline_path}
Plan EXACTLY {n} chapters.
"""

    def on_call(name, args):
        if name == "write_file":
            print(f"    [write] {args.get('path','')}")
        else:
            print(f"    [{name}]")

    run_agent(
        system=sys_prompt,
        user=user,
        model=project.judge_model,
        tools=[WRITE_FILE, READ_FILE, LIST_FILES, RETRIEVE_CORPUS],
        handlers={k: HANDLERS[k] for k in
                  ("write_file", "read_file", "list_files", "retrieve_corpus")},
        on_tool_call=on_call,
        temperature=0.5,
        num_ctx=16384,
        max_rounds=15,
    )

    if not outline_path.exists():
        print(f"  [Plotter/Book {book_n:02d}] Tool call missed — fallback generation.")
        body = generate(
            sys_prompt + "\nReturn ONLY the markdown content for BOOK_OUTLINE.md.",
            user, model=project.judge_model, temperature=0.5, num_ctx=16384,
        )
        outline_path.write_text(body, encoding="utf-8")

    book.outline_path = str(outline_path)
    book.title = _extract_book_title(outline_path)
    book.status = "writing"
    project.upsert_book(book)
    project.save()
    print(f"  [Plotter/Book {book_n:02d}] Wrote {outline_path.name}\n")
    return project


# ── Outline parsing for the Drafter ─────────────────────────────────────

_CHAPTER_HEADER = re.compile(
    r"^##\s+Chapter\s+(\d+)\s*[—\-:]\s*(.+?)\s*$", re.MULTILINE,
)


def _extract_book_title(outline_path: Path) -> str:
    text = outline_path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"^#\s+Book\s+\d+\s*[:\-—]\s*(.+?)\s*$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def parse_chapters(outline_path: Path) -> list[dict]:
    text = outline_path.read_text(encoding="utf-8", errors="ignore")
    matches = list(_CHAPTER_HEADER.finditer(text))
    chapters = []
    for i, m in enumerate(matches):
        n = int(m.group(1))
        title = m.group(2).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        chapters.append({"number": n, "title": title, "body": body})
    return chapters
