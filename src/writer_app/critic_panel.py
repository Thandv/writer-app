"""
Critic Panel

Three simulated critics review each chapter at the craft level and return
rubric scores plus structured critiques.
"""

from .shared.llm import generate_json, OllamaUnreachableError
from .shared.rubric import (
    CRITIC_RUBRIC, CRITIC_PERSONAS, weighted_average, rubric_block,
    judged_average, judged_reports, failed_judges_note,
)
from .shared.memory import BookProject


SYSTEM_TEMPLATE = """You are a working critic of fantasy fiction.
Your role: {role}

Your style and concerns:
{profile}

You are reviewing a single chapter. Be specific. Quote lines or reference
beats when you can. Do not hedge. A vague critique is useless.

Return ONLY a JSON object with this exact shape:

{{
  "scores": {{
    "prose_quality":      <1-10 int>,
    "pacing":             <1-10 int>,
    "character_voice":    <1-10 int>,
    "dialogue":           <1-10 int>,
    "stakes_and_tension": <1-10 int>,
    "structure":          <1-10 int>,
    "showing_vs_telling": <1-10 int>,
    "world_integration":  <1-10 int>
  }},
  "strengths":   ["<short bullet>", "<short bullet>"],
  "weaknesses":  ["<short bullet>", "<short bullet>"],
  "line_notes":  [
    {{"quote": "<a specific line from the chapter>", "note": "<what's wrong or right>"}}
  ],
  "directive":  "<one paragraph: what to change in the next revision>"
}}

Score honestly: 5 = competent but flat, 7 = good, 9 = great. Be willing to
give 4 or 3 when warranted. Generosity wastes the author's time.

Rubric:
{rubric}
"""


def _critique_with_persona(persona: dict, chapter_text: str,
                           beat_body: str, judge_model: str) -> dict:
    sys = SYSTEM_TEMPLATE.format(
        role=persona["name"],
        profile=persona["blurb"],
        rubric=rubric_block(CRITIC_RUBRIC),
    )
    user = f"""The chapter's planned beats:
{beat_body}

The chapter:
{chapter_text}
"""
    try:
        data = generate_json(sys, user, model=judge_model, role="judge",
                             temperature=0.4, num_ctx=16384)
    except OllamaUnreachableError:
        raise
    except Exception as e:
        return {
            "persona_id":   persona["id"],
            "persona_name": persona["name"],
            "judge_failed": True,
            "error":        str(e),
        }
    scores = data.get("scores", {})
    return {
        "persona_id":   persona["id"],
        "persona_name": persona["name"],
        "judge_failed": False,
        "scores":     scores,
        "weighted":   weighted_average(scores, CRITIC_RUBRIC),
        "strengths":  data.get("strengths", []),
        "weaknesses": data.get("weaknesses", []),
        "line_notes": data.get("line_notes", []),
        "directive":  data.get("directive", "").strip(),
    }


def run(project: BookProject, chapter_text: str, beat_body: str) -> dict:
    print("  [Critic Panel] Three critics reviewing …")
    reports = []
    for persona in CRITIC_PERSONAS:
        rep = _critique_with_persona(persona, chapter_text, beat_body, project.judge_model)
        if rep["judge_failed"]:
            print(f"    [{persona['name'][:24]:24s}] judge failed: {rep['error'][:120]}")
        else:
            print(f"    [{persona['name'][:24]:24s}] {rep['weighted']:.2f}")
        reports.append(rep)

    judged = len(judged_reports(reports))
    avg = judged_average(reports)
    failed = len(reports) - judged
    if avg is None:
        print("  [Critic Panel] judge failed: no critic returned valid feedback")
    else:
        print(f"  [Critic Panel] Average weighted score: {avg}  "
              f"({judged} judged, {failed} failed)")
    return {"reports": reports, "average_score": avg, "judged": judged, "failed": failed}


def render_markdown(panel_result: dict) -> str:
    out = ["# Critic Panel Report", ""]
    if panel_result["average_score"] is None:
        out.append("**Judge failed:** no critic returned valid feedback.")
    else:
        out.append(f"**Average weighted score:** {panel_result['average_score']}")
    out.append("")
    note = failed_judges_note(panel_result["reports"])
    if note:
        out += [note, ""]
    for r in judged_reports(panel_result["reports"]):
        out.append(f"## {r['persona_name']}  (weighted {r['weighted']})")
        scores = r.get("scores", {})
        for k in CRITIC_RUBRIC:
            out.append(f"- **{k}:** {scores.get(k, '—')}")
        out.append("")
        if r["strengths"]:
            out.append("**Strengths**")
            for s in r["strengths"]:
                out.append(f"- {s}")
            out.append("")
        if r["weaknesses"]:
            out.append("**Weaknesses**")
            for w in r["weaknesses"]:
                out.append(f"- {w}")
            out.append("")
        if r["line_notes"]:
            out.append("**Line notes**")
            for ln in r["line_notes"]:
                quote = ln.get("quote", "").strip()
                note  = ln.get("note", "").strip()
                if quote or note:
                    out.append(f"- > {quote}")
                    out.append(f"  — {note}")
            out.append("")
        if r["directive"]:
            out.append("**Revision directive**")
            out.append(r["directive"])
            out.append("")
    return "\n".join(out)


def build_revision_note(reader_panel: dict, critic_panel: dict) -> str:
    parts = []
    parts.append("## Critic directives")
    for r in judged_reports(critic_panel["reports"]):
        if r["directive"]:
            parts.append(f"- ({r['persona_name']}) {r['directive']}")
    parts.append("")
    parts.append("## Specific weaknesses")
    for r in judged_reports(critic_panel["reports"]):
        for w in r["weaknesses"][:3]:
            parts.append(f"- {w}")
    parts.append("")
    parts.append("## Line-level notes")
    for r in judged_reports(critic_panel["reports"]):
        for ln in r["line_notes"][:3]:
            q, n = ln.get("quote", "").strip(), ln.get("note", "").strip()
            if q and n:
                parts.append(f"- \"{q}\" → {n}")
    parts.append("")
    parts.append("## Reader reactions to address")
    for r in judged_reports(reader_panel["reports"]):
        if r["missed"]:
            parts.append(f"- ({r['persona_name']}) {r['missed']}")
    return "\n".join(parts)
