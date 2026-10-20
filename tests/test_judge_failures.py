"""A judge that fails is recorded as a failure, never as a score of 5.

The real reader/critic panels run with generate_json stubbed; every other
agent uses the stubs from test_orchestrator_e2e. All chapter text is invented.
"""

import json
import sys

import pytest

from writer_app import cli, critic_panel, orchestrator, reader_panel, reviser
from writer_app.shared import corpus as corpus_mod
from writer_app.shared import llm as llm_mod
from writer_app.shared import remote as remote_mod
from writer_app.shared.memory import BookProject
from writer_app.shared.rubric import CRITIC_RUBRIC, READER_RUBRIC

from .test_orchestrator_e2e import mocked_pipeline  # noqa: F401  (fixture)

REAL_READER_RUN = reader_panel.run
REAL_CRITIC_RUN = critic_panel.run
JUDGE_CALLS_PER_ITERATION = 7   # 4 readers + 3 critics


def _scores_json(score):
    return {"scores": {k: score for k in {**READER_RUBRIC, **CRITIC_RUBRIC}},
            "would_keep_reading": True, "directive": "tighten the middle"}


def _judges(monkeypatch, behaviour):
    """Install real panels whose generate_json calls `behaviour(call_index)`."""
    calls = {"n": 0}

    def fake_generate_json(*a, **k):
        i = calls["n"]
        calls["n"] += 1
        return behaviour(i)
    monkeypatch.setattr(reader_panel, "run", REAL_READER_RUN)
    monkeypatch.setattr(critic_panel, "run", REAL_CRITIC_RUN)
    monkeypatch.setattr(reader_panel, "generate_json", fake_generate_json)
    monkeypatch.setattr(critic_panel, "generate_json", fake_generate_json)
    return calls


def _always_fail(i):
    raise ValueError("Model did not return valid JSON after 3 tries: stub")


def _count_revisions(monkeypatch):
    calls = {"n": 0}
    real = reviser.revise

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)
    monkeypatch.setattr(reviser, "revise", counting)
    return calls


def _project(tmp_path, chapters=1, **kw):
    p = BookProject(title="Invented Test Saga", output_dir=tmp_path,
                    target_chapters_per_book=chapters, target_words_per_chapter=100,
                    min_chapter_score=7.0, max_revisions_per_chapter=2, **kw)
    p.judge_model = "stub-judge"
    p.save()
    return p


def _chapters(tmp_path):
    return json.loads((tmp_path / "STATE.json").read_text())["books"][0]["chapters"]


# ── Panels ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("panel,args", [
    (reader_panel, ("An invented chapter.",)),
    (critic_panel, ("An invented chapter.", "beat")),
])
def test_failed_judge_has_no_scores(monkeypatch, tmp_path, panel, args):
    _judges(monkeypatch, _always_fail)
    result = panel.run(_project(tmp_path), *args)
    assert result["average_score"] is None
    assert result["judged"] == 0 and result["failed"] == len(result["reports"])
    for rep in result["reports"]:
        assert rep["judge_failed"] is True
        assert "valid JSON" in rep["error"]
        assert "scores" not in rep and "weighted" not in rep
    assert "Judge failed" in panel.render_markdown(result)


def test_mixed_results_average_only_successful_judges(monkeypatch, tmp_path):
    # Reader call 0 succeeds with 8s; every other judge fails.
    _judges(monkeypatch, lambda i: _scores_json(8) if i == 0 else _always_fail(i))
    project = _project(tmp_path)
    reader = reader_panel.run(project, "An invented chapter.")
    critic = critic_panel.run(project, "An invented chapter.", "beat")
    assert reader["average_score"] == 8.0
    assert (reader["judged"], reader["failed"]) == (1, 3)
    assert critic["average_score"] is None
    # One whole panel failed: combined is the other panel's average.
    assert orchestrator._combined_score(reader, critic) == 8.0
    note = critic_panel.build_revision_note(reader, critic)
    assert "valid JSON" not in note


def test_combined_keeps_critic_reader_weights_when_both_scored():
    reader = {"average_score": 6.0}
    critic = {"average_score": 8.0}
    assert orchestrator._combined_score(reader, critic) == round((8.0 + 0.9 * 6.0) / 1.9, 2)


# ── Orchestrator ──────────────────────────────────────────────────────────

