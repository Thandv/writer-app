"""
Streamlit UI for writer-app.

Run with:
  writer ui
  # or directly:
  streamlit run ui/app.py

Every input has an inline hint. Tabs cover the full workflow: setup,
bible upload, write (live progress), chapter inspection/revision, export,
and help.

The UI is a thin shell over the CLI — anything you can do here you can
also do with `writer ...` commands. On-disk artefacts are identical.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

# Ensure src/ is on path when running from a dev checkout (`streamlit run ui/app.py`)
_REPO_ROOT = Path(__file__).resolve().parent.parent
if (_REPO_ROOT / "src").exists():
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from writer_app.shared.memory import BookProject, BookState
from writer_app.shared.llm    import (
    resolve_models, ModelUnavailableError, OllamaUnreachableError,
)
from writer_app.shared        import remote as remote_mod
from writer_app.shared.keys   import load_keys, save_keys
from writer_app.shared        import corpus as corpus_mod
from writer_app               import (
    provenance as provenance_mod,
    export     as export_mod,
    humanizer  as humanizer_mod,
)


BOOKS_ROOT = Path.home() / "books"

st.set_page_config(
    page_title="writer-app",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())
    return slug.strip("-")[:60] or "untitled"


def _list_projects() -> list[Path]:
    if not BOOKS_ROOT.exists():
        return []
    return sorted(p for p in BOOKS_ROOT.iterdir()
                  if p.is_dir() and (p / "STATE.json").exists())


def _load_project(path: Path) -> BookProject | None:
    if not path or not (path / "STATE.json").exists():
        return None
    try:
        return BookProject.load(path)
    except Exception as e:
        st.error(f"Could not load project at {path}: {e}")
        return None


def _save_env_file(project: BookProject, keys: dict):
    """Persist provider settings/API keys to the project's .env (owner-only,
    0600; see writer_app.shared.keys) and apply them to this process."""
    if not keys:
        return
    save_keys(project.output_dir, keys)
    for k, v in keys.items():
        if v:
            os.environ[k] = v


def _load_env_file(project: BookProject):
    """Hydrate process env from project's .env (called on project load)."""
    os.environ.update(load_keys(project.output_dir))


def _running_state() -> dict:
    return st.session_state.setdefault("run", {
        "process": None, "log": "", "started_at": None,
    })


# ── Session state ────────────────────────────────────────────────────────

if "selected_project" not in st.session_state:
    st.session_state.selected_project = None
if "selected_chapter" not in st.session_state:
    st.session_state.selected_chapter = None


# ── Sidebar ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📜 writer-app")
    st.caption("Multi-agent local fantasy novel writer")

    projects = _list_projects()
    options = ["+ New project"] + [p.name for p in projects]
    default_idx = 0
    if st.session_state.selected_project:
        try:
            default_idx = options.index(Path(st.session_state.selected_project).name)
        except ValueError:
            pass

    choice = st.selectbox("Project", options, index=default_idx)

    if choice == "+ New project":
        st.session_state.selected_project = None
        project = None
    else:
        idx = options.index(choice) - 1
        st.session_state.selected_project = str(projects[idx])
        project = _load_project(projects[idx])
        if project:
            _load_env_file(project)

    st.divider()

    # Provider status
    st.markdown("### Providers")
    online = remote_mod.internet_available()
    st.markdown(f"- Internet: {'🟢 online' if online else '🔴 offline'}")
    try:
        draft_local, judge_local = resolve_models()
        st.markdown(f"- Ollama (local): 🟢")
        st.caption(f"draft: `{draft_local}` · judge: `{judge_local}`")
    except (OllamaUnreachableError, ModelUnavailableError) as e:
        st.markdown("- Ollama (local): 🔴")
        st.caption(str(e))

    routing = remote_mod.describe_routing()
    for role in ("draft", "judge"):
        info = routing[role]
        if info["provider"] == "local":
            st.markdown(f"- {role.title()} role: local")
        else:
            st.markdown(f"- {role.title()} role: 🟢 **{info['provider']}** (`{info['model']}`)")

    st.divider()
    st.caption("[Docs](https://github.com/Thandv/writer-app/tree/main/docs) · "
               "[Issues](https://github.com/Thandv/writer-app/issues)")


