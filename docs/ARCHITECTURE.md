# Architecture

A high-level view of how the agents fit together. For end-user docs see
[QUICKSTART.md](QUICKSTART.md) and [CLI.md](CLI.md).

## Package layout

```
writer-app/
├── src/writer_app/                # the Python package
│   ├── cli.py                     # argparse entry point (writer command)
│   ├── orchestrator.py            # pipeline state machine
│   ├── loremaster.py              # bible → WORLD_BIBLE.md
│   ├── plotter.py                 # series + book outlines
│   ├── drafter.py                 # chapter prose generation
│   ├── reviser.py                 # critique-aware redraft (thin wrapper on drafter)
│   ├── reader_panel.py            # 4 reader-persona scoring
│   ├── critic_panel.py            # 3 critic-persona scoring
│   ├── humanizer.py               # AI-tell detector + rewriter
│   ├── continuity.py              # post-book continuity check
│   ├── provenance.py              # PROVENANCE.md + KDP_DISCLOSURE.md
│   ├── export.py                  # DOCX + EPUB
│   └── shared/
│       ├── llm.py                 # router: local Ollama + role-based remote routing
│       ├── remote.py              # Groq + Cerebras (OpenAI-compatible) + circuit breaker
│       ├── tools.py               # read/write/list/retrieve_corpus (for tool-using agents)
│       ├── memory.py              # BookProject / BookState / ChapterState dataclasses
│       ├── rubric.py              # reader + critic rubric weights and personas
│       └── corpus.py              # corpus dir resolver + style cards + craft notes
├── ui/app.py                      # Streamlit UI
├── corpus/                        # dev-mode corpus (style_cards/, craft/, gutenberg/)
├── docs/                          # markdown documentation
├── scripts/                       # build/install scripts
├── tests/                         # pytest suite
└── .github/workflows/             # CI + release
```

## Two model roles

Every LLM call declares a **role**, either `draft` or `judge`. The router
in `shared/llm.py` decides per-call:

1. If `WRITER_<ROLE>_PROVIDER` is set to a remote provider AND its API key
   is present AND `internet_available()` AND the circuit breaker is closed
   AND `--local-only` was not set: route to remote.
2. Otherwise: route to local Ollama using `WRITER_<ROLE>_MODEL`.

Any remote failure falls back to local automatically (URLError, HTTPError,
timeout, malformed response). Three consecutive failures for a provider
open its circuit breaker for the rest of the run.

| Agent | Function | Role |
|---|---|---|
| Loremaster | bible → WORLD_BIBLE.md | judge (local-only, uses tool calls) |
| Plotter | outlines | judge (local-only, uses tool calls) |
| Drafter | chapter prose | **draft** |
| Reviser | redraft with critique | **draft** |
| Humanizer rewriter | reduce AI tells | **draft** |
| Humanizer detector | find AI tells | judge |
| Reader Panel | engagement scores | judge |
| Critic Panel | craft scores | judge |
| Continuity | post-book check | judge |

Tool-using agents (Loremaster, Plotter) stay local because tool-calling
syntax varies across providers and we keep them simple. All other agents
honour the role.

## State machine

`BookProject` holds the pipeline state and persists to `STATE.json` after
every state change. The orchestrator is idempotent: re-running `writer
start` skips:

- The Loremaster if `WORLD_BIBLE.md` exists with >500 bytes.
- The series Plotter if `SERIES_OUTLINE.md` exists.
- The book Plotter if `BOOK_OUTLINE.md` exists.
- Any chapter whose `chapter-NN/final.md` exists AND status == "done".

This makes the pipeline trivially resumable — kill it at any time.

Chapter status is one of `pending | drafting | revising | done | judge_failed`.
A `judge_failed` chapter has no scored draft and no `final.md`. The next
`writer start` re-runs it from a fresh draft. A book is marked `done` only
when every chapter is `done`.

### Judge failures

A reader or critic whose JSON call fails, or whose JSON has no numeric
rubric scores, is recorded as a failure (`judge_failed: true` plus the
error). An HTTP error from a running Ollama (e.g. out of memory) counts as
one failed judge. It gets no score and is never
counted as a 5. Panel averages and the combined score use only the judges
that answered. If one whole panel fails, the combined score is the other
panel's average. If every judge fails:

- on the first draft: the chapter is `judge_failed`, with the error in
  `judge_error` in `STATE.json`. No revision runs.
- on a later revision: the loop stops and the best scored draft becomes
  `final.md` with its real score. The error is kept in `judge_error`.

Three `judge_failed` chapters in a row abort `writer start` with exit code 1.
The count is kept in memory for one run only. An unreachable Ollama is
not a judge failure: it stops the run at once (exit 1, start hint).

## Chapter loop

