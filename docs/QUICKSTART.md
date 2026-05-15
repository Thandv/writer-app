# Quickstart — your first book end-to-end

Assumes you've already installed writer-app and have Ollama running with at
least `qwen2.5:7b` pulled. If not, see [INSTALL.md](INSTALL.md).

## 1. Initialise a project

```bash
writer init "The Bone Empire" \
  --author "Real Name" \
  --pen-name "Pen Name" \
  --chapters 30 \
  --words 3000 \
  --threshold 7.5 \
  --max-revisions 3
```

This creates `~/books/the-bone-empire/` with:

```
the-bone-empire/
  STATE.json          pipeline state
  bible/              ← you drop your worldbuilding here
    README.md         (auto-written; tells you what to drop in)
```

## 2. Drop your bible

Put anything you have into `~/books/the-bone-empire/bible/` as `.md` or
`.txt` files. Suggested but not required:

```
bible/
  world.md         geography, climate, history
  magic.md         power system, costs, rules, failure modes
  characters.md    POV characters: drive, wound, voice
  factions.md      political/cultural groups and their conflicts
  plot.md          anything you already know about where the story goes
```

The Loremaster treats your files as authoritative — it never overrides
your named characters, factions, or magic rules. It organises them into
a single `WORLD_BIBLE.md` and fills small mundane gaps (weather, minor
place names, sensory texture) consistently with what you wrote.

## 3. Start writing

```bash
writer start ~/books/the-bone-empire
```

The pipeline now:
1. **Loremaster** consolidates your bible → `WORLD_BIBLE.md`
2. **Plotter** generates `BOOK_OUTLINE.md` with all chapters as beat sheets
3. For each chapter:
   - **Drafter** writes a first draft
   - **Humanizer** detects AI-tells and rewrites
   - **Reader Panel** (4 personas) and **Critic Panel** (3 personas) score it
   - If below `--threshold`: **Reviser** re-drafts; loop up to `--max-revisions`
   - Best draft → `chapter-NN/final.md`
4. **Continuity Pass** → `CONTINUITY_REPORT.md`
5. **Provenance Pass** → `PROVENANCE.md`
6. **MANUSCRIPT.md** assembled

This will take several hours on M2 16GB for a default 30-chapter novel.
Kill it any time — re-running `writer start` resumes from the next un-done
chapter.

To follow progress from a second terminal:

```bash
writer status ~/books/the-bone-empire
```

## 4. (Optional) Light revision

Read through `book-01/MANUSCRIPT.md`. For any chapter that bothers you,
drop your revised version at:

```
~/books/the-bone-empire/book-01/revisions/chapter-05.md
```

The export step prefers your revision file over the AI's `final.md`.
No need to re-run the pipeline.

You can also re-run the humanizer on a single chapter:

```bash
writer humanize ~/books/the-bone-empire book-01/chapter-05/final.md --write
```

## 5. Export

```bash
writer export ~/books/the-bone-empire
```

Produces, in `book-01/`:
- `the-bone-empire.docx` — KDP-ready Word doc
- `the-bone-empire.epub` — EPUB

Both include a title page, copyright page, AI disclosure page, and your
chapters.

## 6. Get the KDP disclosure text

```bash
writer disclosure ~/books/the-bone-empire
```

Prints the exact answer to give Amazon's "AI use" question on the upload
form. Also writes `KDP_DISCLOSURE.md` at the project root.

## 7. Upload to KDP

- Log in to [kdp.amazon.com](https://kdp.amazon.com).
- Create a new title; upload the `.docx`.
- When asked about AI use, **answer yes — AI-generated text**.
- Add your own cover; KDP does not generate one.
- Set price, KU enrolment, categories, keywords.

See [PUBLISHING.md](PUBLISHING.md) for the full self-pub checklist including
copyright considerations.

---

## What if I want to use a remote provider for better prose?

After step 1 but before step 3:

```bash
# Sign up at https://console.groq.com (no credit card)
export GROQ_API_KEY='gsk_...'
export WRITER_DRAFT_PROVIDER=groq   # 70B Llama for prose
export WRITER_JUDGE_PROVIDER=local  # keep judging on local Ollama

writer providers   # confirm
writer start ~/books/the-bone-empire
```

If the internet drops mid-run, the pipeline falls back to local Ollama
automatically. See [REMOTE.md](REMOTE.md).