# ── Main: New project mode ───────────────────────────────────────────────

if project is None:
    st.title("Create a new project")
    st.caption("Each project lives at `~/books/<slug>/`. Pick the basics now; "
               "you can change anything later in the Setup tab.")

    with st.form("new_project"):
        title = st.text_input("Series title",
            placeholder="The Bone Empire",
            help="The series title. Used on title pages and as the export filename.")
        author = st.text_input("Author (real name)",
            help="Goes on the copyright page. Used if you register the work with the USCO. "
                 "Not displayed publicly unless you also set it as the pen name.")
        pen_name = st.text_input("Pen name (publishing name)",
            help="Goes on the title page and is publicly visible on Amazon. "
                 "Leave blank to use your real name.")

        col_a, col_b = st.columns(2)
        with col_a:
            chapters = st.number_input("Chapters per book", 1, 100, 30,
                help="Default 30. A shorter book runs faster but feels thinner. "
                     "Most fantasy novels are 25-40 chapters.")
            words = st.number_input("Target words per chapter", 500, 8000, 3000, step=100,
                help="~3000 words = ~12 minutes of reading. Longer chapters take "
                     "more time to generate but read smoother in print.")
            books = st.number_input("Books in series", 1, 12, 1,
                help="Start with 1. Multi-book is supported but the continuity "
                     "checker only works within a single book in v1.")
        with col_b:
            threshold = st.slider("Pass threshold (1-10)", 1.0, 10.0, 7.5, 0.1,
                help="Combined reader+critic score a chapter must reach to pass. "
                     "Lower = faster runs, higher = more revisions per chapter. "
                     "7.5 is a sensible default.")
            max_revisions = st.number_input("Max revisions per chapter", 0, 10, 3,
                help="Cap on redraft attempts before keeping the best version. "
                     "Each revision = one full draft + scoring cycle (~5-15 min).")
            humanize = st.checkbox("Enable AI-tell humanizer", value=True,
                help="Detects and rewrites AI-sounding prose (stock phrases, em-dash "
                     "parentheticals, 'not just X, but Y', filter words). "
                     "Does NOT change KDP's disclosure category.")

        submit = st.form_submit_button("Create project", type="primary")

    if submit and title.strip():
        out_dir = BOOKS_ROOT / _slugify(title)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "bible").mkdir(exist_ok=True)

        new_p = BookProject(
            title=title.strip(),
            output_dir=out_dir,
            target_books_in_series=books,
            target_chapters_per_book=chapters,
            target_words_per_chapter=words,
            min_chapter_score=threshold,
            max_revisions_per_chapter=max_revisions,
            humanize=humanize,
            author_name=author.strip(),
            author_pen_name=pen_name.strip(),
        )
        new_p.save()
        st.success(f"Created {out_dir}. Switch to it from the sidebar.")
        st.session_state.selected_project = str(out_dir)
        time.sleep(1)
        st.rerun()

    st.stop()


# ── Main: existing project ───────────────────────────────────────────────

st.title(project.title)
st.caption(f"`{project.output_dir}` · stage: {project.stage}")

tab_setup, tab_bible, tab_write, tab_chapters, tab_export, tab_help = st.tabs([
    "⚙️ Setup",
    "📖 Bible",
    "▶️ Write",
    "🔍 Chapters",
    "📦 Export",
    "❓ Help",
])


# ── Tab: Setup ───────────────────────────────────────────────────────────

