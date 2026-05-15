"""
Rubric definitions used by the reader and critic panels.

Scores are 1-10 integers. We weight categories so that prose and pacing
(which affect every line) count more than e.g. world-consistency.

The threshold for "good enough to move on" lives on BookProject.min_chapter_score
(default 7.5). The Reviser loop keeps revising a chapter until it crosses
the threshold or hits BookProject.max_revisions_per_chapter.
"""

# ── Critic panel: structural rubric, scored 1-10 each ────────────────────
CRITIC_RUBRIC = {
    "prose_quality":      {"weight": 1.5, "desc": "Sentence-level craft: imagery, rhythm, word choice, variety."},
    "pacing":             {"weight": 1.3, "desc": "Scene tension and momentum. No sag, no rush."},
    "character_voice":    {"weight": 1.2, "desc": "POV character feels specific, internally consistent, alive."},
    "dialogue":           {"weight": 1.0, "desc": "Sounds like people, advances plot/character, no exposition dumps."},
    "stakes_and_tension": {"weight": 1.2, "desc": "Reader feels something is at risk, scene-by-scene."},
    "structure":          {"weight": 1.0, "desc": "Scene goal, conflict, outcome arc is present and works."},
    "showing_vs_telling": {"weight": 1.0, "desc": "Concrete sensory detail vs summary/exposition balance."},
    "world_integration":  {"weight": 0.8, "desc": "World details surface organically; no info-dumps."},
}

# ── Reader panel: emotional / engagement rubric, scored 1-10 each ────────
READER_RUBRIC = {
    "engagement":     {"weight": 1.5, "desc": "Did you want to keep reading?"},
    "emotional_pull": {"weight": 1.3, "desc": "Did you feel something? Tension, awe, dread, delight."},
    "clarity":        {"weight": 1.0, "desc": "Could you follow what was happening and who was doing it?"},
    "character_care": {"weight": 1.2, "desc": "Do you care what happens to these people?"},
    "freshness":      {"weight": 0.9, "desc": "Does it feel like familiar genre territory or surprising?"},
    "promise_payoff": {"weight": 1.0, "desc": "Did this chapter deliver on what its opening promised?"},
}

# ── Reader personas: who's reading and judging ───────────────────────────
READER_PERSONAS = [
    {
        "id": "epic-fan",
        "name": "Mara",
        "blurb": ("A 34-year-old epic fantasy lifer. Grew up on Tolkien and Robert Jordan, "
                  "moved on to Erikson, Sanderson, and Hobb. Wants worldbuilding that "
                  "rewards close reading, but loses patience with prologue-style info-dumps. "
                  "Values prose that earns its length. Will DNF a book that doesn't earn "
                  "its first chapter."),
    },
    {
        "id": "grimdark-fan",
        "name": "Theo",
        "blurb": ("A 29-year-old who reads Abercrombie, Lawrence, Bakker, R. Scott Bakker, "
                  "and dark Erikson. Wants morally compromised POVs with sharp interior "
                  "voices, dark humour, real bodily cost. Allergic to chosen-one tropes "
                  "played straight and to virtuous protagonists with no shadow."),
    },
    {
        "id": "progression-fan",
        "name": "Lin",
        "blurb": ("A 24-year-old who came up through Royal Road megahits — Cradle, He Who "
                  "Fights With Monsters, Mother of Learning, Dungeon Crawler Carl. Wants "
                  "clear power-system tiers, visible growth, satisfying training/breakthrough "
                  "beats. Tolerates rougher prose if the system and momentum deliver. Loses "
                  "interest fast when stakes feel static."),
    },
    {
        "id": "casual-reader",
        "name": "Aubrey",
        "blurb": ("A 41-year-old who reads broadly — literary fiction, mystery, occasional "
                  "fantasy (Le Guin, Jemisin, Clarke's Piranesi). Will bounce off a chapter "
                  "that assumes too much genre context. Cares deeply about character voice "
                  "and sentence-level prose. A great proxy for whether the book reads as "
                  "real literature, not just genre product."),
    },
]

# ── Critic personas ──────────────────────────────────────────────────────
CRITIC_PERSONAS = [
    {
        "id": "developmental-editor",
        "name": "The Developmental Editor",
        "blurb": ("Twenty years editing genre fiction at a major imprint. Thinks in scenes, "
                  "beats, and arcs. Will flag scenes with no goal, scenes that resolve too "
                  "easily, dialogue that exists only for exposition, and chapters that don't "
                  "earn their length."),
    },
    {
        "id": "prose-critic",
        "name": "The Prose Critic",
        "blurb": ("A literary critic who reviews for The Atlantic. Reads every sentence for "
                  "rhythm, image, and freshness. Notices clichés, mixed metaphors, said-bookisms, "
                  "filter words ('she felt', 'he saw'), and limp verbs. Quotes specific lines."),
    },
    {
        "id": "structure-critic",
        "name": "The Structure Critic",
        "blurb": ("A story consultant trained on Save-the-Cat, Story Grid, and Brandon "
                  "Sanderson's lectures. Identifies scene structure (goal/conflict/outcome), "
                  "tension curves, and where promises were made vs paid off."),
    },
]


def weighted_average(scores: dict, rubric: dict) -> float:
    """Compute the weighted average of a {category: 1-10} score dict."""
    total_w, total_s = 0.0, 0.0
    for cat, meta in rubric.items():
        if cat in scores:
            try:
                s = float(scores[cat])
            except (TypeError, ValueError):
                continue
            s = max(1.0, min(10.0, s))
            w = meta["weight"]
            total_w += w
            total_s += s * w
    return round(total_s / total_w, 2) if total_w else 0.0


def rubric_block(rubric: dict) -> str:
    """Return a markdown block listing each rubric category for prompts."""
    lines = []
    for cat, meta in rubric.items():
        lines.append(f"- **{cat}** (1-10): {meta['desc']}")
    return "\n".join(lines)
