from __future__ import annotations

from types import SimpleNamespace

import pytest
from adx_frontier.candidate import AgentCandidate, Budget
from adx_frontier.mh_bridge import BeneApi, bridge_collaborative_candidate


class _Genome:
    genome_id = "genome-1"
    scores = {}
    engram_id = None

    def encode(self) -> bytes:
        return b"genome"


class _Store:
    def __init__(self) -> None:
        self.calls = []

    def append(self, *args, **kwargs) -> str:
        self.calls.append((args, kwargs))
        return "engram-1"


def _candidate(tmp_path) -> AgentCandidate:
    (tmp_path / "agent.py").write_text("pass\n")
    return AgentCandidate(
        "agent",
        "python agent.py",
        ("agent.py",),
        "model",
        Budget(1, 2),
        ("pokeagent-gen1ou",),
        tmp_path,
    )


def _axes(quality: float) -> dict[str, float]:
    return {"quality": quality, "cost_dollar": 1.0, "wall_clock_sec": 2.0}


@pytest.mark.parametrize("status,promoted", [("ACCEPT", True), ("REJECT", False)])
def test_bridge_delegates_accept_only_promotion_to_bene(tmp_path, status, promoted) -> None:
    seen = {}

    def auto(engram_id, **kwargs):
        seen.update(engram_id=engram_id, **kwargs)
        return SimpleNamespace(
            promoted=promoted, status=status, verdict_engram="verdict-1", reason="gate"
        )

    store = _Store()
    outcome = bridge_collaborative_candidate(
        _candidate(tmp_path),
        ladder_id="pokeagent-gen1ou",
        scores=_axes(2),
        baseline=_axes(1),
        metric="quality",
        store=store,
        conn=object(),
        agent_id="collaborative-agent",
        api=BeneApi(lambda _data: _Genome(), auto),
    )
    assert store.calls[0][0][:2] == ("strategic", "mh-candidate:agent")
    assert store.calls[0][1]["metadata"]["source"] == "agentdex.collaborative"
    assert seen["engram_id"] == "engram-1" and seen["metric"] == "quality"
    assert (outcome.status, outcome.promoted) == (status, promoted)


def test_bridge_rejects_incomplete_frontier_before_bene(tmp_path) -> None:
    with pytest.raises(ValueError, match="missing frontier axes"):
        bridge_collaborative_candidate(
            _candidate(tmp_path),
            ladder_id="pokeagent-gen1ou",
            scores={"quality": 2},
            baseline=_axes(1),
            metric="quality",
            store=_Store(),
            conn=object(),
            agent_id="agent",
            api=BeneApi(lambda _data: _Genome(), lambda *a, **k: None),
        )