```
for each chapter in BOOK_OUTLINE.md:
    iteration = 1
    revision_note = ""
    best = (text=None, score=-1)

    while iteration <= max_revisions + 1:
        raw = Drafter(beats, prev_chapter, revision_note) if iter > 1
              else Drafter(beats, prev_chapter)

        text, ai_score = Humanizer(raw)   # detector + rewriter, capped passes

        reader  = ReaderPanel(text)       # 4 personas, JSON output
        critic  = CriticPanel(text, beats) # 3 personas, JSON output

        combined = weighted_avg(reader, critic)   # judged reports only

        save_artifacts(vN.md, vN_raw.md, vN_reader.{md,json}, ...)

        if combined is None:              # every judge failed
            record judge_error; break

        if combined > best.score:
            best = (text, combined)

        if combined >= threshold:
            break
        if iteration > max_revisions:
            break

        revision_note = build_revision_note(reader, critic)
        iteration += 1

    if no draft was scored: status = judge_failed (no final.md)
    else: save best.text → chapter-NN/final.md
```

## Output structure

```
~/books/<slug>/
├── STATE.json
├── WORLD_BIBLE.md
├── SERIES_OUTLINE.md            (if multi-book)
├── KDP_DISCLOSURE.md            (after writer disclosure)
├── bible/                       your inputs, untouched
└── book-NN/
    ├── BOOK_OUTLINE.md
    ├── CONTINUITY_REPORT.md
    ├── PROVENANCE.md
    ├── MANUSCRIPT.md
    ├── <slug>.docx              after writer export
    ├── <slug>.epub
    ├── revisions/               your edits — used over AI final
    │   └── chapter-NN.md
    └── chapter-NN/
        ├── v1.md                post-humanize draft
        ├── v1_raw.md            pre-humanize draft
        ├── v1_reader.md         reader-panel report (markdown)
        ├── v1_reader.json       reader-panel report (machine-readable)
        ├── v1_critic.md
        ├── v1_critic.json
        ├── v1_humanizer.json    humanizer diagnostics
        ├── v2.md                if a revision happened
        ├── ...
        └── final.md             accepted version (best score)
```

## Why this shape

- **Multi-agent over single-prompt** because every stage has a clearly
  different job and we want different temperatures, rubrics, and personas
  for each.
- **Reader and critic separate panels** because engagement (will I keep
  reading?) and craft (is this a good sentence?) are different judgements.
  A book can have good craft and feel boring, or vice versa.
- **Humanizer between draft and judge** because the judges should score
  what the reader will actually see, and we want AI-tells fixed before
  they bias the judge.
- **Revision loop with cap** because the reviser sometimes makes the
  chapter worse; we keep the best draft, not the last one.
- **STATE.json everywhere** because local-LLM pipelines crash, run out of
  RAM, or just take a long time. Resumable is non-negotiable.
- **Markdown for everything** because plain text is the most resilient
  format and renders well on GitHub, in editors, and via export.

## Corpus and retrieval

Three layers under `corpus/`:

1. **`style_cards/`** — fair-use markdown describing modern bestseller
   voices (Sanderson, Abercrombie, Rothfuss, Erikson, Jemisin, Le Guin,
   Royal Road progression conventions).
2. **`craft/`** — beat sheets, magic system templates, dialogue craft,
   show-don't-tell, stakes layering, etc.
3. **`gutenberg/`** — full public-domain fantasy classics downloaded by
   `writer corpus`.

`retrieve_corpus(query, kind=...)` does paragraph-level grep keyed on
extracted keywords. No vector DB — paragraph-level grep is fast,
deterministic, and good enough for the use case (the goal is "find me a
relevant style example for grimdark with weather"; we don't need semantic
embeddings for that).

The Drafter calls `retrieve_corpus` for each chapter with the beat sheet
as the query, pulling 4–6 paragraphs from style/craft + Gutenberg.

## Adding a new agent

1. Add `src/writer_app/<name>.py` with a `run(project, ...)` function.
2. If it makes LLM calls, use `shared.llm.generate` or `generate_json`
   with `role="draft"` (for prose) or `role="judge"` (for scoring).
3. Wire it into `orchestrator.py` at the appropriate point in the loop.
4. Add a test in `tests/test_<name>.py`.
5. Add a section to `WRITER.md` / relevant docs.

## Adding a new remote provider

In `shared/remote.py`:

```python
PROVIDERS = {
    ...,
    "newprovider": {
        "base_url": "...",
        "env_key":  "NEWPROVIDER_API_KEY",
        "tos_url":  "...",
        "privacy_url": "...",
        "default_models": {
            "draft": "...",
            "judge": "...",
        },
        "supports_response_format_json": True,
    },
}
```

Provider must be OpenAI-compatible at `/chat/completions`. If it's not,
add a custom adapter in `_provider_chat` (currently inlined in `chat`).
