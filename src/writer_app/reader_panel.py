"""
Reader Panel

Four simulated reader personas read each chapter and produce numeric rubric
scores plus free-text reactions.
"""

from .shared.llm import generate_json, OllamaUnreachableError
from .shared.rubric import (
    READER_RUBRIC, READER_PERSONAS, weighted_average, rubric_block,
    judged_average, judged_reports, failed_judges_note,
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
        scores = data.get("scores", {})
        weighted = weighted_average(scores, READER_RUBRIC)
        if not weighted:  # scores are clamped to >= 1, so 0.0 means none were numeric
            raise ValueError("judge returned no numeric rubric scores")
    except OllamaUnreachableError:
        raise
    except Exception as e:
        return {
            "persona_id":   persona["id"],
            "persona_name": persona["name"],
            "judge_failed": True,
            "error":        str(e),
        }
    return {
        "persona_id":   persona["id"],
        "persona_name": persona["name"],
        "judge_failed": False,
        "scores":   scores,
        "weighted": weighted,
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
        if rep["judge_failed"]:
            print(f"    [{persona['name']:8s}] judge failed: {rep['error'][:120]}")
        else:
            keep = "→ keeps reading" if rep["would_keep_reading"] else "→ DNF"
            print(f"    [{persona['name']:8s}] {rep['weighted']:.2f}  {keep}")
        reports.append(rep)

    judged = judged_reports(reports)
    avg = judged_average(reports)
    keep_pct = (
        round(100 * sum(1 for r in judged if r["would_keep_reading"]) / len(judged))
        if judged else None
    )
    failed = len(reports) - len(judged)
    if avg is None:
        print("  [Reader Panel] judge failed: no reader returned valid feedback")
    else:
        print(f"  [Reader Panel] Average weighted score: {avg}  ({keep_pct}% would keep "
              f"reading; {len(judged)} judged, {failed} failed)")
    return {"reports": reports, "average_score": avg, "keep_reading_pct": keep_pct,
            "judged": len(judged), "failed": failed}


def render_markdown(panel_result: dict) -> str:
    out = ["# Reader Panel Report", ""]
    if panel_result["average_score"] is None:
        out.append("**Judge failed:** no reader returned valid feedback.")
    else:
        out.append(f"**Average weighted score:** {panel_result['average_score']}  ")
        out.append(f"**Would keep reading:** {panel_result['keep_reading_pct']}%")
    out.append("")
    note = failed_judges_note(panel_result["reports"])
    if note:
        out += [note, ""]
    for r in judged_reports(panel_result["reports"]):
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
