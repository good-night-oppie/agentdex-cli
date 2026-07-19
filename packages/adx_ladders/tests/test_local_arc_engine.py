"""Unit tests for LocalArcEngine — genuine dynamics, no hardcoded score."""

from __future__ import annotations

from adx_ladders.engines.local_arc import LocalArcEngine


def _greedy_to_goal(engine: LocalArcEngine, game_id: str, *, max_steps: int = 64) -> float:
    obs = engine.reset(game_id)
    frame = obs["frame"]
    done = bool(obs.get("done", False))
    steps = 0
    while not done and steps < max_steps:
        agent = frame["agent"]
        goal = frame["goal"]
        ar, ac = agent[0], agent[1]
        gr, gc = goal[0], goal[1]
        if ar < gr:
            action = "down"
        elif ar > gr:
            action = "up"
        elif ac < gc:
            action = "right"
        elif ac > gc:
            action = "left"
        else:
            break
        step_obs = engine.step(action)
        frame = step_obs["frame"]
        done = bool(step_obs.get("done", False))
        steps += 1
    return float(engine.score())


def test_deterministic_reset_and_score() -> None:
    a = LocalArcEngine()
    b = LocalArcEngine()
    qa = _greedy_to_goal(a, "game-0")
    qb = _greedy_to_goal(b, "game-0")
    assert qa == qb
    assert a.reset("game-0")["frame"]["agent"] == b.reset("game-0")["frame"]["agent"]
    assert a.reset("game-0")["frame"]["goal"] == b.reset("game-0")["frame"]["goal"]


def test_good_sequence_beats_bad_sequence() -> None:
    good = LocalArcEngine()
    bad = LocalArcEngine()

    # Same seeded layout.
    g_obs = good.reset("game-det")
    b_obs = bad.reset("game-det")
    assert g_obs["frame"]["agent"] == b_obs["frame"]["agent"]
    assert g_obs["frame"]["goal"] == b_obs["frame"]["goal"]

    # Good: greedy toward goal.
    frame = g_obs["frame"]
    done = False
    for _ in range(64):
        if done:
            break
        ar, ac = frame["agent"]
        gr, gc = frame["goal"]
        if ar < gr:
            action = "down"
        elif ar > gr:
            action = "up"
        elif ac < gc:
            action = "right"
        elif ac > gc:
            action = "left"
        else:
            break
        step = good.step(action)
        frame = step["frame"]
        done = bool(step["done"])
    good_q = good.score()

    # Bad: repeatedly move away / no-op in a wrong direction.
    frame = b_obs["frame"]
    for _ in range(8):
        ar, ac = frame["agent"]
        gr, gc = frame["goal"]
        # Move opposite of greedy.
        if ar < gr:
            action = "up"
        elif ar > gr:
            action = "down"
        elif ac < gc:
            action = "left"
        elif ac > gc:
            action = "right"
        else:
            action = "up"
        step = bad.step(action)
        frame = step["frame"]
        if step["done"]:
            break
    bad_q = bad.score()

    assert 0.0 <= bad_q <= 1.0
    assert 0.0 <= good_q <= 1.0
    assert good_q > bad_q


def test_score_in_unit_interval() -> None:
    engine = LocalArcEngine()
    engine.reset("game-x")
    engine.step("left")
    engine.step("up")
    q = engine.score()
    assert 0.0 <= q <= 1.0


def test_reaching_goal_scores_one() -> None:
    q = _greedy_to_goal(LocalArcEngine(), "game-reach")
    assert q == 1.0


def test_scorecard_id_always_none() -> None:
    engine = LocalArcEngine()
    engine.reset("game-0")
    assert engine.scorecard_id() is None
    _greedy_to_goal(engine, "game-1")
    assert engine.scorecard_id() is None


def test_frame_exposes_grid_agent_goal() -> None:
    engine = LocalArcEngine()
    frame = engine.reset("game-frame")["frame"]
    assert "grid" in frame
    assert "agent" in frame
    assert "goal" in frame
    assert len(frame["grid"]) == frame["size"]
    assert frame["grid"][frame["agent"][0]][frame["agent"][1]] == 1
    assert frame["grid"][frame["goal"][0]][frame["goal"][1]] == 2