with tab_setup:
    st.subheader("Project config")
    st.caption("Anything you change here is saved to `STATE.json` and applies on the next run.")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Identity**")
        author = st.text_input("Author (real name)", project.author_name,
            help="Copyright-page name. Used for USCO registration if you file.")
        pen_name = st.text_input("Pen name", project.author_pen_name,
            help="Title-page name (publicly visible on Amazon). Defaults to real name.")

        st.markdown("**Scope**")
        chapters = st.number_input("Chapters per book", 1, 100,
            project.target_chapters_per_book,
            help="Cap on chapter count for the book outline.")
        words = st.number_input("Target words per chapter", 500, 8000,
            project.target_words_per_chapter, step=100,
            help="~3000 = ~12 min reading. Longer = slower per chapter.")
        books = st.number_input("Books in series", 1, 12,
            project.target_books_in_series,
            help="v1 is single-book focused; series mode is experimental.")

    with col_b:
        st.markdown("**Quality**")
        threshold = st.slider("Pass threshold (1-10)", 1.0, 10.0,
            project.min_chapter_score, 0.1,
            help="Combined reader+critic score needed to pass a chapter. "
                 "7.5 is a sensible default.")
        max_revisions = st.number_input("Max revisions per chapter", 0, 10,
            project.max_revisions_per_chapter,
            help="Hard cap on redraft attempts. Each attempt = one full draft + scoring.")

        st.markdown("**Humanizer**")
        humanize = st.checkbox("Enable humanizer", project.humanize,
            help="Detects and rewrites AI-sounding prose before scoring. "
                 "Does NOT change KDP's disclosure category — the text is still AI-generated.")
        humanizer_target = st.slider("Humanizer target score", 1.0, 10.0,
            project.humanizer_target, 0.1,
            help="AI-score (1=human, 10=robot) below which the humanizer stops rewriting. "
                 "Default 3.5.")
        humanizer_passes = st.number_input("Humanizer max passes", 0, 5,
            project.humanizer_max_passes,
            help="Per-draft cap on humanizer rewrite passes.")

    st.markdown("---")
    st.markdown("### Providers (optional remote routing)")
    st.caption("Defaults are 100% local. Setting a remote provider sends manuscript "
               "text to that provider — only do this if you've verified their ToS.")

    cur_groq      = os.environ.get("GROQ_API_KEY", "")
    cur_cerebras  = os.environ.get("CEREBRAS_API_KEY", "")
    cur_draft_p   = os.environ.get("WRITER_DRAFT_PROVIDER", "local")
    cur_judge_p   = os.environ.get("WRITER_JUDGE_PROVIDER", "local")

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        draft_provider = st.selectbox("Draft provider",
            ["local", "groq", "cerebras"],
            index=["local","groq","cerebras"].index(cur_draft_p) if cur_draft_p in ["local","groq","cerebras"] else 0,
            help="Where prose drafting runs. 'local' uses Ollama; remote uses Llama 3.3 70B.")
        judge_provider = st.selectbox("Judge provider",
            ["local", "groq", "cerebras"],
            index=["local","groq","cerebras"].index(cur_judge_p) if cur_judge_p in ["local","groq","cerebras"] else 0,
            help="Where scoring runs. 'local' is fast and free; remote sends each "
                 "judge call (chapter text) to that provider too.")
    with col_p2:
        groq_key = st.text_input("GROQ_API_KEY", cur_groq, type="password",
            help="Sign up at console.groq.com (no credit card required). "
                 "Stored locally in the book folder's .env with owner-only "
                 "permissions (0600).")
        cerebras_key = st.text_input("CEREBRAS_API_KEY", cur_cerebras, type="password",
            help="Sign up at cloud.cerebras.ai (no credit card required). "
                 "Stored locally in the book folder's .env with owner-only "
                 "permissions (0600).")

    if st.button("Save", type="primary"):
        project.author_name       = author.strip()
        project.author_pen_name   = pen_name.strip()
        project.target_chapters_per_book = chapters
        project.target_words_per_chapter = words
        project.target_books_in_series   = books
        project.min_chapter_score        = threshold
        project.max_revisions_per_chapter = max_revisions
        project.humanize             = humanize
        project.humanizer_target     = humanizer_target
        project.humanizer_max_passes = humanizer_passes
        project.save()

        # Persist provider env to .env
        env_updates = {}
        if groq_key:     env_updates["GROQ_API_KEY"] = groq_key
        if cerebras_key: env_updates["CEREBRAS_API_KEY"] = cerebras_key
        env_updates["WRITER_DRAFT_PROVIDER"] = draft_provider
        env_updates["WRITER_JUDGE_PROVIDER"] = judge_provider
        _save_env_file(project, env_updates)
        st.success("Saved.")


