# Changelog

All notable changes to writer-app are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] — Unreleased

### Added
- Multi-agent pipeline: Loremaster → Plotter → Drafter → Humanizer →
  Reader Panel → Critic Panel → Reviser → Continuity → Provenance → Export.
- Local-first execution via Ollama with two model roles (`draft`, `judge`).
- Optional remote routing to Groq and Cerebras free tiers with automatic
  fallback to local when offline, when API quota is exhausted, or when the
  user passes `--local-only`.
- Circuit breaker on remote providers (3 consecutive failures → local-only
  for the rest of the run).
- Humanizer with heuristic + LLM AI-tell detection and rewriting.
- Per-chapter audit trail (`PROVENANCE.md`).
- KDP-ready `.docx` and `.epub` export with title/copyright/disclosure
  pages; falls back to `pandoc` when available.
- Streamlit interactive UI (`writer ui`) for upload / refine / automate
  workflows with inline hints.
- Self-extracting `install.sh` build target.
- GitHub Actions: CI on every push, release artefacts on tag push.

### Not yet
- Multi-book continuity enforcement (each book's continuity pass is local).
- Cover generation.
- Voice-audit pass per POV character.
- Windows installer.
