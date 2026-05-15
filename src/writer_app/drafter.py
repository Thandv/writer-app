"""
Drafter Agent

Writes one chapter at a time. Uses the DRAFT model (potentially remote).
"""

from pathlib import Path
from .shared.llm import generate
from .shared.tools import retrieve_corpus
from .shared.memory import BookProject


SYSTEM = """You are the Drafter. You write a single chapter of a fantasy
novel at a time, in finished prose. You do not write summaries, headings,
or notes — only the chapter as a reader would read it.

Constraints:
- Write the chapter in scenes, separated by a blank line and a centred ⁂
  (three asterisks on their own line).
- Stay in the assigned POV. Render their interiority specifically.
- Honour the beat list. Each numbered beat must be visible in the chapter.
- Follow the outcome shape ("Yes-but", "No-and", etc.) at scene level.
- Use specific sensory detail — sight, smell, weather, body, sound.
- Dialogue should reveal character or relationship, not just deliver info.
- Avoid: clichés, filter words on every page, exposition dumps.
- Aim for around {target_words} words. Do not pad. Do not rush.
- Do not write the chapter heading — the pipeline adds it.
- Do not write meta-notes, author commentary, or "End of chapter".

You are writing for an adult fantasy reader. Trust them.
"""


def _retrieve_references(beat_body: str, world_bible: str) -> str:
    blocks = []
    blocks.append(retrieve_corpus(query=beat_body[:1200], kinds="style_cards", k=2))
    blocks.append(retrieve_corpus(query=beat_body[:1200], kinds="craft", k=2))
    blocks.append(retrieve_corpus(
        query=(beat_body[:1200] + "\n" + world_bible[:600])[:2000],
        kinds="gutenberg", k=2,
    ))
    return "\n\n".join(b for b in blocks if b and not b.startswith("No"))


def draft_chapter(
    project: BookProject,
    book_n: int,
    chapter_n: int,
    chapter_title: str,
    beat_body: str,
    previous_chapter_text: str = "",
    revision_note: str = "",
) -> str:
    world_bible = ""
    if project.world_bible_path and Path(project.world_bible_path).exists():
        world_bible = Path(project.world_bible_path).read_text(encoding="utf-8", errors="ignore")

    refs = _retrieve_references(beat_body, world_bible)
    prev_tail = previous_chapter_text[-2500:] if previous_chapter_text else ""

    revision_block = ""
    if revision_note:
        revision_block = f"""
You are REVISING a previous draft of this chapter. Read the critique below
and apply it. Do not throw out what was working — fix what was flagged.
Keep the POV, the beats, and the outcome shape unchanged unless the critique
explicitly demands otherwise.

CRITIQUE:
{revision_note}
"""

    system = SYSTEM.format(target_words=project.target_words_per_chapter)
    user = f"""WORLD BIBLE (truncated):
{world_bible[:6000]}

PREVIOUS CHAPTER (last ~500 words, for continuity):
{prev_tail or "(this is chapter 1 — no prior text)"}

STYLE / CRAFT REFERENCES (use these to inform voice — do not copy):
{refs or "(no references retrieved)"}

CHAPTER TO WRITE:
Book {book_n}, Chapter {chapter_n} — {chapter_title}

Beat sheet for this chapter:
{beat_body}

{revision_block}

Write the chapter now. Prose only.
"""

    text = generate(
        system=system,
        user=user,
        model=project.draft_model,
        role="draft",
        temperature=0.85,
        num_ctx=16384,
        max_tokens=8192,
    )

    cleaned = text.strip()
    if cleaned.lower().startswith("# ") or cleaned.lower().startswith("## chapter"):
        first_nl = cleaned.find("\n")
        if first_nl > 0:
            cleaned = cleaned[first_nl + 1:].lstrip()
    return cleaned


def run(project: BookProject, book_n: int, chapter_n: int,
        chapter_title: str, beat_body: str,
        previous_chapter_text: str = "",
        revision_note: str = "") -> str:
    label = f"Book {book_n:02d} / Ch {chapter_n:02d}"
    mode = "revising" if revision_note else "drafting"
    print(f"  [Drafter] {label} — {mode} …")
    text = draft_chapter(
        project, book_n, chapter_n, chapter_title, beat_body,
        previous_chapter_text=previous_chapter_text,
        revision_note=revision_note,
    )
    print(f"  [Drafter] {label} — produced {len(text.split()):,} words.")
    return text
