# CLI reference

Every `writer …` subcommand. `PATH` accepts either a full path or just a
slug under `~/books/`.

## `writer init "Title"`

Scaffold a new project at `~/books/<slug>/`.

| Flag | Default | What it does |
|---|---|---|
| `--out PATH` | `~/books/<slug>` | Custom project path |
| `--books N` | 1 | Books in series (currently single-book is the main path) |
| `--chapters N` | 30 | Chapters per book |
| `--words N` | 3000 | Target words per chapter |
| `--threshold X` | 7.5 | Min combined reader+critic score to pass a chapter |
| `--max-revisions N` | 3 | Max revision passes per chapter before keeping best |
| `--no-humanize` | off | Disable the AI-tell detector + rewriter |
| `--humanizer-target X` | 3.5 | AI-score target (1=human, 10=robot) |
| `--humanizer-passes N` | 2 | Max humanizer rewrite passes per draft |
| `--author "Name"` | — | Real name (used on copyright page) |
| `--pen-name "Name"` | — | Publishing name (used on title page) |

## `writer corpus`

Build the reference corpus (style cards + craft notes + Project Gutenberg).

| Flag | What it does |
|---|---|
| `--no-gutenberg` | Skip the heavy downloads (still writes style cards + craft notes) |
| `--list` | Show what's already on disk |

The corpus directory defaults to `<repo>/corpus/` in development or
`~/.local/share/writer-app/corpus/` when installed. Override with
`WRITER_CORPUS_DIR`.

## `writer start PATH`

Run (or resume) the pipeline. Resumable — kill any time and restart.

| Flag | What it does |
|---|---|
| `--local-only` | Disable remote providers for this run (use Ollama only) |
| `--chapters / --words / --threshold / --max-revisions / --books` | Override the project's config for this run |

## `writer status PATH`

Print project summary and per-chapter progress.

## `writer config PATH`

View (no flags) or change (with flags) project config.

| Flag | What it does |
|---|---|
| `--chapters N` | Change target chapters per book |
| `--words N` | Change target words per chapter |
| `--threshold X` | Change pass threshold |
| `--max-revisions N` | Change revision cap |
| `--books N` | Change series book count |
| `--humanizer-target X` | Change AI-score target |
| `--humanizer-passes N` | Change humanizer pass cap |
| `--humanize y/n` | Enable / disable humanizer entirely |
| `--author "Name"` | Set real author name |
| `--pen-name "Name"` | Set pen name |

## `writer export PATH`

Produce KDP-ready manuscripts.

| Flag | Default | What it does |
|---|---|---|
| `--book N` | all | Export only this book |
| `--formats docx epub md` | `docx epub` | Choose subset |

Prefers your `book-NN/revisions/chapter-NN.md` over the AI's `final.md`
when both exist.

## `writer disclosure PATH`

Write and print the KDP AI-disclosure answers. Also writes
`KDP_DISCLOSURE.md` at the project root.

## `writer providers`

Show local + remote routing config and reachability. Does not require an
existing project.

## `writer humanize PATH CHAPTER_FILE`

Re-run the humanizer on a single chapter file out-of-band. Useful for
already-final chapters, or chapters you've edited and want re-checked.

| Flag | Default | What it does |
|---|---|---|
| `--passes N` | 2 | Max humanizer passes |
| `--target X` | 3.5 | Stop at this AI-score |
| `--write` | off | Overwrite the input file in place (default: write side file) |
| `--no-llm` | off | Use heuristic detector only (much faster) |

## `writer ui`

Launch the interactive Streamlit UI in your browser. Requires
`pip install streamlit` (or `pip install 'writer-app[ui]'`).

Extra arguments after `ui` are passed through to `streamlit run`:

```bash
writer ui -- --server.port 8502
```
