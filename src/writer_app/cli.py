#!/usr/bin/env python3
"""
writer — multi-agent local fantasy novel writer.

Workflow:
  1. writer init "My Series Title"
  2. writer corpus
  3. drop your bible files into ~/books/<slug>/bible/
  4. writer start ~/books/<slug>
  5. writer export ~/books/<slug>
  6. writer disclosure ~/books/<slug>
"""

import argparse
import json
import re
import sys
from pathlib import Path

from .shared.memory  import BookProject
from .shared.llm     import resolve_models, OllamaUnreachableError
from .shared         import corpus as corpus_mod
from .shared         import remote as remote_mod
from . import provenance as provenance_mod
from . import export as export_mod
from . import humanizer as humanizer_mod
from . import orchestrator


BOOKS_ROOT = Path.home() / "books"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())
    return slug.strip("-")[:60] or "untitled"


def _project_path(path_or_slug: str) -> Path:
    p = Path(path_or_slug).expanduser()
    if p.exists():
        return p
    candidate = BOOKS_ROOT / path_or_slug
    if candidate.exists():
        return candidate
    return p


# ── init ──────────────────────────────────────────────────────────────────

def cmd_init(args):
    title = " ".join(args.title).strip()
    if not title:
        print("Provide a title: writer init \"My Series Title\"")
        sys.exit(2)

    out_dir = Path(args.out).expanduser() if args.out else BOOKS_ROOT / _slugify(title)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bible").mkdir(exist_ok=True)

    if (out_dir / "STATE.json").exists():
        print(f"Project already exists at {out_dir}.")
        print("Run `writer status <path>` to see progress, or `writer start <path>` to resume.")
        return

    project = BookProject(
        title=title,
        output_dir=out_dir,
        target_books_in_series=args.books,
        target_chapters_per_book=args.chapters,
        target_words_per_chapter=args.words,
        min_chapter_score=args.threshold,
        max_revisions_per_chapter=args.max_revisions,
        humanize=not args.no_humanize,
        humanizer_target=args.humanizer_target,
        humanizer_max_passes=args.humanizer_passes,
        author_name=args.author or "",
        author_pen_name=args.pen_name or "",
    )
    project.save()

    (out_dir / "bible" / "README.md").write_text(
        "# Your Bible\n\n"
        "Drop any worldbuilding, character, magic, geography, faction, or plot\n"
        "notes here as `.md` or `.txt` files. The Loremaster will read every\n"
        "file in this folder and consolidate them into WORLD_BIBLE.md.\n\n"
        "Suggested files (none are required — provide what you have):\n"
        "- `world.md` — geography, climate, history\n"
        "- `magic.md` — power system, costs, rules, failure modes\n"
        "- `characters.md` — major characters, their wounds and drives\n"
        "- `factions.md` — political and cultural groups\n"
        "- `plot.md` — anything you already know about where the story goes\n",
        encoding="utf-8",
    )

    print(f"\nInitialised: {out_dir}")
    print(f"  Title    : {title}")
    print(f"  Books    : {project.target_books_in_series}")
    print(f"  Chapters : {project.target_chapters_per_book} per book")
    print(f"  Words    : ~{project.target_words_per_chapter:,} per chapter")
    print(f"  Quality  : score ≥ {project.min_chapter_score} "
          f"(up to {project.max_revisions_per_chapter} revisions)")
    print(f"\nNext:")
    print(f"  1. Drop your bible files into {out_dir / 'bible'}/")
    print(f"  2. Make sure corpus is built:  writer corpus")
    print(f"  3. Start writing:              writer start {out_dir}")


# ── corpus ────────────────────────────────────────────────────────────────

def cmd_corpus(args):
    if args.list:
        corpus_mod.list_corpus()
        return
    corpus_mod.build_all(gutenberg=not args.no_gutenberg)


# ── start ─────────────────────────────────────────────────────────────────

def _check_models(project: BookProject):
    draft, judge = resolve_models()
    print(f"  local  draft : {draft}")
    print(f"  local  judge : {judge}")
    if draft == judge:
        print("\n  Note: draft and judge local models are the same. For best local prose,")
        print("        pull a 12B-class general model:")
        print("          ollama pull mistral-nemo:12b")
        print("          export WRITER_DRAFT_MODEL=mistral-nemo:12b")


