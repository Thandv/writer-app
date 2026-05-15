# Interactive UI

The Streamlit UI is a complete cover for the CLI — anything you can do
here you can also do with `writer ...` commands. The on-disk artefacts
(STATE.json, chapter files, PROVENANCE.md) are identical either way.

## Launch

```bash
writer ui
```

Opens in your default browser at `http://localhost:8501`.

If Streamlit isn't installed:
```bash
pip install 'writer-app[ui]'
```

## Layout

The UI has a left sidebar for **project selection** and **provider status**,
and a main area split into tabs.

### Sidebar

- **Project selector** — pick from `~/books/*` or "Create new"
- **Status snapshot** — books done, current chapter, last update
- **Quick actions** — pause / resume the pipeline; `--local-only` toggle
- **Provider status** — green/red dots for Ollama, Groq, Cerebras and
  whether the internet is reachable

### Tab: Setup

Every field has a hint below it explaining what it does. The fields:

| Field | Hint |
|---|---|
| Series title | Used in title pages and the export filename |
| Author (real name) | Goes on the copyright page; used for USCO registration |
| Pen name | Goes on the title page; leave blank to use real name |
| Number of books | 1 to start; series mode is experimental |
| Chapters per book | Default 30. Less = faster runs but smaller scope |
| Words per chapter | Default 3000 (~12 min reading). Longer = slower per chapter |
| Pass threshold | Combined reader+critic score (1–10). Default 7.5. Lower = faster, higher = more revisions |
| Max revisions | Cap on revision attempts per chapter. Default 3 |
| Humanizer enabled | Detect and rewrite AI-tells before scoring. Default on |
| Humanizer target | AI-score (1=human, 10=robot). Stops rewriting when below this. Default 3.5 |
| Humanizer max passes | Cap on rewrite passes per draft. Default 2 |
| GROQ_API_KEY | Paste your Groq key. Sets the env var for this process |
| CEREBRAS_API_KEY | Paste your Cerebras key |
| Draft provider | local / groq / cerebras — where prose generation runs |
| Judge provider | local / groq / cerebras — where scoring runs (local is usually right) |

"Save" persists everything to `STATE.json` and `.env` (the API keys stay
local — never committed to git, the project's `.gitignore` excludes `.env`).

### Tab: Bible

- **Drag-and-drop uploader** for `.md` / `.txt` files
- **File list** showing what's currently in `bible/`
- **Inline preview** when you click a file
- **Delete** button per file
- **Quick templates**: one-click buttons for `world.md`, `magic.md`,
  `characters.md`, `factions.md`, `plot.md` that drop in a starter file
  with hint comments

### Tab: Write

- **Start** button — spawns the pipeline as a subprocess
- **Pause** / **Stop** — interrupts gracefully; resume any time
- **Live log** — tails the pipeline's stdout
- **Per-chapter table** — chapter, status, iterations, combined score,
  AI-score before/after humanizer, user-revised flag
- **Click a row** → jumps to the Chapters tab for that chapter

### Tab: Chapters

For each chapter:
- **Version selector** — v1, v2, …, final, plus your `revisions/` file if present
- **Read the prose** — full text in a scrollable pane
- **Reader Panel report** — 4 readers, scores per rubric category, what
  landed, what missed, would-keep-reading verdicts
- **Critic Panel report** — 3 critics, scores per rubric category, line
  notes with quoted offending lines, revision directives
- **Humanizer report** — heuristic + LLM AI-scores before / after, the
  specific tells caught, the heuristic hits
- **Edit and save as user revision** — type / paste your edits into the
  textarea; click "Save as `revisions/chapter-NN.md`" to override the AI's
  version in the export

### Tab: Export

- **Generate** buttons for DOCX, EPUB, MD
- **Download** links for the generated files
- **PROVENANCE.md viewer** — see the per-chapter audit table
- **KDP disclosure text** with a "Copy" button — paste into the Amazon form
- **Hint panel** explaining what to expect on the KDP upload flow

### Tab: Help

- A condensed version of QUICKSTART.md
- Glossary: every term used in the UI explained
- Links to all of `docs/`

## Hints and progressive disclosure

The UI is designed so a new user can produce their first book without
reading any documentation:
- Every input has an inline hint.
- Critical warnings (e.g. "this still counts as AI-generated text for KDP
  disclosure even after humanizing") are surfaced as info banners on the
  Export and Setup tabs.
- Optional/advanced settings are behind an expander labelled "Advanced".

## Privacy reminders in the UI

- The Setup tab shows the privacy state per role (local vs remote) with a
  link to the active provider's ToS.
- The Write tab shows a banner if remote routing is enabled, naming the
  provider that will receive manuscript text.
- When you save API keys via the Setup tab, the UI writes them to a local
  `.env` in the project dir (which is gitignored). Keys are never sent
  anywhere except to the providers themselves at call time.
