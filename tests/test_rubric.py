"""Tests for shared.rubric — weighted averages, personas, rubric_block."""

from writer_app.shared.rubric import (
    CRITIC_RUBRIC, READER_RUBRIC,
    READER_PERSONAS, CRITIC_PERSONAS,
    weighted_average, rubric_block,
)


# ── weighted_average ──────────────────────────────────────────────────────

def test_weighted_average_all_sevens():
    scores = {k: 7 for k in CRITIC_RUBRIC}
    assert weighted_average(scores, CRITIC_RUBRIC) == 7.0


def test_weighted_average_clamps_above_ten():
    scores = {k: 15 for k in READER_RUBRIC}
    # 15 → clamped to 10
    assert weighted_average(scores, READER_RUBRIC) == 10.0


def test_weighted_average_clamps_below_one():
    scores = {k: 0 for k in READER_RUBRIC}
    # 0 → clamped to 1
    assert weighted_average(scores, READER_RUBRIC) == 1.0


def test_weighted_average_empty_returns_zero():
    assert weighted_average({}, READER_RUBRIC) == 0.0


def test_weighted_average_handles_partial_scores():
    """If only some categories are scored, weighted average uses only those."""
    only_some = {"engagement": 9, "clarity": 5}
    avg = weighted_average(only_some, READER_RUBRIC)
    # Manual calc: (9*1.5 + 5*1.0) / (1.5+1.0) = 18.5/2.5 = 7.4
    assert avg == 7.4


def test_weighted_average_ignores_non_numeric():
    """Non-numeric values should be skipped silently."""
    mixed = {"engagement": 8, "clarity": "not a number", "emotional_pull": 6}
    avg = weighted_average(mixed, READER_RUBRIC)
    # Should only use engagement (1.5) and emotional_pull (1.3)
    expected = (8 * 1.5 + 6 * 1.3) / (1.5 + 1.3)
    assert avg == round(expected, 2)


def test_weighted_average_rounded_to_two_decimals():
    """Result is always rounded to 2 decimal places."""
    scores = {k: 7 for k in CRITIC_RUBRIC}
    scores["prose_quality"] = 8  # change one
    result = weighted_average(scores, CRITIC_RUBRIC)
    # Must be at most 2 decimals
    decimals = str(result).split(".")[-1] if "." in str(result) else ""
    assert len(decimals) <= 2


# ── rubric_block ──────────────────────────────────────────────────────────

def test_rubric_block_lists_every_category():
    block = rubric_block(CRITIC_RUBRIC)
    for category in CRITIC_RUBRIC:
        assert category in block


def test_rubric_block_includes_descriptions():
    block = rubric_block(READER_RUBRIC)
    # Each rubric entry has a description; should appear in the block
    for meta in READER_RUBRIC.values():
        assert meta["desc"] in block


# ── personas ──────────────────────────────────────────────────────────────

def test_reader_personas_unique_ids():
    ids = [p["id"] for p in READER_PERSONAS]
    assert len(ids) == len(set(ids)), "Reader persona ids must be unique"


def test_critic_personas_unique_ids():
    ids = [p["id"] for p in CRITIC_PERSONAS]
    assert len(ids) == len(set(ids)), "Critic persona ids must be unique"


def test_personas_have_required_fields():
    for p in READER_PERSONAS + CRITIC_PERSONAS:
        assert "id" in p and p["id"]
        assert "name" in p and p["name"]
        assert "blurb" in p and len(p["blurb"]) > 50


def test_four_reader_personas_three_critic_personas():
    """The pipeline assumes these counts in scoring code — pin them."""
    assert len(READER_PERSONAS) == 4
    assert len(CRITIC_PERSONAS) == 3


def test_rubric_weights_are_positive_floats():
    for rubric in (CRITIC_RUBRIC, READER_RUBRIC):
        for cat, meta in rubric.items():
            assert isinstance(meta["weight"], (int, float))
            assert meta["weight"] > 0, f"{cat} has non-positive weight"