# ── Tab: Bible ───────────────────────────────────────────────────────────

with tab_bible:
    st.subheader("Your bible")
    st.caption("Drop worldbuilding, character, magic, faction, and plot notes here "
               "as `.md` or `.txt` files. The Loremaster reads everything and "
               "consolidates it into `WORLD_BIBLE.md` — your named characters and "
               "rules are treated as authoritative.")

    bible_dir = project.output_dir / "bible"
    bible_dir.mkdir(parents=True, exist_ok=True)

    uploads = st.file_uploader("Upload .md or .txt files", type=["md", "txt"],
        accept_multiple_files=True,
        help="Drag-and-drop multiple files. They'll be saved to bible/ and the "
             "Loremaster will read them on the next run.")
    if uploads:
        for f in uploads:
            dest = bible_dir / f.name
            dest.write_bytes(f.getvalue())
        st.success(f"Saved {len(uploads)} file(s) to bible/")

    st.markdown("**Quick templates** — one click creates a starter file:")
    template_cols = st.columns(5)
    templates = {
        "world.md":      "# World\n\n## Geography\n\n## Climate\n\n## History\n\n",
        "magic.md":      "# Magic System\n\n## Source\n\n## Cost\n\n## Rules\n\n## Failure modes\n\n",
        "characters.md": "# Characters\n\n## (Name)\n- **Drive:**\n- **Wound:**\n- **Voice:**\n\n",
        "factions.md":   "# Factions\n\n## (Name)\n- **Goal:**\n- **Means:**\n- **Conflict with:**\n\n",
        "plot.md":       "# Plot notes\n\n## What I already know about the arc\n\n",
    }
    for i, (name, body) in enumerate(templates.items()):
        with template_cols[i]:
            if st.button(name, use_container_width=True):
                dest = bible_dir / name
                if not dest.exists():
                    dest.write_text(body, encoding="utf-8")
                    st.success(f"Created {name}")
                else:
                    st.info(f"{name} already exists")

    st.markdown("---")
    st.markdown("### Current files")
    files = sorted(p for p in bible_dir.iterdir()
                   if p.is_file() and p.suffix.lower() in {".md", ".txt"})
    if not files:
        st.info("No bible files yet. Upload some, or use the templates above.")
    for f in files:
        with st.expander(f"{f.name}  ({f.stat().st_size:,} bytes)"):
            col_v, col_d = st.columns([5, 1])
            with col_v:
                st.code(f.read_text(encoding="utf-8")[:8000], language="markdown")
            with col_d:
                if st.button("Delete", key=f"del_{f.name}"):
                    f.unlink()
                    st.rerun()


# ── Tab: Write ───────────────────────────────────────────────────────────

