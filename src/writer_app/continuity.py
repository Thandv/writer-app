"""
Continuity Checker

Runs after a book's chapters are all finalised. Looks for named-character
drift, magic-rule violations, timeline contradictions, and unpaid promises.
"""

import re
from pathlib import Path
from .shared.llm import generate_json
from .shared.memory import BookProject


SYSTEM = """You are the Continuity Editor for a fantasy novel.
You read a full book manuscript and the world bible, and you flag continuity
issues a reader or copy-editor would catch. You do NOT rewrite the book.

You return ONLY a JSON object with this shape:

{
  "issues": [
    {
      "chapter":  <chapter number int, or 0 if unclear>,
      "severity": "high" | "medium" | "low",
      "kind":     "name_drift" | "magic_rule" | "timeline" | "geography" | "promise_unpaid" | "other",
      "summary":  "<one line>",
      "evidence": "<short quote or beat reference>",
      "fix":      "<concrete suggestion>"
    }
  ],
  "overall_grade": <1-10 int — overall continuity quality>,
  "summary":       "<one paragraph: state of the manuscript>"
}

Score honestly. A clean manuscript can score 9 or 10. A messy one with name
drift and timeline contradictions should score 4 or 5.
"""


def _gather_manuscript(project: BookProject, book_n: int) -> str:
    book_dir = project.book_dir(book_n)
    parts = []
    for ch_dir in sorted(book_dir.glob("chapter-*")):
        final = ch_dir / "final.md"
        if not final.exists():
            continue
        n_match = re.search(r"chapter-(\d+)", ch_dir.name)
        n = int(n_match.group(1)) if n_match else 0
        parts.append(f"\n\n===== CHAPTER {n} =====\n\n{final.read_text(encoding='utf-8')}")
    return "".join(parts)


def run(project: BookProject, book_n: int) -> dict:
    print(f"  [Continuity] Reviewing Book {book_n:02d} …")
    manuscript = _gather_manuscript(project, book_n)
    if not manuscript.strip():
        print("  [Continuity] No chapters found — skipping.")
        return {"issues": [], "overall_grade": 0, "summary": "no chapters"}

    world_bible = ""
    if project.world_bible_path and Path(project.world_bible_path).exists():
        world_bible = Path(project.world_bible_path).read_text(encoding="utf-8", errors="ignore")

    BUDGET = 90_000
    if len(manuscript) > BUDGET:
        manuscript = manuscript[:BUDGET] + "\n[... manuscript truncated for review ...]"

    user = f"""WORLD BIBLE:
{world_bible[:12000]}

FULL MANUSCRIPT (Book {book_n}):
{manuscript}
"""
    try:
        data = generate_json(SYSTEM, user, model=project.judge_model, role="judge",
                             temperature=0.2, num_ctx=32768)
    except Exception as e:
        print(f"  [Continuity] Could not parse continuity report: {e}")
        data = {"issues": [], "overall_grade": 0, "summary": str(e)}

    issues = data.get("issues", [])
    grade  = data.get("overall_grade", 0)
    print(f"  [Continuity] {len(issues)} issues, overall grade {grade}/10")

    report_lines = [
        f"# Continuity Report — Book {book_n:02d}",
        "",
        f"**Overall grade:** {grade}/10",
        "",
        data.get("summary", ""),
        "",
        "## Issues",
        "",
    ]
    if not issues:
        report_lines.append("_No issues found._")
    for issue in issues:
        report_lines.append(
            f"- **[{issue.get('severity','?')}]** Ch {issue.get('chapter','?')} — "
            f"{issue.get('kind','?')}: {issue.get('summary','')}"
        )
        if issue.get("evidence"):
            report_lines.append(f"  - Evidence: {issue['evidence']}")
        if issue.get("fix"):
            report_lines.append(f"  - Fix: {issue['fix']}")
        report_lines.append("")

    report_path = project.book_dir(book_n) / "CONTINUITY_REPORT.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"  [Continuity] Wrote {report_path}")
    return data
