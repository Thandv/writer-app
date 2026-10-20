# Troubleshooting

## `writer: command not found`

The installer didn't add `~/.local/bin` (or `/opt/homebrew/bin`) to your PATH.

```bash
export PATH="$HOME/.local/bin:$PATH"
# Add the same line to ~/.zshrc or ~/.bashrc to persist
```

Or run from source:
```bash
python3 -m writer_app.cli --help
```

## `Cannot reach Ollama`

Ollama is not running. Any `writer` command that needs the local model
stops with exit code 1 and prints this to stderr:

```
writer: Cannot reach Ollama at http://localhost:11434. Run `brew services start ollama`. (...)
```

The run stops at the first failed call. Chapters are never scored as if
the judges had answered. In the UI, the Write tab shows the same message
in red when the pipeline exits. Progress up to that point is in
`STATE.json`, so `writer start` resumes once Ollama is back.

```bash
# macOS
brew services start ollama

# Linux
sudo systemctl start ollama
```

Check it's listening:
```bash
curl -s http://localhost:11434/api/tags
```

Override the endpoint if it's elsewhere:
```bash
export OLLAMA_HOST=http://192.168.1.10:11434
```

## `No usable chat model is pulled in Ollama`

Ollama is running but has no model that can draft or judge prose. Embedding
models (`*embed*`) and vision models (`*vl`) don't count. Pull the defaults:

```bash
ollama pull mistral-nemo:12b
ollama pull qwen2.5:7b
```

If a default isn't pulled but other chat models are, `writer start` and
`writer providers` name the model used instead (e.g.
`(mistral-nemo:12b is not pulled; using qwen2.5-coder:14b. To use it: ollama pull mistral-nemo:12b)`).
It's the first pulled chat model in alphabetical order, which may be a code
model. Pull the default or set `WRITER_DRAFT_MODEL` / `WRITER_JUDGE_MODEL`.

## `Corpus directory not found`

```bash
writer corpus
```

Or if it's installed somewhere unusual:
```bash
export WRITER_CORPUS_DIR=~/.local/share/writer-app/corpus
writer corpus
```

## Drafter outputs are very short / incoherent

Likely the local model is too small. Pull a larger one:

```bash
ollama pull mistral-nemo:12b
export WRITER_DRAFT_MODEL=mistral-nemo:12b
```

Or enable remote drafting via Groq/Cerebras — see [REMOTE.md](REMOTE.md).

## "Model did not return valid JSON after 3 tries"

The judge model is too small or producing markdown around its JSON. Try
a larger judge model:

```bash
ollama pull qwen2.5:14b
export WRITER_JUDGE_MODEL=qwen2.5:14b
```

Or use remote judging (Groq's Llama 3.1 8B is reliable for JSON output):

```bash
export GROQ_API_KEY='gsk_...'
export WRITER_JUDGE_PROVIDER=groq
```

## `Remote groq (...): HTTP 401`

Your API key is invalid or revoked. Check the value:

```bash
echo "${GROQ_API_KEY:0:6}..."
```

The circuit breaker opens immediately on auth errors. Restart your shell
or re-export the corrected key.

## `Remote groq (...): HTTP 429` (rate limited)

You hit the free-tier limit (typically per-minute tokens). Wait a minute
or fall back to local for this run:

```bash
writer start ~/books/my-series --local-only
```

## The pipeline hangs after the Drafter prints "produced N words"

Almost always the judge model is slow. The reader+critic panels run 7
JSON calls per chapter. If each takes 30s on local, that's ~3.5 min per
chapter just for scoring.

Speed up:
- Use a smaller judge model: `export WRITER_JUDGE_MODEL=qwen2.5:7b`
- Or route judge to remote: `export WRITER_JUDGE_PROVIDER=groq`

## Streamlit UI won't start

```bash
pip install 'writer-app[ui]'
```

If it's installed but `writer ui` can't find the UI file, you may be running
from an unusual install location. From a source checkout:

```bash
streamlit run ui/app.py
```

## `MANUSCRIPT.md` is empty or has fewer chapters than expected

The pipeline only includes chapters with a `final.md`. Check chapter status:

```bash
writer status ~/books/my-series
```

Any chapter not at `done` status was interrupted. Resume:

```bash
writer start ~/books/my-series
```

## `writer humanize` returns the input unchanged

The humanizer only rewrites if the AI-score is above the target. If the
chapter scored ≤ 3.5 already, it returns the input. Force a rewrite:

```bash
writer humanize ~/books/my-series book-01/chapter-05/final.md --target 1.0 --passes 1 --write
```

## Export produces .docx that Word complains about

The stdlib DOCX writer is minimal. If you have Word and it shows warnings,
install `pandoc` for a cleaner output:

```bash
brew install pandoc      # macOS
sudo apt install pandoc  # Debian/Ubuntu

writer export ~/books/my-series   # will now use pandoc automatically
```

## KDP rejects my upload citing "unrecognised format"

Use the `.docx` from the export. KDP supports DOCX, EPUB, and KPF. Avoid
uploading the raw `MANUSCRIPT.md`.

## A chapter shows `judge_failed`

No reader or critic returned valid JSON for that chapter's first draft.
Usually the judge model is too small or the remote judge provider is
failing. Nothing is scored as a placeholder 5. The chapter has no
`final.md`, and `writer status` prints the error. Fix the judge (see "Model
did not return valid JSON" above), then run `writer start` again; it
re-drafts the chapter. Three `judge_failed` chapters in a row stop the run
with exit code 1.

If the judges fail on a later revision instead, the best scored draft is
kept as `final.md` with its real score. The error is still recorded in
`judge_error` in `STATE.json`.

## "I want to start over from chapter 5"

Delete the chapter and resume:

```bash
rm -rf ~/books/my-series/book-01/chapter-05
# Edit STATE.json and change that chapter's "status" to "pending"
# (or just delete the chapter entry — it'll be recreated)
writer start ~/books/my-series
```

## "Where did the API key/manuscript go?"

API keys: only in your shell environment, plus the project's `.env` file
if you saved them via the UI (gitignored).

Manuscript: `~/books/<slug>/book-NN/MANUSCRIPT.md`. Nothing is uploaded
anywhere unless you've explicitly set `WRITER_*_PROVIDER` to a remote
provider.

## Anything else

Open an issue: include the output of `writer providers`, the contents of
`STATE.json` (no secrets), and the last 30 lines of the pipeline's output.
