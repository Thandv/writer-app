# Installation

writer-app supports macOS and Linux. Windows support is not currently shipped.

## Requirements

- Python 3.10 or later
- [Ollama](https://ollama.com) for local inference (recommended)
- ~10 GB free disk space (mostly for Ollama models)
- 16 GB RAM is enough for the recommended models

Optional:
- `pandoc` for higher-quality DOCX/EPUB export (the pipeline has stdlib
  fallbacks so this is not required)
- A Groq or Cerebras API key (free tier, no card) for higher-quality prose
  drafting via remote 70B Llama

## Option A: Self-extracting installer

Easiest path, no source clone needed.

```bash
curl -fsSL https://github.com/Thandv/writer-app/releases/latest/download/writer-app-install.sh \
  -o writer-app-install.sh
bash writer-app-install.sh
```

What this does:
1. Verifies Python 3.10+ is present.
2. Extracts the source tarball into `~/.local/share/writer-app/`.
3. Creates `~/.local/bin/writer` shim.
4. Prompts you to add `~/.local/bin` to PATH if needed.
5. Builds the reference corpus (style cards + craft notes; Gutenberg
   downloads on demand later).

To uninstall:

```bash
bash ~/.local/share/writer-app/scripts/uninstall.sh
```

## Option B: pip install from source

```bash
git clone https://github.com/Thandv/writer-app.git
cd writer-app
python3 -m pip install -e ".[ui]"
```

`[ui]` pulls Streamlit for the interactive UI. Leave it off for CLI-only.

## Option C: Editable dev install

For developers who want to contribute:

```bash
git clone https://github.com/Thandv/writer-app.git
cd writer-app
make install   # equivalent to: pip install -e ".[dev]"
make test
```

## Install Ollama and pull models

```bash
# macOS
brew install ollama
brew services start ollama

# Linux (any distro)
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama

# Pull the recommended models
ollama pull qwen2.5:7b           # judge model — fast, structured
ollama pull mistral-nemo:12b     # draft model — best local prose on 16 GB
```

You can use any other Ollama models by setting `WRITER_DRAFT_MODEL` and
`WRITER_JUDGE_MODEL`. See [CONFIG.md](CONFIG.md).

## Verify the installation

```bash
writer --help
writer providers
```

`writer providers` shows what models are pulled, what's reachable, and
what (if anything) is configured for remote.

## Build the reference corpus

One-time, ~30–90 seconds:

```bash
writer corpus
```

This writes ~16 style cards and craft notes to disk, then downloads ~17
public-domain fantasy classics (Dunsany, Morris, MacDonald, Eddison, Howard,
Lovecraft, Mirrlees, Le Morte d'Arthur, etc.) from Project Gutenberg.

Skip the Gutenberg downloads (only style + craft):

```bash
writer corpus --no-gutenberg
```

## Next steps

- [QUICKSTART.md](QUICKSTART.md) — write your first book end-to-end
- [CLI.md](CLI.md) — every `writer …` subcommand
- [UI.md](UI.md) — the Streamlit interactive UI
