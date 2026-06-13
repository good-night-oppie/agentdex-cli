"""BattleOracle — execution-grounded hard verdict for arena battles (A2).

The bridge's response text for a battle expedition is a JSON battle report:

    {"battle_id": ..., "me": ..., "opponent": ..., "winner": ..., "win": bool,
     "turns": int, "input_log_path": ..., "format": ..., "seed": [...],
     "dispute": bool?}

The winner IS the verdict — no rubric, no judge, nothing to game (the
anti-Clawvard property). A deterministic re-simulation audit samples
``audit_rate`` of battles (100% when the report carries ``dispute: true``);
the resim callable is INJECTED so the engine never imports the simulator
(adx_showdown supplies it).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from agentdex_engine.cards import TaskCard
from agentdex_engine.oracle.base import OracleVerdict, OracleVerdictMap

ResimFn = Callable[[str], str]
"""input_log_path -> winner name (re-simulated). Sync on purpose: the
orchestrator already runs Oracle.evaluate inside asyncio.to_thread."""


def _audit_sampled(battle_id: str, audit_rate: float) -> bool:
    """Deterministic per-battle sampling — same battle always samples the same
    way, so audits are reproducible and un-gameable by retry."""
    if audit_rate <= 0.0:
        return False
    if audit_rate >= 1.0:
        return True
    bucket = int.from_bytes(hashlib.blake2b(battle_id.encode(), digest_size=4).digest(), "big")
    return (bucket % 10_000) < int(audit_rate * 10_000)


class BattleOracle:
    """Oracle Protocol impl: battle outcome -> hard verdict (+ resim audit)."""

    def __init__(self, *, audit_rate: float = 0.10, resim: ResimFn | None = None) -> None:
        self.audit_rate = audit_rate
        self.resim = resim

    def evaluate(self, response: str, task_card: TaskCard) -> OracleVerdictMap:
        try:
            report = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            return {
                "battle.win": OracleVerdict(
                    kind="hard",
                    **{"pass": False},
                    score=0.0,
                    evidence=f"unparseable battle report: {str(response)[:160]!r}",
                )
            }
        winner = str(report.get("winner", ""))
        me = str(report.get("me", ""))
        win = (winner == me) and bool(winner)
        verdicts: OracleVerdictMap = {
            "battle.win": OracleVerdict(
                kind="hard",
                **{"pass": win},
                score=1.0 if win else 0.0,
                evidence=(
                    f"winner={winner!r} me={me!r} turns={report.get('turns')} "
                    f"battle_id={report.get('battle_id')}"
                ),
            )
        }
        battle_id = str(report.get("battle_id", ""))
        dispute = bool(report.get("dispute", False))
        if self.resim is not None and (dispute or _audit_sampled(battle_id, self.audit_rate)):
            log_path = str(report.get("input_log_path", ""))
            try:
                resim_winner = self.resim(log_path)
                match = resim_winner == winner
                verdicts["battle.resim_audit"] = OracleVerdict(
                    kind="hard",
                    **{"pass": match},
                    score=1.0 if match else 0.0,
                    evidence=(
                        f"resim winner={resim_winner!r} vs reported {winner!r} "
                        f"({'dispute' if dispute else 'sampled'} audit)"
                    ),
                )
                if not match:
                    # a falsified report also fails the win verdict outright
                    verdicts["battle.win"] = OracleVerdict(
                        kind="hard",
                        **{"pass": False},
                        score=0.0,
                        evidence=f"resim audit falsified report: {resim_winner!r} != {winner!r}",
                    )
            except Exception as e:  # audit infrastructure failure ≠ battle loss
                verdicts["battle.resim_audit"] = OracleVerdict(
                    kind="hard",
                    **{"pass": False},
                    score=0.0,
                    evidence=f"resim audit errored: {e!r}",
                    uncertainty=1.0,
                )
        return verdicts
