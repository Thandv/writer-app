"""
Writer Orchestrator

Stages:
  1. Loremaster         — consolidate bible → WORLD_BIBLE.md
  2. Plotter (series)   — SERIES_OUTLINE.md (if multi-book)
  3. Plotter (book N)   — BOOK_OUTLINE.md with chapter beats
  4. For each chapter:
       a. Drafter writes v1
       b. Humanizer detects + rewrites AI-tells
       c. Reader + Critic panels score
       d. If below threshold and under cap: Reviser → humanize → score again
       e. Save best draft to chapter-NN/final.md
  5. Continuity check   — CONTINUITY_REPORT.md per book
  6. Provenance pass    — PROVENANCE.md per book
  7. Assemble           — MANUSCRIPT.md (revisions/ overrides applied)
"""

import json
import time
from datetime import datetime
from pathlib import Path

from .shared.memory  import BookProject, ChapterState
from .shared         import llm
from .shared.rubric  import CRITIC_RUBRIC, READER_RUBRIC, weighted_average
from . import (
    loremaster, plotter, drafter, reader_panel, critic_panel,
    reviser, continuity, humanizer, provenance,
)


def _header(title: str):
    bar = "─" * 58
    print(f"\n{bar}\n  {title}\n{bar}")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _save_chapter_artifacts(ch_dir: Path, iteration: int,
                            draft_text: str,
                            reader_result: dict,
                            critic_result: dict,
                            humanize_result: dict = None,
                            pre_humanize_text: str = None):
    ch_dir.mkdir(parents=True, exist_ok=True)
    (ch_dir / f"v{iteration}.md").write_text(draft_text, encoding="utf-8")
    (ch_dir / f"v{iteration}_reader.json").write_text(
        json.dumps(reader_result, indent=2), encoding="utf-8")
    (ch_dir / f"v{iteration}_critic.json").write_text(
        json.dumps(critic_result, indent=2), encoding="utf-8")
    (ch_dir / f"v{iteration}_reader.md").write_text(
        reader_panel.render_markdown(reader_result), encoding="utf-8")
    (ch_dir / f"v{iteration}_critic.md").write_text(
        critic_panel.render_markdown(critic_result), encoding="utf-8")
    if humanize_result is not None:
        report = {k: v for k, v in humanize_result.items() if k != "text"}
        (ch_dir / f"v{iteration}_humanizer.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
    if pre_humanize_text is not None and pre_humanize_text != draft_text:
        (ch_dir / f"v{iteration}_raw.md").write_text(pre_humanize_text, encoding="utf-8")


def _previous_chapter_text(project: BookProject, book_n: int, chapter_n: int) -> str:
    if chapter_n <= 1:
        return ""
    user_rev = project.book_dir(book_n) / "revisions" / f"chapter-{chapter_n - 1:02d}.md"
    if user_rev.exists():
        return user_rev.read_text(encoding="utf-8", errors="ignore")
    prev_final = project.chapter_dir(book_n, chapter_n - 1) / "final.md"
    return _read_text(prev_final)


def _user_revision_path(project: BookProject, book_n: int, chapter_n: int) -> Path:
    return project.book_dir(book_n) / "revisions" / f"chapter-{chapter_n:02d}.md"


def _run_chapter(project: BookProject, book_n: int, chapter: dict) -> ChapterState:
    n          = chapter["number"]
    title      = chapter["title"]
    beat_body  = chapter["body"]
    ch_dir     = project.chapter_dir(book_n, n)
    final_path = ch_dir / "final.md"

    book = project.book(book_n)
    state = book.chapter(n)
    state.number = n
    state.title  = title

    if final_path.exists() and state.status == "done":
        print(f"  [Ch {n:02d}] already finalised — skipping.")
        return state

    prev_text = _previous_chapter_text(project, book_n, n)
    threshold = project.min_chapter_score
    max_iters = project.max_revisions_per_chapter

    best_text  = ""
    best_score = -1.0
    best_iter  = 0
    best_humanize_result = None
    revision_note = ""

    for iteration in range(1, max_iters + 2):
        is_revision = iteration > 1
        state.status = "revising" if is_revision else "drafting"
        state.iterations = iteration
        state.drafted_at = datetime.now().isoformat()
        state.draft_model_used = project.draft_model
        state.judge_model_used = project.judge_model
        book.upsert_chapter(state)
        project.upsert_book(book)
        project.save()

        raw_draft = (
            reviser.revise(project, book_n, n, title, beat_body, prev_text, revision_note)
            if is_revision
            else drafter.run(project, book_n, n, title, beat_body,
                             previous_chapter_text=prev_text)
        )

        humanize_result = None
        chapter_text = raw_draft
        if project.humanize:
            humanize_result = humanizer.run(
                project, raw_draft,
                max_passes=project.humanizer_max_passes,
                ai_score_target=project.humanizer_target,
            )
            chapter_text = humanize_result["text"]
            state.humanizer_passes    = humanize_result["passes"]
            state.ai_score_before     = humanize_result["ai_score_before"]
            state.ai_score_after      = humanize_result["ai_score_after"]
            state.llm_ai_score_before = humanize_result["llm_score_before"]
            state.llm_ai_score_after  = humanize_result["llm_score_after"]

        reader_result = reader_panel.run(project, chapter_text)
        critic_result = critic_panel.run(project, chapter_text, beat_body)

        combined = round(
            (1.0 * critic_result["average_score"] + 0.9 * reader_result["average_score"])
            / 1.9, 2,
        )

        _save_chapter_artifacts(
            ch_dir, iteration, chapter_text, reader_result, critic_result,
            humanize_result=humanize_result, pre_humanize_text=raw_draft,
        )
        ai_after = humanize_result["ai_score_after"] if humanize_result else None
        ai_str = f"  ai={ai_after}" if ai_after is not None else ""
        print(f"  [Ch {n:02d}] v{iteration}: combined score {combined}  "
              f"(critic {critic_result['average_score']}, "
              f"reader {reader_result['average_score']}){ai_str}")

        if combined > best_score:
            best_score, best_text, best_iter = combined, chapter_text, iteration
            best_humanize_result = humanize_result

        if combined >= threshold:
            print(f"  [Ch {n:02d}] reached threshold ({threshold}) at v{iteration}.")
            break
        if iteration > max_iters:
            print(f"  [Ch {n:02d}] hit revision cap ({max_iters}); keeping best draft "
                  f"(v{best_iter}, score {best_score}).")
            break

        revision_note = critic_panel.build_revision_note(reader_result, critic_result)

    final_path.write_text(best_text, encoding="utf-8")
    state.status = "done"
    state.score  = best_score
    state.final_path = str(final_path)
    if best_humanize_result is not None:
        state.humanizer_passes    = best_humanize_result["passes"]
        state.ai_score_before     = best_humanize_result["ai_score_before"]
        state.ai_score_after      = best_humanize_result["ai_score_after"]
        state.llm_ai_score_before = best_humanize_result["llm_score_before"]
        state.llm_ai_score_after  = best_humanize_result["llm_score_after"]
    if _user_revision_path(project, book_n, n).exists():
        state.user_revised = True
    book.upsert_chapter(state)
    project.upsert_book(book)
    project.save()
    print(f"  [Ch {n:02d}] FINAL → {final_path.name}  (v{best_iter}, score {best_score})")
    return state


def _assemble_manuscript(project: BookProject, book_n: int):
    book = project.book(book_n)
    parts = [f"# {book.title or f'Book {book_n}'}\n"]
    revisions_dir = project.book_dir(book_n) / "revisions"
    user_revised_chapters = []
    for ch in sorted(book.chapters, key=lambda c: c["number"]):
        n = ch["number"]
        user_rev = revisions_dir / f"chapter-{n:02d}.md"
        if user_rev.exists():
            source = user_rev
            user_revised_chapters.append(n)
        else:
            source = project.chapter_dir(book_n, n) / "final.md"
        if not source.exists():
            continue
        parts.append(f"\n\n## Chapter {n} — {ch.get('title','')}\n")
        parts.append(source.read_text(encoding="utf-8"))
    out = project.book_dir(book_n) / "MANUSCRIPT.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    rev_note = f"  (used user revisions for chapters: {user_revised_chapters})" \
        if user_revised_chapters else ""
    print(f"  Assembled → {out}{rev_note}")


def _run_book(project: BookProject, book_n: int) -> BookProject:
    _header(f"Book {book_n:02d} — Plotting")
    plotter.run_book(project, book_n)

    book = project.book(book_n)
    chapters = plotter.parse_chapters(Path(book.outline_path))
    if not chapters:
        print(f"  [Book {book_n:02d}] outline parsed 0 chapters — aborting.")
        return project

    for ch in chapters:
        st = book.chapter(ch["number"])
        st.number = ch["number"]
        st.title  = ch["title"]
        if st.status not in ("done",):
            st.status = "pending"
        book.upsert_chapter(st)
    project.upsert_book(book)
    project.save()

    _header(f"Book {book_n:02d} — Writing {len(chapters)} chapters")
    for ch in chapters:
        st = book.chapter(ch["number"])
        if st.status == "done":
            continue
        t0 = time.time()
        _run_chapter(project, book_n, ch)
        print(f"  [Ch {ch['number']:02d}] done in {(time.time()-t0)/60:.1f}m\n")
        book = project.book(book_n)

    _header(f"Book {book_n:02d} — Continuity Pass")
    continuity.run(project, book_n)

    _header(f"Book {book_n:02d} — Provenance Pass")
    provenance.write_book_provenance(project, book_n)

    _header(f"Book {book_n:02d} — Assembling MANUSCRIPT.md")
    _assemble_manuscript(project, book_n)

    book = project.book(book_n)
    book.status = "done"
    project.upsert_book(book)
    project.save()
    return project


def run(project: BookProject) -> BookProject:
    draft_model, judge_model = llm.resolve_models()
    project.draft_model = draft_model
    project.judge_model = judge_model
    print(f"\nLocal models: draft={draft_model}  judge={judge_model}")

    wbp = Path(project.output_dir) / "WORLD_BIBLE.md"
    if wbp.exists() and wbp.stat().st_size > 500:
        print(f"\n[Loremaster] {wbp.name} exists — skipping.")
        project.world_bible_path = str(wbp)
    else:
        _header("Loremaster")
        loremaster.run(project)

    if project.target_books_in_series > 1:
        _header("Plotter — Series Arc")
        plotter.run_series(project)
    else:
        sop = Path(project.output_dir) / "SERIES_OUTLINE.md"
        if sop.exists():
            project.series_outline_path = str(sop)

    project.save()

    for book_n in range(1, project.target_books_in_series + 1):
        b = project.book(book_n)
        if b.status == "done":
            print(f"\n[Book {book_n:02d}] already done — skipping.")
            continue
        _run_book(project, book_n)

    project.stage = "done"
    project.save()
    return project
