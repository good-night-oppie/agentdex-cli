"""Render regression: 'Your active' is read from the request, never '?'.

codex dogfood P1: at the opening (and any turn where the caller's
``state["active"]`` map lacks this side) ``BattleContext.my_species`` is None,
yet the |request| flags the active mon on the bench. The renderer must show it
— NOT ``Your active: ?`` — while the bench lists it as ``[active]``.

Sidecar-free on purpose: ``render_state`` + ``active_species`` are pure (no Node
BattleStream), so this lives OUTSIDE the sidecar-gated test_showdown_battle_bridge
module and actually runs in every environment.
"""

from __future__ import annotations

from adx_bridges.showdown_battle_bridge import render_state
from adx_showdown.protocol import active_species, parse_request
from adx_showdown.sim import BattleContext

_REQ = {
    "active": [{"moves": [{"id": "headlongrush", "move": "Headlong Rush", "pp": 8, "maxpp": 8}]}],
    "side": {
        "id": "p1",
        "pokemon": [
            {
                "ident": "p1: Great Tusk",
                "details": "Great Tusk",
                "condition": "100/100",
                "active": True,
            },
            {
                "ident": "p1: Kingambit",
                "details": "Kingambit",
                "condition": "100/100",
                "active": False,
            },
        ],
    },
}


def test_render_shows_active_from_request_when_ctx_my_species_missing():
    req = parse_request(_REQ)
    # my_species=None reproduces the opening-render condition (state['active'] lacks p1)
    text = render_state(
        req, BattleContext(side="p1", my_species=None, turns=1), scratchpad="", recent_turns=[]
    )
    assert "Your active: Great Tusk" in text
    assert "Your active: ?" not in text


def test_ctx_my_species_still_wins_when_present():
    """The request fallback must not override an explicit ctx.my_species."""
    req = parse_request(_REQ)
    text = render_state(
        req,
        BattleContext(side="p1", my_species="Landorus-Therian", turns=1),
        scratchpad="",
        recent_turns=[],
    )
    assert "Your active: Landorus-Therian" in text


def test_active_species_helper_contract():
    assert active_species(parse_request(_REQ)) == "Great Tusk"
    # no active flag → None (renders as '?', the honest "unknown" state)
    assert active_species(parse_request({"side": {"id": "p1", "pokemon": []}})) is None
    none_active = {
        "side": {"id": "p1", "pokemon": [{"ident": "p1: X", "details": "X", "active": False}]}
    }
    assert active_species(parse_request(none_active)) is None
