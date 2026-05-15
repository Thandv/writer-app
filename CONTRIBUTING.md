# Contributing

Thanks for your interest. A few notes before you open a PR.

## Development setup

```bash
git clone https://github.com/Thandv/writer-app.git
cd writer-app
python3 -m venv .venv
source .venv/bin/activate
make install      # editable install with [dev] extras
make corpus       # build the reference corpus
```

You'll also need [Ollama](https://ollama.com) running locally with at least
one model pulled:

```bash
ollama pull qwen2.5:7b
```

## Running tests

```bash
make test
```

CI runs the same on every push.

## Coding style

- Stdlib-first. The runtime requirement is "Python 3.10+ and Ollama". Adding
  a runtime dependency requires discussion in an issue first. Optional
  extras (UI, etc.) are fine via `[project.optional-dependencies]`.
- One agent per file under `src/writer_app/`. Shared code in `shared/`.
- The two model roles (`draft` and `judge`) are honoured by every LLM call.
  When adding a new agent, pass `role="draft"` for prose-producing calls and
  `role="judge"` for scoring/structured-output calls.
- Documentation lives in `docs/` as plain Markdown. Keep it terse.

## Scope notes

- **AI-generated text is still AI-generated** — even after the humanizer.
  Anything that risks misleading users about this (e.g. promoting the
  humanizer as a way to bypass KDP disclosure) is out of scope.
- **No scraping of copyrighted material.** The corpus is Project Gutenberg
  classics plus fair-use style/craft notes. PRs adding scrapers for
  paid/restricted sites will not be merged.
- **Privacy default is local-only.** Remote-provider integration must remain
  opt-in via env var and must fall back cleanly to local on any failure.

## Reporting issues

Include:
- OS and Python version (`python3 --version`)
- `writer providers` output (with API keys redacted)
- Steps to reproduce
- What you expected vs what happened

For pipeline failures, share `STATE.json` from the project directory (it
contains no secrets, just configuration and per-chapter status).
