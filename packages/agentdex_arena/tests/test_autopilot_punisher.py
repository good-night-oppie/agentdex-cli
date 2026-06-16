"""Default-sandbox autopilot-punisher (codex dogfood P2).

The default sandbox opponent loses to "always choose 1" (5/5) — a reward hack on
the sandbox win-signal. The punisher detects the low-entropy autopilot SIGNATURE
and escalates only against it (gentle random -> latched max-damage), so a player
who actually varies their play keeps the gentle on-ramp.

Sidecar-free: exercises the escalation LOGIC and the policy ROUTING with injected
fake inner policies; no Node BattleStream, so it runs everywhere (the full
sandbox battle path is covered by the sidecar-gated arena suite).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from adx_showdown.protocol import parse_request
from adx_showdown.sim import BattleContext, call_policy
from agentdex_arena.gateway import _AUTOPILOT_WINDOW, _is_autopilot, autopilot_punisher

_REQ = parse_request(
    {
        "active": [{"moves": [{"id": "tackle", "move": "Tackle", "pp": 35, "maxpp": 35}]}],
        "side": {"id": "p2", "pokemon": [{"ident": "p2: A", "details": "A", "active": True}]},
    }
)
_CTX = BattleContext(side="p2", turns=1)


def _sess(choices: list[str], escalated: bool = False) -> SimpleNamespace:
    return SimpleNamespace(visitor_choices=list(choices), autopilot_escalated=escalated)


def test_not_autopilot_until_window_filled():
    assert _is_autopilot(_sess([])) is False
    assert _is_autopilot(_sess(["move 1"] * (_AUTOPILOT_WINDOW - 1))) is False


def test_autopilot_detected_at_window_of_identical_choices():
    s = _sess(["move 1"] * _AUTOPILOT_WINDOW)
    assert _is_autopilot(s) is True
    assert s.autopilot_escalated is True  # the latch was set


def test_varied_play_keeps_the_gentle_bot():
    assert _is_autopilot(_sess(["move 1", "move 2", "switch 2", "move 1"])) is False


def test_latch_is_sticky_against_vary_once_to_reset():
    s = _sess(["move 1"] * _AUTOPILOT_WINDOW)
    assert _is_autopilot(s) is True
    # now the visitor varies — but the latch holds (no de-escalation game)
    s.visitor_choices.append("move 2")
    assert _is_autopilot(s) is True


def test_punisher_routes_to_strong_only_when_on_autopilot():
    calls: list[str] = []

    def gentle(req, ctx):  # noqa: ANN001
        calls.append("gentle")
        return "move 1"

    def strong(req, ctx):  # noqa: ANN001
        calls.append("strong")
        return "move 2"

    flag = {"on": False}
    pol = autopilot_punisher(None, 0, on_autopilot=lambda: flag["on"], gentle=gentle, strong=strong)
    assert asyncio.run(call_policy(pol, _REQ, _CTX)) == "move 1"  # gentle path
    flag["on"] = True
    assert asyncio.run(call_policy(pol, _REQ, _CTX)) == "move 2"  # escalated path
    assert calls == ["gentle", "strong"]