def _print_routing(force_local: bool):
    if force_local:
        print("  routing: --local-only set, ALL calls use Ollama locally.")
        return
    online = remote_mod.internet_available()
    print(f"  internet: {'available' if online else 'offline (remote disabled this run)'}")
    routing = remote_mod.describe_routing()
    for role in ("draft", "judge"):
        info = routing[role]
        if info["provider"] == "local":
            cfg = info.get("configured", "local")
            extra = ""
            if cfg != "local":
                key_state = "set" if info.get("key_set") else "MISSING"
                extra = f"  (configured={cfg}, API key {key_state})"
            print(f"  {role:5s} role → local Ollama{extra}")
        else:
            print(f"  {role:5s} role → REMOTE  {info['provider']:8s}  model={info['model']}")
            print(f"                       ToS: {info['tos_url']}")
            print(f"                   Privacy: {info['privacy_url']}")


def cmd_start(args):
    path = _project_path(args.path)
    if not (path / "STATE.json").exists():
        print(f"No project at {path}. Run `writer init \"Title\"` first.")
        sys.exit(2)

    project = BookProject.load(path)
    if args.chapters:      project.target_chapters_per_book = args.chapters
    if args.words:         project.target_words_per_chapter = args.words
    if args.threshold is not None:     project.min_chapter_score = args.threshold
    if args.max_revisions is not None: project.max_revisions_per_chapter = args.max_revisions
    if args.books:         project.target_books_in_series = args.books
    project.save()

    remote_mod.reset_circuit_breaker()
    remote_mod.set_force_local(bool(args.local_only))

    print(f"\n{'='*60}")
    print(f"  Writer: {project.title}")
    print(f"  Path  : {project.output_dir}")
    print(f"  Books : {project.target_books_in_series}, "
          f"Chapters: {project.target_chapters_per_book}, "
          f"Target words: {project.target_words_per_chapter}")
    print(f"{'='*60}\n")
    print("Models in use:")
    _check_models(project)
    print("Routing:")
    _print_routing(bool(args.local_only))

    # Ensure corpus exists
    if not (corpus_mod.CORPUS_DIR / "style_cards").exists() \
            or not (corpus_mod.CORPUS_DIR / "craft").exists():
        print("\nCorpus not built yet. Writing style cards + craft notes (fast) …")
        corpus_mod.build_style_cards()
        corpus_mod.build_craft_notes()
        print("Skipping Gutenberg download. Run `writer corpus` later to add it.")

    orchestrator.run(project)
    print(project.summary())


# ── status ────────────────────────────────────────────────────────────────

def cmd_status(args):
    path = _project_path(args.path)
    if not (path / "STATE.json").exists():
        print(f"No project at {path}.")
        sys.exit(2)
    project = BookProject.load(path)
    print(project.summary())

    for b in project.books:
        print(f"\nBook {b['number']:02d}: {b.get('title') or '(untitled)'} — {b['status']}")
        if not b["chapters"]:
            print("  (no chapters yet)")
            continue
        for ch in sorted(b["chapters"], key=lambda c: c["number"]):
            score = f"{ch['score']:.2f}" if ch.get("score") else "  —  "
            print(f"  Ch {ch['number']:02d}  [{ch['status']:8s}]  score {score}  "
                  f"iters {ch.get('iterations',0)}  {ch.get('title','')}")


# ── config ────────────────────────────────────────────────────────────────

def cmd_config(args):
    path = _project_path(args.path)
    if not (path / "STATE.json").exists():
        print(f"No project at {path}.")
        sys.exit(2)
    project = BookProject.load(path)
    changed = False
    if args.chapters is not None:        project.target_chapters_per_book = args.chapters; changed = True
    if args.words is not None:           project.target_words_per_chapter = args.words; changed = True
    if args.threshold is not None:       project.min_chapter_score = args.threshold; changed = True
    if args.max_revisions is not None:   project.max_revisions_per_chapter = args.max_revisions; changed = True
    if args.books is not None:           project.target_books_in_series = args.books; changed = True
    if args.humanizer_target is not None: project.humanizer_target = args.humanizer_target; changed = True
    if args.humanizer_passes is not None: project.humanizer_max_passes = args.humanizer_passes; changed = True
    if args.humanize is not None:        project.humanize = args.humanize; changed = True
    if args.author is not None:          project.author_name = args.author; changed = True
    if args.pen_name is not None:        project.author_pen_name = args.pen_name; changed = True

    if not changed:
        print(json.dumps({
            "title":               project.title,
            "author_name":         project.author_name,
            "author_pen_name":     project.author_pen_name,
            "target_books":        project.target_books_in_series,
            "chapters_per_book":   project.target_chapters_per_book,
            "words_per_chapter":   project.target_words_per_chapter,
            "min_chapter_score":   project.min_chapter_score,
            "max_revisions":       project.max_revisions_per_chapter,
            "humanize":            project.humanize,
            "humanizer_target":    project.humanizer_target,
            "humanizer_passes":    project.humanizer_max_passes,
        }, indent=2))
        return

    project.save()
    print(f"Updated config for {project.title}.")


