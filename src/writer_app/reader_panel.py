"""
Reader Panel

Four simulated reader personas read each chapter and produce numeric rubric
scores plus free-text reactions.
"""

from .shared.llm import generate_json, OllamaUnreachableError
from .shared.rubric import (
    READER_RUBRIC, READER_PERSONAS, weighted_average, rubric_block,
)
from .shared.memory import BookProject


SYSTEM_TEMPLATE = """You are a fantasy reader, NOT a writer or editor.
You read like a real reader: for pleasure, for tension, for the next chapter.
You are not assessing craft in the abstract — you are reporting your experience.

Your reader profile:
{profile}

You will be given a chapter to read. After reading, return ONLY a JSON object
with the following keys:

{{
  "scores": {{
    "engagement":     <1-10 int>,
    "emotional_pull": <1-10 int>,
    "clarity":        <1-10 int>,
    "character_care": <1-10 int>,
    "freshness":      <1-10 int>,
    "promise_payoff": <1-10 int>
  }},
  "would_keep_reading": <true | false>,
  "landed":   "<one or two specific things that worked, in your voice>",
  "missed":   "<one or two specific things that didn't, in your voice>",
  "verdict":  "<one short sentence summarising your reaction>"
}}

Score 1 = couldn't finish, 5 = competent but flat, 7 = good chapter,
9 = great chapter, 10 = the kind of chapter that makes you tell a friend.
Be honest. If something is mediocre, say 5. Don't be generous.

Rubric:
{rubric}
"""


def _score_with_persona(persona: dict, chapter_text: str, judge_model: str) -> dict:
    sys = SYSTEM_TEMPLATE.format(
        profile=f"{persona['name']} — {persona['blurb']}",
        rubric=rubric_block(READER_RUBRIC),
    )
    user = f"Chapter to read:\n\n{chapter_text}"
    try:
        data = generate_json(sys, user, model=judge_model, role="judge",
                             temperature=0.5, num_ctx=16384)
    except OllamaUnreachableError:
        raise
    except Exception as e:
        return {
            "persona_id":   persona["id"],
            "persona_name": persona["name"],
            "scores": {k: 5 for k in READER_RUBRIC},
            "weighted": 5.0,
            "would_keep_reading": False,
            "landed": "",
            "missed": f"(reader did not return valid feedback: {e})",
            "verdict": "(error)",
        }
    scores = data.get("scores", {})
    return {
        "persona_id":   persona["id"],
        "persona_name": persona["name"],
        "scores":   scores,
        "weighted": weighted_average(scores, READER_RUBRIC),
        "would_keep_reading": bool(data.get("would_keep_reading", False)),
        "landed":  data.get("landed", "").strip(),
        "missed":  data.get("missed", "").strip(),
        "verdict": data.get("verdict", "").strip(),
    }


def run(project: BookProject, chapter_text: str) -> dict:
    print("  [Reader Panel] Four readers reading …")
    reports = []
    for persona in READER_PERSONAS:
        rep = _score_with_persona(persona, chapter_text, project.judge_model)
        weighted = rep["weighted"]
        keep = "→ keeps reading" if rep["would_keep_reading"] else "→ DNF"
        print(f"    [{persona['name']:8s}] {weighted:.2f}  {keep}")
        reports.append(rep)

    if reports:
        avg = round(sum(r["weighted"] for r in reports) / len(reports), 2)
    else:
        avg = 0.0
    keep_pct = round(
        100 * sum(1 for r in reports if r["would_keep_reading"]) / max(1, len(reports)),
    )
    print(f"  [Reader Panel] Average weighted score: {avg}  ({keep_pct}% would keep reading)")
    return {"reports": reports, "average_score": avg, "keep_reading_pct": keep_pct}


def render_markdown(panel_result: dict) -> str:
    out = ["# Reader Panel Report", ""]
    out.append(f"**Average weighted score:** {panel_result['average_score']}  ")
    out.append(f"**Would keep reading:** {panel_result['keep_reading_pct']}%")
    out.append("")
    for r in panel_result["reports"]:
        out.append(f"## {r['persona_name']}  (weighted {r['weighted']})")
        scores = r.get("scores", {})
        for k in READER_RUBRIC:
            out.append(f"- **{k}:** {scores.get(k, '—')}")
        out.append("")
        out.append(f"**Would keep reading:** {r['would_keep_reading']}")
        out.append("")
        out.append(f"**What landed:** {r['landed']}")
        out.append("")
        out.append(f"**What didn't:** {r['missed']}")
        out.append("")
        out.append(f"**Verdict:** {r['verdict']}")
        out.append("")
    return "\n".join(out)
