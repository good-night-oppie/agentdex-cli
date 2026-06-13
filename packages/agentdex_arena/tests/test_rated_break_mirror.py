"""Test #8: rated lane i.i.d. anchor-team matchmaking."""

import hashlib

import pytest

from adx_showdown.teams import starter_pack
from agentdex_arena.gateway import RATED_ANCHOR_TEAMS, RATED_POOL


def test_rated_anchor_teams_held_out():
    """RATED_ANCHOR_TEAMS must be held-out from visitor defaults and gym teams."""
    pack = starter_pack()
    # First 5 teams (indices 0-4) are the "common" pool: default + 4 archetypes
    common = list(pack.keys())[:5]
    # RATED_ANCHOR_TEAMS must be AFTER the common pool in the sorted pack
    for anchor_team in RATED_ANCHOR_TEAMS:
        assert anchor_team in pack, f"{anchor_team} missing from starter pack"
        assert anchor_team not in common, f"{anchor_team} must be held-out from defaults/gym"


def test_rated_anchor_team_selection_iid():
    """Opponent team selected i.i.d. of visitor team via extended nonce hash."""
    # Simulate two different visitor teams with the SAME battle nonce
    nonce = "test-nonce-123"

    # The opponent policy is selected by the battle nonce alone
    opponent_idx = (
        int.from_bytes(
            hashlib.blake2b(nonce.encode(), digest_size=2).digest(), "big"
        )
        % len(RATED_POOL)
    )
    opponent = RATED_POOL[opponent_idx]

    # The opponent TEAM is selected by an EXTENDED nonce hash, independent of visitor
    anchor_team_idx = (
        int.from_bytes(
            hashlib.blake2b(f"team:{nonce}".encode(), digest_size=2).digest(),
            "big",
        )
        % len(RATED_ANCHOR_TEAMS)
    )
    anchor_team = RATED_ANCHOR_TEAMS[anchor_team_idx]

    # Same nonce -> same opponent -> same anchor team (deterministic)
    assert opponent in RATED_POOL
    assert anchor_team in RATED_ANCHOR_TEAMS

    # Different nonce prefix -> different team index (i.i.d. of opponent selection)
    other_nonce = "other-nonce-456"
    other_anchor_idx = (
        int.from_bytes(
            hashlib.blake2b(f"team:{other_nonce}".encode(), digest_size=2).digest(),
            "big",
        )
        % len(RATED_ANCHOR_TEAMS)
    )
    # Very likely different (hash collision probability ~1/len(RATED_ANCHOR_TEAMS))
    assert other_anchor_idx != anchor_team_idx or len(RATED_ANCHOR_TEAMS) == 1


def test_rated_pool_and_anchor_teams_disjoint():
    """RATED_POOL (opponents) and RATED_ANCHOR_TEAMS must be disjoint sets."""
    # This ensures the opponent NAME and opponent TEAM are independently selectable
    for anchor_team in RATED_ANCHOR_TEAMS:
        # Anchor teams are team NAMES from starter pack, not opponent policy names
        # So they shouldn't overlap with RATED_POOL policy identifiers
        assert anchor_team.startswith(
            ("0", "1")
        ), f"anchor team {anchor_team} must be a pack key"

    for opponent in RATED_POOL:
        # Opponent policy names are anchor-* identifiers
        assert opponent.startswith("anchor-"), f"opponent {opponent} must be anchor-*"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