# ── export ────────────────────────────────────────────────────────────────

def cmd_export(args):
    path = _project_path(args.path)
    if not (path / "STATE.json").exists():
        print(f"No project at {path}.")
        sys.exit(2)
    project = BookProject.load(path)
    formats = args.formats or ["docx", "epub"]
    books = [args.book] if args.book else sorted({b["number"] for b in project.books})
    if not books:
        print("No books to export — has the pipeline produced any chapters yet?")
        sys.exit(2)
    for n in books:
        print(f"\n── Exporting Book {n:02d} ──")
        out_paths = export_mod.export_book(project, n, formats)
        for p in out_paths:
            print(f"  wrote {p}  ({p.stat().st_size:,} bytes)")


# ── disclosure ────────────────────────────────────────────────────────────

def cmd_disclosure(args):
    path = _project_path(args.path)
    if not (path / "STATE.json").exists():
        print(f"No project at {path}.")
        sys.exit(2)
    project = BookProject.load(path)
    out = provenance_mod.write_disclosure(project)
    print(out.read_text(encoding="utf-8"))


# ── providers ─────────────────────────────────────────────────────────────

def cmd_providers(args):
    print()
    online = remote_mod.internet_available()
    print(f"  Internet: {'available' if online else 'OFFLINE'}")
    print()
    print("  Local (Ollama):")
    try:
        draft, judge = resolve_models()
        print(f"    draft model: {draft}")
        print(f"    judge model: {judge}")
    except Exception as e:
        print(f"    (Ollama unreachable: {e})")
    print()
    print("  Remote routing (per role, from env vars):")
    routing = remote_mod.describe_routing()
    for role in ("draft", "judge"):
        info = routing[role]
        if info["provider"] == "local":
            cfg = info.get("configured", "local")
            key_state = "set" if info.get("key_set") else "missing"
            if cfg == "local":
                print(f"    {role:5s}: local (WRITER_{role.upper()}_PROVIDER unset)")
            else:
                print(f"    {role:5s}: local — provider {cfg} configured but API key {key_state}")
        else:
            print(f"    {role:5s}: REMOTE → {info['provider']} ({info['model']})")
            print(f"         ToS:     {info['tos_url']}")
            print(f"         Privacy: {info['privacy_url']}")
    print()
    print("  To enable a remote provider, set env vars (no card required for")
    print("  Groq or Cerebras free tiers — verify current ToS):")
    print("    export GROQ_API_KEY='gsk_...'      # https://console.groq.com")
    print("    export CEREBRAS_API_KEY='csk-...'  # https://cloud.cerebras.ai")
    print("    export WRITER_DRAFT_PROVIDER=groq")
    print("    export WRITER_JUDGE_PROVIDER=local")
    print()


# ── humanize ──────────────────────────────────────────────────────────────

def cmd_humanize(args):
    path = _project_path(args.path)
    if not (path / "STATE.json").exists():
        print(f"No project at {path}.")
        sys.exit(2)
    project = BookProject.load(path)
    project.draft_model, project.judge_model = resolve_models()

    target = Path(args.chapter_file).expanduser()
    if not target.exists():
        print(f"Chapter file not found: {target}")
        sys.exit(2)
    text = target.read_text(encoding="utf-8")
    result = humanizer_mod.run(
        project, text,
        max_passes=args.passes,
        ai_score_target=args.target,
        use_llm_detector=not args.no_llm,
    )
    if args.write:
        target.write_text(result["text"], encoding="utf-8")
        print(f"\nRewrote {target} in place.")
    else:
        out = target.with_suffix(".humanized.md")
        out.write_text(result["text"], encoding="utf-8")
        print(f"\nWrote rewrite to {out}")
    print(f"AI score: {result['ai_score_before']} → {result['ai_score_after']}  "
          f"(LLM: {result['llm_score_before']} → {result['llm_score_after']})  "
          f"after {result['passes']} pass(es).")


# ── ui (launch Streamlit) ────────────────────────────────────────────────

