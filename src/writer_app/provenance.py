"""
Provenance Module — writes PROVENANCE.md and KDP_DISCLOSURE.md.
"""

from datetime import datetime
from pathlib import Path
from .shared.memory import BookProject


KDP_DISCLOSURE_TEMPLATE = """\
# KDP AI Disclosure Answer

When Amazon's KDP submission flow asks about AI use, answer as follows.

## Did AI generate the text content?
**Yes — AI-generated text.**

KDP defines "AI-generated" as text *created* by an AI tool (even if you then
refined it). The pipeline used here drafts each chapter with an AI model;
even where you later revised, the underlying draft was AI-generated. Choose
**AI-generated** in the disclosure form, not "AI-assisted".

## Did AI generate the cover?
**Answer based on what you did.** This pipeline does not produce a cover.
If you generated the cover with an AI tool without substantial human
modification, answer **yes**. If a human artist made the cover, answer **no**.

## Did AI generate the translation (if applicable)?
Answer based on what you did. This pipeline does not produce translations.

## Important
- KDP's disclosure is **internal**. It does not appear on your book's product page.
- Failing to disclose is a Terms of Service violation. Disclosure is cheap insurance.
- Disclosure does NOT prevent you from publishing or earning royalties.
"""


def build_kdp_disclosure(project: BookProject) -> str:
    return KDP_DISCLOSURE_TEMPLATE


def _chapter_row(ch: dict) -> str:
    n        = ch.get("number", "?")
    title    = ch.get("title", "")
    score    = ch.get("score", 0.0) or 0.0
    iters    = ch.get("iterations", 0)
    drafted  = ch.get("drafted_at", "") or "—"
    if drafted and drafted != "—":
        drafted = drafted.split("T")[0]
    draft_m  = ch.get("draft_model_used", "") or "—"
    judge_m  = ch.get("judge_model_used", "") or "—"
    h_passes = ch.get("humanizer_passes", 0)
    ai_b     = ch.get("ai_score_before", 0.0)
    ai_a     = ch.get("ai_score_after", 0.0)
    user_rev = "yes" if ch.get("user_revised") else "no"
    return (
        f"| {n:02d} | {title[:40]:40s} | {drafted} | {draft_m:20s} | "
        f"{judge_m:14s} | {iters} | {score:.2f} | {h_passes} | "
        f"{ai_b:.1f}→{ai_a:.1f} | {user_rev} |"
    )


def write_book_provenance(project: BookProject, book_n: int) -> Path:
    book = project.book(book_n)
    book_dir = project.book_dir(book_n)
    book_dir.mkdir(parents=True, exist_ok=True)

    author = project.author_pen_name or project.author_name or "(author name not set)"
    real_name = project.author_name or "(real name not set)"
    n_chapters = len(book.chapters)
    n_user_revised = sum(1 for c in book.chapters if c.get("user_revised"))
    bible_files = ", ".join(Path(p).name for p in project.user_bible_files) or "(none)"

    lines = [
        f"# Provenance — {project.title}, Book {book_n}",
        "",
        f"_Generated {datetime.now().isoformat(timespec='seconds')}_",
        "",
        "## Authorship summary",
        "",
        f"- **Series**: {project.title}",
        f"- **Book**:   {book.title or f'Book {book_n}'}",
        f"- **Author (publishing name)**: {author}",
        f"- **Author (real name)**:       {real_name}",
        "",
        "## What is original to the human author",
        "",
        "The following elements were authored by the human author before any AI",
        "involvement and are protected as their original creative work:",
        "",
        "- Plot, story arcs, scene-level decisions where author-authored",
        "- World, geography, history, cultures",
        "- Magic / power system, its rules, costs, and progression",
        "- Named characters and their drives, wounds, and relationships",
        "- Selection, arrangement, and editorial revision of the AI-drafted text",
        "",
        f"Author-supplied bible files: {bible_files}",
        "",
        "## What was AI-generated",
        "",
        "- The chapter-by-chapter outline (Plotter agent, judge model)",
        "- The prose of each chapter (Drafter and Reviser agents, draft model)",
        "- Style detection and AI-tell rewriting (Humanizer agent)",
        "",
        "Per US Copyright Office guidance (post-Zarya 2023), the AI-generated",
        "prose itself is not copyrightable. The human-authored elements above",
        "remain protected as the author's original work.",
        "",
        "## Per-chapter audit",
        "",
        "| #  | Title                                    | Drafted    | Draft model          | Judge model    | Iters | Score | Hum passes | AI score | User rev |",
        "|----|------------------------------------------|------------|----------------------|----------------|-------|-------|------------|----------|----------|",
    ]
    for ch in sorted(book.chapters, key=lambda c: c["number"]):
        lines.append(_chapter_row(ch))
    lines += [
        "",
        f"- Total chapters: {n_chapters}",
        f"- Chapters with user revision file: {n_user_revised}",
        "",
        "## KDP disclosure summary",
        "",
        "When submitting to Amazon KDP, answer **yes** to the AI-generated text",
        "question. See `KDP_DISCLOSURE.md` for the full answer.",
        "",
        "## Models used",
        "",
        f"- Draft model: `{project.draft_model or '(varied)'}`",
        f"- Judge model: `{project.judge_model or '(varied)'}`",
        "",
        "## Pipeline config",
        "",
        f"- Target chapters per book:  {project.target_chapters_per_book}",
        f"- Target words per chapter:  {project.target_words_per_chapter}",
        f"- Chapter pass threshold:    {project.min_chapter_score}",
        f"- Max revisions per chapter: {project.max_revisions_per_chapter}",
        f"- Humanizer enabled:         {project.humanize}",
        f"- Humanizer score target:    {project.humanizer_target}",
        f"- Humanizer max passes:      {project.humanizer_max_passes}",
        "",
    ]

    out = book_dir / "PROVENANCE.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Provenance → {out}")
    return out


def write_disclosure(project: BookProject) -> Path:
    out = Path(project.output_dir) / "KDP_DISCLOSURE.md"
    out.write_text(build_kdp_disclosure(project), encoding="utf-8")
    print(f"  KDP disclosure → {out}")
    return out
