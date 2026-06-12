"""ScriptedBattleBridge — battle = expedition variant (ADR-0010 phase 4).

Satisfies the orchestrator's `_BridgeLike` protocol: `async send(prompt, ...)`
plays ONE battle (this baseline's policy vs the spec'd house anchor) and
returns a `BridgeResponse` whose text is the JSON battle report BattleOracle
consumes. The bridge also writes the A2 artifacts: the re-simulable inputLog
file and the BattleCard receipt.

The prompt IS the battle spec (JSON):

    {"battle_id", "format", "seed": [a,b,c,d], "anchor": "random|max_damage|
     heuristic", "anchor_seed": int, "my_team": packed|null,
     "anchor_team": packed|null, "expedition_id"}

cost_usd is 0.0 (not None) for scripted bots so the Pareto pool includes the
card instead of excluding it as failed (ResultCard MF5 semantics).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from agentdex_engine.cards import BattleCard

from adx_showdown.bots import heuristic_bot, max_damage_bot, random_bot
from adx_showdown.sidecar import Sidecar
from adx_showdown.sim import Policy, run_battle


@dataclass
class _BridgeCfg:
    name: str


@dataclass
class _ArenaBridgeResponse:
    """Structural twin of adx_bridges.BridgeResponse (text/cost/tokens/trace)."""

    text: str
    langfuse_trace_id: str | None = None
    cost_usd: float | None = None
    tokens: int | None = None


def _blake16(data: str) -> str:
    return hashlib.blake2b(data.encode(), digest_size=16).hexdigest()


def _make_policy(kind: str, sidecar: Sidecar, seed: int) -> Policy:
    if kind == "random":
        return random_bot(seed)
    if kind == "max_damage":
        return max_damage_bot(sidecar, fallback_seed=seed)
    if kind == "heuristic":
        return heuristic_bot(sidecar, fallback_seed=seed)
    raise ValueError(f"unknown policy kind {kind!r}")


class ScriptedBattleBridge:
    """One baseline = one scripted policy; each send() plays one battle."""

    def __init__(
        self,
        name: str,
        policy_kind: str,
        *,
        artifacts_dir: str | Path,
        policy_seed: int = 0,
        max_battles: int | None = None,
    ) -> None:
        self.cfg = _BridgeCfg(name=name)
        self.policy_kind = policy_kind
        self.policy_seed = policy_seed
        self.artifacts_dir = Path(artifacts_dir)
        self._max_battles = max_battles

    async def send(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        extra: dict | None = None,
    ) -> _ArenaBridgeResponse:
        spec = json.loads(prompt)
        battle_id = f"{spec['battle_id']}-{self.cfg.name}"
        t0 = time.monotonic()
        async with Sidecar(max_battles=self._max_battles) as sidecar:
            me = _make_policy(self.policy_kind, sidecar, self.policy_seed)
            anchor = _make_policy(
                spec.get("anchor", "random"), sidecar, int(spec.get("anchor_seed", 1))
            )
            result = await run_battle(
                sidecar,
                battle_id=battle_id,
                format_id=spec["format"],
                p1_name=self.cfg.name,
                p2_name=f"anchor-{spec.get('anchor', 'random')}",
                p1_policy=me,
                p2_policy=anchor,
                seed=list(spec["seed"]),
                p1_team=spec.get("my_team"),
                p2_team=spec.get("anchor_team"),
            )
        duration = time.monotonic() - t0

        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.artifacts_dir / f"{battle_id}.inputlog.json"
        log_path.write_text(json.dumps(result.input_log, indent=1) + "\n")
        log_digest = _blake16("\n".join(result.input_log))

        card = BattleCard(
            battle_id=battle_id,
            expedition_id=str(spec.get("expedition_id", "unscored")),
            format_id=str(spec["format"]),
            seed=[int(x) for x in spec["seed"]],
            p1_name=self.cfg.name,
            p2_name=f"anchor-{spec.get('anchor', 'random')}",
            winner=result.winner,
            turns=result.turns,
            input_log_path=str(log_path),
            input_log_blake2b16=log_digest,
            p1_team_sha=_blake16(spec["my_team"]) if spec.get("my_team") else None,
            p2_team_sha=_blake16(spec["anchor_team"]) if spec.get("anchor_team") else None,
            duration_sec=max(duration, 1e-6),
            decision_tokens=0,  # scripted: zero LLM cost (A7)
            choice_errors=result.choice_errors,
        )
        card_path = self.artifacts_dir / f"{battle_id}.battle_card.json"
        card_path.write_text(card.model_dump_json(indent=1) + "\n")

        report = {
            "battle_id": battle_id,
            "me": self.cfg.name,
            "opponent": card.p2_name,
            "winner": result.winner,
            "win": result.winner == self.cfg.name,
            "turns": result.turns,
            "input_log_path": str(log_path),
            "battle_card_path": str(card_path),
            "format": spec["format"],
            "seed": list(spec["seed"]),
        }
        return _ArenaBridgeResponse(
            text=json.dumps(report),
            langfuse_trace_id=None,
            cost_usd=0.0,  # NOT None — keeps the card in the Pareto pool
            tokens=0,
        )