def cmd_ui(args):
    """Launch the Streamlit interactive UI."""
    import shutil, subprocess
    if shutil.which("streamlit") is None:
        print("Streamlit is not installed.")
        print("Install with: pip install 'writer-app[ui]'  (or: pip install streamlit)")
        sys.exit(2)
    # The UI lives at <repo>/ui/app.py for dev installs; for packaged installs
    # it's bundled at writer_app/_ui/app.py. Try both.
    candidates = [
        Path(__file__).resolve().parents[2] / "ui" / "app.py",      # dev layout
        Path(__file__).resolve().parent / "_ui" / "app.py",         # packaged
    ]
    ui_path = next((p for p in candidates if p.exists()), None)
    if ui_path is None:
        print("Could not find the UI file (ui/app.py). Reinstall writer-app or run from a checkout.")
        sys.exit(2)
    print(f"Launching Streamlit UI from {ui_path}")
    subprocess.run(["streamlit", "run", str(ui_path)] + list(args.streamlit_args or []))


# ── main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="writer",
        description="Multi-agent local fantasy novel writer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Initialise a new book/series project.")
    p_init.add_argument("title", nargs="+")
    p_init.add_argument("--out", "-o")
    p_init.add_argument("--books", type=int, default=1)
    p_init.add_argument("--chapters", type=int, default=30)
    p_init.add_argument("--words", type=int, default=3000)
    p_init.add_argument("--threshold", type=float, default=7.5)
    p_init.add_argument("--max-revisions", type=int, default=3)
    p_init.add_argument("--no-humanize", action="store_true")
    p_init.add_argument("--humanizer-target", type=float, default=3.5)
    p_init.add_argument("--humanizer-passes", type=int, default=2)
    p_init.add_argument("--author")
    p_init.add_argument("--pen-name")
    p_init.set_defaults(func=cmd_init)

    p_corpus = sub.add_parser("corpus", help="Build or list the reference corpus.")
    p_corpus.add_argument("--list", action="store_true")
    p_corpus.add_argument("--no-gutenberg", action="store_true")
    p_corpus.set_defaults(func=cmd_corpus)

    p_start = sub.add_parser("start", help="Start (or resume) writing.")
    p_start.add_argument("path")
    p_start.add_argument("--chapters",      type=int)
    p_start.add_argument("--words",         type=int)
    p_start.add_argument("--threshold",     type=float)
    p_start.add_argument("--max-revisions", type=int)
    p_start.add_argument("--books",         type=int)
    p_start.add_argument("--local-only", action="store_true",
                         help="Disable remote providers for this run.")
    p_start.set_defaults(func=cmd_start)

    p_status = sub.add_parser("status", help="Show progress on a project.")
    p_status.add_argument("path")
    p_status.set_defaults(func=cmd_status)

    p_config = sub.add_parser("config", help="View or change project config.")
    p_config.add_argument("path")
    p_config.add_argument("--chapters",         type=int)
    p_config.add_argument("--words",            type=int)
    p_config.add_argument("--threshold",        type=float)
    p_config.add_argument("--max-revisions",    type=int)
    p_config.add_argument("--books",            type=int)
    p_config.add_argument("--humanizer-target", type=float)
    p_config.add_argument("--humanizer-passes", type=int)
    p_config.add_argument("--humanize", type=lambda s: s.lower() in ("y","yes","true","1"))
    p_config.add_argument("--author")
    p_config.add_argument("--pen-name")
    p_config.set_defaults(func=cmd_config)

    p_export = sub.add_parser("export", help="Export book(s) to .docx and .epub.")
    p_export.add_argument("path")
    p_export.add_argument("--book", type=int)
    p_export.add_argument("--formats", nargs="*")
    p_export.set_defaults(func=cmd_export)

    p_disc = sub.add_parser("disclosure", help="Write and print KDP AI disclosure answers.")
    p_disc.add_argument("path")
    p_disc.set_defaults(func=cmd_disclosure)

    p_prov = sub.add_parser("providers",
        help="Show LLM routing config (local + remote) and reachability.")
    p_prov.set_defaults(func=cmd_providers)

    p_hum = sub.add_parser("humanize", help="Re-run humanizer on one chapter file.")
    p_hum.add_argument("path")
    p_hum.add_argument("chapter_file")
    p_hum.add_argument("--passes", type=int, default=2)
    p_hum.add_argument("--target", type=float, default=3.5)
    p_hum.add_argument("--write", action="store_true")
    p_hum.add_argument("--no-llm", action="store_true")
    p_hum.set_defaults(func=cmd_humanize)

    p_ui = sub.add_parser("ui", help="Launch the interactive Streamlit UI.")
    p_ui.add_argument("streamlit_args", nargs="*",
                      help="Extra args passed to streamlit run.")
    p_ui.set_defaults(func=cmd_ui)

    args = parser.parse_args()
    try:
        args.func(args)
    except OllamaUnreachableError as e:
        print(f"writer: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