with tab_write:
    st.subheader("Run the pipeline")
    st.caption("The pipeline is fully resumable. Killing this app doesn't lose progress — "
               "STATE.json is updated after every chapter.")

    run = _running_state()
    proc = run.get("process")
    running = proc is not None and proc.poll() is None

    col_a, col_b, col_c = st.columns([1, 1, 4])
    with col_a:
        local_only = st.toggle("Local only", value=False,
            help="Disable remote providers for this run regardless of env vars.")
    with col_b:
        if running:
            if st.button("Stop", type="secondary"):
                proc.terminate()
                st.rerun()
        else:
            if st.button("Start", type="primary"):
                cmd = [sys.executable, "-m", "writer_app.cli", "start",
                       str(project.output_dir)]
                if local_only:
                    cmd.append("--local-only")
                log_path = project.output_dir / "pipeline.log"
                log_f = open(log_path, "a", buffering=1)
                env = os.environ.copy()
                run["process"] = subprocess.Popen(
                    cmd, stdout=log_f, stderr=subprocess.STDOUT, env=env,
                )
                run["started_at"] = time.time()
                st.rerun()
    with col_c:
        if running:
            elapsed = time.time() - (run["started_at"] or time.time())
            st.info(f"Pipeline running — {elapsed/60:.1f} min elapsed. "
                    f"PID {proc.pid}")
        elif proc is not None:
            rc = proc.returncode
            if rc == 0:
                st.success("Pipeline finished successfully.")
            else:
                # The CLI prints the reason (e.g. the Ollama start hint) as its
                # last log lines before exiting non-zero; surface it here.
                log_tail = (project.output_dir / "pipeline.log").read_text(
                    encoding="utf-8", errors="ignore").strip().splitlines()[-3:]
                st.error(f"Pipeline exited with code {rc}:\n\n" + "\n\n".join(log_tail))

    # Live log tail
    log_path = project.output_dir / "pipeline.log"
    if log_path.exists():
        text = log_path.read_text(encoding="utf-8", errors="ignore")
        st.text_area("Pipeline log (live tail)", text[-8000:], height=300)

    # Refresh every 3s while running
    if running:
        time.sleep(3)
        st.rerun()

    # Chapter table
    st.markdown("---")
    st.markdown("### Chapter progress")
    fresh = _load_project(project.output_dir) or project
    for b in fresh.books:
        st.markdown(f"**Book {b['number']:02d}: {b.get('title') or '(untitled)'}** "
                    f"— status: {b['status']}")
        if not b["chapters"]:
            st.caption("(no chapters yet — run the pipeline first)")
            continue
        rows = []
        for ch in sorted(b["chapters"], key=lambda c: c["number"]):
            rows.append({
                "#":         ch["number"],
                "Title":     ch.get("title", ""),
                "Status":    ch["status"],
                "Iters":     ch.get("iterations", 0),
                "Score":     ("—" if ch["status"] == "judge_failed"
                              else f"{ch.get('score', 0):.2f}"),
                "Judge error": ch.get("judge_error", ""),
                "AI before": f"{ch.get('ai_score_before', 0):.1f}",
                "AI after":  f"{ch.get('ai_score_after', 0):.1f}",
                "User rev":  "yes" if ch.get("user_revised") else "",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)


# ── Tab: Chapters ────────────────────────────────────────────────────────

with tab_chapters:
    st.subheader("Inspect and revise chapters")

    fresh = _load_project(project.output_dir) or project
    all_books = sorted(b["number"] for b in fresh.books)
    if not all_books:
        st.info("No chapters yet. Run the pipeline first from the Write tab.")
        st.stop()

    col_b, col_c = st.columns(2)
    with col_b:
        book_n = st.selectbox("Book", all_books)
    book = fresh.book(book_n)
    chapter_numbers = sorted(c["number"] for c in book.chapters)
    if not chapter_numbers:
        st.info("This book has no chapters yet.")
        st.stop()
    with col_c:
        chapter_n = st.selectbox("Chapter", chapter_numbers,
            format_func=lambda n: f"Ch {n:02d} — {next((c['title'] for c in book.chapters if c['number']==n), '')}")

    ch_dir = fresh.chapter_dir(book_n, chapter_n)

    # Available versions
    versions = []
    for p in sorted(ch_dir.glob("v*.md")):
        if "raw" not in p.stem:
            versions.append(p.name)
    if (ch_dir / "final.md").exists():
        versions.append("final.md")
    user_rev_path = fresh.book_dir(book_n) / "revisions" / f"chapter-{chapter_n:02d}.md"
    if user_rev_path.exists():
        versions.append("revisions/chapter-NN.md (your revision)")

    if not versions:
        st.info("This chapter hasn't been drafted yet.")
        st.stop()

    v_choice = st.selectbox("Version", versions, index=len(versions)-1)
    if v_choice.startswith("revisions/"):
        chapter_text = user_rev_path.read_text(encoding="utf-8")
    else:
        chapter_text = (ch_dir / v_choice).read_text(encoding="utf-8")

    col_text, col_reports = st.columns([3, 2])

    with col_text:
        st.markdown(f"#### {v_choice}")
        edited = st.text_area("Chapter text", chapter_text, height=600,
            help="Edit here and click 'Save as user revision' to override the AI's final for this chapter.")
        col_save, col_humanize = st.columns(2)
        with col_save:
            if st.button("💾 Save as user revision",
                         help="Saves to book-NN/revisions/chapter-NN.md. Export uses this over final.md."):
                user_rev_path.parent.mkdir(parents=True, exist_ok=True)
                user_rev_path.write_text(edited, encoding="utf-8")
                st.success(f"Saved to {user_rev_path.name}")
        with col_humanize:
            if st.button("🪄 Re-run humanizer on this version",
                         help="Runs the AI-tell detector + rewriter on the current text. "
                              "Results are written to a side file you can review."):
                with st.spinner("Humanizing …"):
                    try:
                        project.draft_model, project.judge_model = resolve_models()
                        result = humanizer_mod.run(
                            project, edited,
                            max_passes=project.humanizer_max_passes,
                            ai_score_target=project.humanizer_target,
                        )
                    except (OllamaUnreachableError, ModelUnavailableError) as e:
                        st.error(str(e))
                    else:
                        out = ch_dir / "humanized_preview.md"
                        out.write_text(result["text"], encoding="utf-8")
                        st.success(f"AI-score: {result['ai_score_before']} → {result['ai_score_after']} "
                                   f"after {result['passes']} pass(es). Saved to {out.name}.")

    with col_reports:
        # Determine which iteration the chosen version corresponds to
        iter_n = None
        m = re.match(r"v(\d+)\.md", v_choice)
        if m:
            iter_n = int(m.group(1))
        elif v_choice == "final.md":
            ch_state = book.chapter(chapter_n)
            iter_n = ch_state.iterations or 1

        reader_path  = ch_dir / f"v{iter_n}_reader.md" if iter_n else None
        critic_path  = ch_dir / f"v{iter_n}_critic.md" if iter_n else None
        humanizer_path = ch_dir / f"v{iter_n}_humanizer.json" if iter_n else None

        st.markdown("#### Reports")
        if reader_path and reader_path.exists():
            with st.expander("📚 Reader Panel", expanded=True):
                st.markdown(reader_path.read_text(encoding="utf-8"))
        if critic_path and critic_path.exists():
            with st.expander("📝 Critic Panel"):
                st.markdown(critic_path.read_text(encoding="utf-8"))
        if humanizer_path and humanizer_path.exists():
            with st.expander("🪄 Humanizer diagnostics"):
                try:
                    data = json.loads(humanizer_path.read_text(encoding="utf-8"))
                    st.json(data)
                except Exception as e:
                    st.error(f"Could not parse humanizer report: {e}")


# ── Tab: Export ──────────────────────────────────────────────────────────

with tab_export:
    st.subheader("Export and KDP disclosure")
    st.caption("DOCX and EPUB are ready for upload to Amazon KDP. The export "
               "uses your `revisions/chapter-NN.md` files over the AI's `final.md` "
               "wherever they exist.")

    fresh = _load_project(project.output_dir) or project
    if not fresh.books:
        st.info("No books to export yet.")
        st.stop()

    book_options = sorted(b["number"] for b in fresh.books)
    book_n = st.selectbox("Book to export", book_options)
    fmts = st.multiselect("Formats", ["docx", "epub", "md"], default=["docx", "epub"],
        help="DOCX is what KDP recommends for novels. EPUB is also accepted. "
             "MD is the source markdown.")

    if st.button("Generate", type="primary"):
        with st.spinner("Generating …"):
            paths = export_mod.export_book(fresh, book_n, fmts)
            for p in paths:
                st.success(f"Wrote {p.name} ({p.stat().st_size:,} bytes)")
                with open(p, "rb") as f:
                    st.download_button(f"⬇️ Download {p.name}", f.read(), p.name)

    st.markdown("---")
    st.markdown("### KDP AI disclosure")
    st.caption("Run this and copy the answer onto the KDP upload form. "
               "writer-app produces AI-generated text — disclosure is required.")

    if st.button("Generate disclosure text"):
        out = provenance_mod.write_disclosure(fresh)
        text = out.read_text(encoding="utf-8")
        st.code(text, language="markdown")

    st.markdown("---")
    st.markdown("### Provenance (audit trail)")
    prov_paths = []
    for b in fresh.books:
        p = fresh.book_dir(b["number"]) / "PROVENANCE.md"
        if p.exists():
            prov_paths.append(p)
    if not prov_paths:
        st.info("No PROVENANCE.md yet — run the pipeline to completion first.")
    for p in prov_paths:
        with st.expander(p.name):
            st.markdown(p.read_text(encoding="utf-8"))


# ── Tab: Help ────────────────────────────────────────────────────────────

with tab_help:
    st.subheader("Help and hints")

    st.markdown("### The pipeline in one paragraph")
    st.markdown(
        "Loremaster reads your bible and produces `WORLD_BIBLE.md`. Plotter "
        "designs the chapter outline. For every chapter the Drafter writes "
        "prose, the Humanizer rewrites AI-tells, four Readers and three "
        "Critics score it, and if it falls below your pass threshold the "
        "Reviser tries again (up to your revision cap). Once all chapters "
        "are done, a Continuity pass checks for name drift and unpaid promises, "
        "Provenance records the audit trail, and Export produces a KDP-ready "
        "manuscript. Everything is resumable.")

    st.markdown("### Where things live")
    st.markdown(f"- This project: `{project.output_dir}`")
    st.markdown(f"- Bible inputs: `{project.output_dir / project.bible_dir}/`")
    st.markdown(f"- Per-chapter artefacts: `{project.output_dir}/book-NN/chapter-NN/`")
    st.markdown(f"- Your revisions (override AI): `{project.output_dir}/book-NN/revisions/`")
    st.markdown(f"- Exports: `{project.output_dir}/book-NN/<slug>.docx, .epub`")
    st.markdown(f"- KDP disclosure text: `{project.output_dir}/KDP_DISCLOSURE.md`")

    st.markdown("### Documentation")
    docs = [
        ("README",          "https://github.com/Thandv/writer-app/blob/main/README.md"),
        ("Install guide",   "https://github.com/Thandv/writer-app/blob/main/docs/INSTALL.md"),
        ("Quickstart",      "https://github.com/Thandv/writer-app/blob/main/docs/QUICKSTART.md"),
        ("CLI reference",   "https://github.com/Thandv/writer-app/blob/main/docs/CLI.md"),
        ("Config reference", "https://github.com/Thandv/writer-app/blob/main/docs/CONFIG.md"),
        ("Remote routing",  "https://github.com/Thandv/writer-app/blob/main/docs/REMOTE.md"),
        ("Publishing",      "https://github.com/Thandv/writer-app/blob/main/docs/PUBLISHING.md"),
        ("Troubleshooting", "https://github.com/Thandv/writer-app/blob/main/docs/TROUBLESHOOTING.md"),
        ("Architecture",    "https://github.com/Thandv/writer-app/blob/main/docs/ARCHITECTURE.md"),
    ]
    for name, url in docs:
        st.markdown(f"- [{name}]({url})")

    st.markdown("### One important reminder")
    st.warning(
        "Whether you run locally or via a remote API, the prose is **AI-generated**. "
        "If you publish on Amazon KDP you must disclose this (answer **yes** to "
        "the AI-generated text question). The humanizer makes prose read less "
        "like AI but does not change this disclosure obligation."
    )
