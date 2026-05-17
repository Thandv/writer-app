# writer-app

> **Local-first multi-agent novel writer.**
> Drop a worldbuilding bible into a folder, run one command, and a pipeline
> of writing agents produces a manuscript — revising each chapter against
> simulated readers and critics until it crosses a quality threshold.

[![CI](https://github.com/Thandv/writer-app/actions/workflows/ci.yml/badge.svg)](https://github.com/Thandv/writer-app/actions/workflows/ci.yml)
[![Release](https://github.com/Thandv/writer-app/actions/workflows/release.yml/badge.svg)](https://github.com/Thandv/writer-app/actions/workflows/release.yml)
[![Tests](https://img.shields.io/badge/tests-151_passing-brightgreen)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-58%25-yellow)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

No data leaves your machine by default. All inference runs through Ollama.
Optional free-tier remote APIs (Groq, Cerebras) can be enabled per-role for
much better prose, with automatic fallback to local when offline.

---

## Pipeline at a glance

```
your bible/                 →  Loremaster        →  WORLD_BIBLE.md
                            →  Plotter           →  SERIES_OUTLINE.md, BOOK_OUTLINE.md
   for each chapter:
       →  Drafter           →  v1 (raw)
       →  Humanizer         →  v1 (AI-tells removed)
       →  Reader Panel      →  4 reader scores
       →  Critic Panel      →  3 critic scores + line notes
       →  if below threshold: Reviser → loop
       →  final.md
   then:
       →  Continuity Pass   →  CONTINUITY_REPORT.md
       →  Provenance Pass   →  PROVENANCE.md
       →  Export            →  *.docx, *.epub
       →  Disclosure        →  KDP_DISCLOSURE.md
```

Reader panel = 4 personas (epic-fan, grimdark-fan, progression-fan, casual).
Critic panel = 3 personas (developmental editor, prose critic, structure critic).

---

## Quick install (macOS / Linux)

The fast path is the self-extracting installer from GitHub Releases:

```bash
curl -fsSL https://github.com/Thandv/writer-app/releases/latest/download/writer-app-install.sh \
  | bash
```

Or from source:

```bash
git clone https://github.com/Thandv/writer-app.git
cd writer-app
make install
```

You'll also need [Ollama](https://ollama.com) running locally:

```bash
brew install ollama
brew services start ollama
ollama pull qwen2.5:7b          # judge model (fast)
ollama pull mistral-nemo:12b    # draft model (best local prose, ~7GB)
```

Then:

```bash
writer corpus                                # build reference corpus
writer init "My Series" --author "Your Name" --pen-name "Pen Name"
# drop bible files into ~/books/my-series/bible/
writer start ~/books/my-series               # write the book (resumable)
```

Or use the interactive UI:

```bash
writer ui                                    # opens in your browser
```

---

## Interactive UI

```bash
writer ui
```

Tabs:
- **Setup** — title, author, chapter count, target words, quality threshold,
  humanizer config, provider keys. Every field has a hint.
- **Bible** — upload `.md` / `.txt` files; preview / delete.
- **Write** — start / resume the pipeline; live chapter table; pause / stop.
- **Chapters** — read each version, view reader + critic reports, save
  user revisions inline.
- **Export** — generate `.docx` and `.epub`, view PROVENANCE.md, copy the
  KDP disclosure text.
- **Help** — what each field means; links to docs.

The UI is a thin shell over the CLI — anything you can do here you can also
do with `writer ...` commands, and the on-disk artefacts are the same.

---

## Local-only vs hybrid (remote-API) mode

Default: **local-only**. Nothing leaves your machine.

To enable free-tier remote drafting (Groq's Llama 3.3 70B at ~300 tok/s,
or Cerebras), sign up yourself (no credit card required as of writing),
then export the key:

```bash
export GROQ_API_KEY='gsk_...'
export WRITER_DRAFT_PROVIDER=groq    # draft prose remotely
export WRITER_JUDGE_PROVIDER=local   # keep judging local + free + fast

writer providers   # confirm routing
writer start ~/books/my-series       # auto-falls-back to local if offline
```

When offline (no internet), or when you pass `--local-only`, the pipeline
routes every call to local Ollama. Three consecutive remote failures open
the circuit breaker for the rest of the run.

Both providers' published ToS state they don't train on customer inputs —
verify the current ToS yourself before relying on it for unpublished text.

---

## Publishing on Amazon KDP

This tool is designed for the **minimum-revision self-publishing workflow**:
let the pipeline produce a draft, do a light read-through, optionally drop
edits into `book-NN/revisions/chapter-NN.md`, then `writer export`.

Critical things to know:

- **You must disclose AI-generated text on KDP.** Even after the humanizer.
  Run `writer disclosure ~/books/<slug>` to get the exact answer text.
  Disclosure is internal to Amazon and does not show on your product page.
- **Your IP is protected** — plot, world, characters, magic system are your
  copyrightable original work. The AI-generated prose itself is not
  copyrightable under current US Copyright Office guidance. The more you
  revise, the stronger your overall copyright position.
- **No credit card** is required if you stick to local Ollama or use the
  no-card free tiers (Groq, Cerebras).

See [docs/PUBLISHING.md](docs/PUBLISHING.md) for the full self-publishing
checklist.

---

## Documentation

| Document                                            | What's in it                                    |
|-----------------------------------------------------|--------------------------------------------------|
| [docs/INSTALL.md](docs/INSTALL.md)                 | Step-by-step install on macOS / Linux           |
| [docs/QUICKSTART.md](docs/QUICKSTART.md)           | First book end-to-end                            |
| [docs/CLI.md](docs/CLI.md)                         | Every `writer …` subcommand                      |
| [docs/UI.md](docs/UI.md)                           | Streamlit UI walkthrough with screenshots       |
| [docs/CONFIG.md](docs/CONFIG.md)                   | Every config knob and what it does               |
| [docs/REMOTE.md](docs/REMOTE.md)                   | Groq / Cerebras setup and privacy notes         |
| [docs/PUBLISHING.md](docs/PUBLISHING.md)           | KDP, disclosure, copyright                       |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common errors and fixes                          |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)       | How the agents fit together                      |

---

## Limitations to know

- Local 7–12B models don't write bestseller-grade prose unaided. The
  reader/critic revision loop closes part of the gap; remote 70B closes
  more; nothing closes it entirely. Set expectations.
- A 30-chapter, 3000-words-per-chapter book at default settings is several
  hours of M2 compute. Overnight runs are normal. Everything is resumable.
- Continuity checking happens once per book post-hoc, not cross-book.
- Cover generation is out of scope. Make or commission your own.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE). Note: the licence covers the code, not text
generated by AI models invoked through the tool.