def test_all_judges_failing_records_judge_failed(tmp_path, monkeypatch, mocked_pipeline, capsys):
    _judges(monkeypatch, _always_fail)
    revisions = _count_revisions(monkeypatch)
    orchestrator.run(_project(tmp_path))

    [ch] = _chapters(tmp_path)
    assert ch["status"] == "judge_failed"
    assert "valid JSON" in ch["judge_error"]
    assert not (tmp_path / "book-01" / "chapter-01" / "final.md").exists()
    assert revisions["n"] == 0
    assert "judge failed" in capsys.readouterr().out
    state = json.loads((tmp_path / "STATE.json").read_text())
    assert state["books"][0]["status"] != "done"
    assert state["stage"] != "done"


def test_later_revision_judge_failure_keeps_best_scored_draft(tmp_path, monkeypatch, mocked_pipeline):
    # v1 is scored 4 (below threshold → revise); every judge fails on v2.
    _judges(monkeypatch, lambda i: _scores_json(4) if i < JUDGE_CALLS_PER_ITERATION
            else _always_fail(i))
    orchestrator.run(_project(tmp_path))

    [ch] = _chapters(tmp_path)
    ch_dir = tmp_path / "book-01" / "chapter-01"
    assert ch["status"] == "done"
    assert ch["score"] == 4.0
    assert "valid JSON" in ch["judge_error"]
    assert (ch_dir / "final.md").read_text() == (ch_dir / "v1.md").read_text()
    assert not (ch_dir / "v3.md").exists()


def test_resume_reruns_judge_failed_chapter(tmp_path, monkeypatch, mocked_pipeline):
    _judges(monkeypatch, _always_fail)
    orchestrator.run(_project(tmp_path))
    assert _chapters(tmp_path)[0]["status"] == "judge_failed"

    _judges(monkeypatch, lambda i: _scores_json(9))
    orchestrator.run(BookProject.load(tmp_path))
    [ch] = _chapters(tmp_path)
    assert ch["status"] == "done" and ch["score"] == 9.0
    assert ch["judge_error"] == ""
    state = json.loads((tmp_path / "STATE.json").read_text())
    assert state["books"][0]["status"] == "done"


def test_streak_does_not_carry_over_between_runs(tmp_path, monkeypatch, mocked_pipeline):
    _judges(monkeypatch, _always_fail)
    orchestrator.run(_project(tmp_path, chapters=2))          # 2 failures
    orchestrator.run(BookProject.load(tmp_path))              # 2 more, no abort
    assert [c["status"] for c in _chapters(tmp_path)] == ["judge_failed"] * 2


def test_three_consecutive_judge_failures_make_writer_start_exit_1(
        tmp_path, monkeypatch, mocked_pipeline, capsys):
    _judges(monkeypatch, _always_fail)
    project = _project(tmp_path / "book", chapters=4)
    monkeypatch.setattr(llm_mod, "_available_models", lambda: {"stub-model:1b"})
    monkeypatch.setattr(remote_mod, "internet_available", lambda: False)
    monkeypatch.setattr(corpus_mod, "CORPUS_DIR", tmp_path / "corpus")
    monkeypatch.setattr(sys, "argv", ["writer", "start", str(project.output_dir)])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert "3 chapters in a row" in capsys.readouterr().err
    statuses = [c["status"] for c in _chapters(project.output_dir)]
    assert statuses == ["judge_failed"] * 3 + ["pending"]


# ── STATE.json compatibility ──────────────────────────────────────────────

def test_state_json_without_judge_error_loads(tmp_path, mocked_pipeline):
    orchestrator.run(_project(tmp_path))
    state = json.loads((tmp_path / "STATE.json").read_text())
    for ch in state["books"][0]["chapters"]:
        del ch["judge_error"]
    (tmp_path / "STATE.json").write_text(json.dumps(state))

    loaded = BookProject.load(tmp_path)
    assert loaded.book(1).chapter(1).judge_error == ""
    assert loaded.book(1).chapter(1).status == "done"


def test_writer_status_shows_judge_failed_chapter(tmp_path, monkeypatch, mocked_pipeline, capsys):
    _judges(monkeypatch, _always_fail)
    orchestrator.run(_project(tmp_path))
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", ["writer", "status", str(tmp_path)])
    cli.main()
    out = capsys.readouterr().out
    assert "[judge_failed]" in out
    assert "score   —" in out
    assert "judge failed: Model did not return valid JSON" in out
