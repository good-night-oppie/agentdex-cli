"""Every advertised gym leader must resolve to a real starter_pack team.

codex dogfood P1: ``ARCHETYPE_GYM_TEAMS["gym-trick-room"]`` pointed at
``04-trick-room``, but ``starter_pack()`` ships ``09-trick-room`` (04 is
``04-sand-balance``). ``_gym_team_name`` returned the missing id, then
``starter_pack()[name]`` raised KeyError -> 500 on an ADVERTISED gym, dead-ending
the agent. This locks the whole class: every name in GYM_LEADERS must resolve to
a team that exists.

Sidecar-free (pure dict lookups), so it lives outside the sidecar-gated
test_visitor_surface module and actually runs.
"""

from __future__ import annotations

import pytest
from adx_showdown.teams import starter_pack
from agentdex_arena.gateway import GYM_LEADERS, _gym_team_name


@pytest.mark.parametrize("gym", GYM_LEADERS)
def test_every_gym_resolves_to_a_real_team(gym: str):
    pack = starter_pack()
    team_name = _gym_team_name(gym)
    assert team_name in pack, (
        f"gym {gym!r} -> {team_name!r} which is NOT in starter_pack() (dead-end)"
    )


def test_trick_room_gym_maps_to_the_real_trick_room_team():
    assert _gym_team_name("gym-trick-room") == "09-trick-room"
    assert "04-trick-room" not in starter_pack()
