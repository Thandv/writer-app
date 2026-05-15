"""
Loremaster Agent

Reads the user's bible/ folder and produces WORLD_BIBLE.md — a consolidated
canon document the rest of the pipeline uses as ground truth.
"""

from pathlib import Path
from .shared.llm import generate, run_agent
from .shared.tools import WRITE_FILE, READ_FILE, LIST_FILES, HANDLERS
from .shared.memory import BookProject


SYSTEM = """You are the Loremaster for a fantasy book series.
You receive the author's bible (worldbuilding, character, magic, geography, factions, plot notes).

Your job is to:
1. READ everything the author provided. Treat it as canon.
2. ORGANISE the canon into a single WORLD_BIBLE.md with these sections:
   - Premise & Tone
   - World & Geography
   - Magic / Power System (rules, costs, limits, failure modes)
   - Factions & Politics
   - Major Characters (one paragraph each: drive, wound, voice)
   - Cultures & Customs
   - Timeline / Historical Context
   - Glossary of Proper Nouns
3. FILL GAPS where the bible is silent — but ONLY fill gaps that are needed
   to write the story. Do not invent named characters or factions the author
   did not include. Do invent: weather patterns, minor customs, mundane place
   names, sensory texture, the feel of streets.
4. FLAG conflicts you find inside the bible under "## Open Questions".

NEVER override the author's named characters, factions, or named magical rules.

Output WORLD_BIBLE.md by calling write_file. Be concrete and dense —
this document is read by every later agent.
"""


def run(project: BookProject) -> BookProject:
    print("  [Loremaster] Reading author's bible …")

    bible_dir = Path(project.output_dir) / project.bible_dir
    if not bible_dir.exists() or not any(bible_dir.iterdir()):
        print(f"  [Loremaster] No files in {bible_dir} — generating a fresh bible "
              f"from the project title alone.")
        bible_files = []
    else:
        bible_files = sorted(
            p for p in bible_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in {".md", ".txt"}
        )

    project.user_bible_files = [str(p) for p in bible_files]

    bible_contents = []
    for p in bible_files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = p.relative_to(bible_dir)
        bible_contents.append(f"--- FILE: {rel} ---\n{text}")

    bible_blob = "\n\n".join(bible_contents) if bible_contents else "(no files provided)"

    out_path = Path(project.output_dir) / "WORLD_BIBLE.md"

    task = f"""Project title: {project.title}

Author's bible:

{bible_blob}

Produce the consolidated WORLD_BIBLE.md and save it to:
{out_path}

Use the write_file tool to save. The document should be long and detailed
(aim for 2000-4000 words) but every paragraph should be load-bearing.
"""

    def on_call(name, args):
        if name == "write_file":
            print(f"    [write] {args.get('path','')}")
        else:
            print(f"    [{name}]")

    run_agent(
        system=SYSTEM,
        user=task,
        model=project.judge_model,
        tools=[WRITE_FILE, READ_FILE, LIST_FILES],
        handlers={k: HANDLERS[k] for k in ("write_file", "read_file", "list_files")},
        on_tool_call=on_call,
        temperature=0.4,
        num_ctx=16384,
    )

    if out_path.exists():
        project.world_bible_path = str(out_path)
        print(f"  [Loremaster] Wrote {out_path.name} "
              f"({out_path.stat().st_size:,} bytes)\n")
    else:
        print("  [Loremaster] Tool call missed — falling back to direct generation.")
        body = generate(
            SYSTEM + "\nReturn ONLY the markdown content for WORLD_BIBLE.md.",
            task,
            model=project.judge_model,
            temperature=0.4,
            num_ctx=16384,
        )
        out_path.write_text(body, encoding="utf-8")
        project.world_bible_path = str(out_path)
        print(f"  [Loremaster] Wrote {out_path.name} via fallback.\n")

    project.stage = "loremaster_done"
    project.save()
    return project
