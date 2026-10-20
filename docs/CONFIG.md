# Configuration reference

Every knob that affects the pipeline, with what it does and when to change it.

## Project config (stored in `STATE.json`)

These persist with the project. Set them at `writer init` or change them
with `writer config <path> --<flag> ...`.

| Key | Default | What it does |
|---|---|---|
| `title` | (required) | Series title — used on title page, export filename |
| `author_name` | "" | Real author name. Used on copyright page and for USCO registration |
| `author_pen_name` | "" | Publishing name. Used on title page. Defaults to author_name if blank |
| `target_books_in_series` | 1 | How many books to plan; v1 is single-book-focused |
| `target_chapters_per_book` | 30 | Chapter count. Less = faster but smaller book |
| `target_words_per_chapter` | 3000 | ~12 min reading; longer = slower per chapter |
| `min_chapter_score` | 7.5 | Combined reader+critic score (1–10) to pass a chapter |
| `max_revisions_per_chapter` | 3 | Revision cap before keeping best draft |
| `humanize` | true | Run humanizer detector + rewriter |
| `humanizer_target` | 3.5 | AI-score target. Lower = stricter rewriting |
| `humanizer_max_passes` | 2 | Cap on humanizer rewrite passes |

**Cost of higher quality**
- Doubling `target_words_per_chapter` roughly doubles drafting time.
- Raising `min_chapter_score` from 7.5 to 8.5 typically doubles revision iterations.
- Each `humanizer_max_passes` = +1 detector LLM call + +1 rewriter LLM call.

## Environment variables

These are not persisted in the project; set them per shell session.

### Local model selection

| Env var | Default | What it does |
|---|---|---|
| `WRITER_DRAFT_MODEL` | `mistral-nemo:12b` | Local Ollama model used by Drafter, Reviser, Humanizer rewriter |
| `WRITER_JUDGE_MODEL` | `qwen2.5:7b` | Local Ollama model used by Loremaster, Plotter, Reader, Critic, Continuity, Humanizer detector |
| `OLLAMA_HOST` | `http://localhost:11434` | Override Ollama endpoint |

If the configured local model isn't pulled, the resolver falls back to the
closest pulled family member, then to `qwen2.5:7b`, then to the first pulled
chat model in alphabetical order. The choice is the same on every run.
Embedding models (name contains `embed`) and vision models (base name ends
in `vl`, e.g. `qwen2.5vl:3b`) are never chosen. If no usable model is pulled,
`writer start` and `writer providers` stop with exit code 1 and print the
`ollama pull` command for each missing default. `writer start` and
`writer providers` say when a fallback is in use.

### Remote provider routing

| Env var | Default | What it does |
|---|---|---|
| `WRITER_DRAFT_PROVIDER` | `local` | `local` / `groq` / `cerebras` — where prose drafting runs |
| `WRITER_JUDGE_PROVIDER` | `local` | Same for scoring/structured-output calls |
| `GROQ_API_KEY` | — | Your Groq key (no card required, see [REMOTE.md](REMOTE.md)) |
| `CEREBRAS_API_KEY` | — | Your Cerebras key |
| `WRITER_DRAFT_REMOTE_MODEL` | `llama-3.3-70b-versatile` (Groq) | Override remote draft model name |
| `WRITER_JUDGE_REMOTE_MODEL` | `llama-3.1-8b-instant` (Groq) | Override remote judge model name |

### Corpus

| Env var | Default | What it does |
|---|---|---|
| `WRITER_CORPUS_DIR` | auto | Override the corpus directory. Auto-detect tries `<repo>/corpus/` then `~/.local/share/writer-app/corpus/` |

## File-system paths (auto)

| Path | What it contains |
|---|---|
| `~/books/<slug>/` | Project root |
| `~/books/<slug>/STATE.json` | Pipeline state, resumable |
| `~/books/<slug>/WORLD_BIBLE.md` | Loremaster output |
| `~/books/<slug>/SERIES_OUTLINE.md` | Plotter output (if multi-book) |
| `~/books/<slug>/bible/` | Your inputs (untouched) |
| `~/books/<slug>/book-NN/BOOK_OUTLINE.md` | Plotter chapter beats |
| `~/books/<slug>/book-NN/CONTINUITY_REPORT.md` | Continuity pass output |
| `~/books/<slug>/book-NN/PROVENANCE.md` | Audit trail |
| `~/books/<slug>/book-NN/MANUSCRIPT.md` | Assembled manuscript |
| `~/books/<slug>/book-NN/the-bone-empire.docx` | KDP-ready DOCX (after `writer export`) |
| `~/books/<slug>/book-NN/the-bone-empire.epub` | EPUB |
| `~/books/<slug>/book-NN/revisions/chapter-NN.md` | Your override (prefer over AI final) |
| `~/books/<slug>/book-NN/chapter-NN/` | All AI versions, reader/critic/humanizer reports |
| `~/books/<slug>/KDP_DISCLOSURE.md` | KDP answer text (after `writer disclosure`) |

## Recommended settings by use-case

### Fast first pass (overnight, lower quality)
```bash
writer config <path> --chapters 20 --words 2000 --threshold 6.5 --max-revisions 1
```

### Higher quality (multi-day, more polish)
```bash
writer config <path> --chapters 30 --words 3500 --threshold 8.0 --max-revisions 4
```

### "Just want to see if it works" (minimum smoke test)
```bash
writer init "Smoke Test" --chapters 3 --words 800 --threshold 6.0 --max-revisions 1
```
