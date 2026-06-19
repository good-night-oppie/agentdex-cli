"""Unit tests for the InviteStore — the agentdex.builders beta registration gate
(GA-CORE-1). Pure storage; no HTTP, no signing."""

from __future__ import annotations

import pytest
from agentdex_arena.invite import InviteError, InviteStore, new_invite_code


def test_new_code_is_unique_hex():
    a, b = new_invite_code(), new_invite_code()
    assert a != b
    assert len(a) == 16 and all(c in "0123456789abcdef" for c in a)


def test_mint_then_redeem_admits_owner():
    s = InviteStore()
    s.mint("code-1")
    assert s.redeemable("code-1") is True
    assert s.is_admitted("alice@x.com") is False
    s.redeem("code-1", "alice@x.com")
    assert s.is_admitted("alice@x.com") is True
    assert s.redeemable("code-1") is False  # now consumed


def test_code_is_single_use():
    s = InviteStore()
    s.mint("code-1")
    s.redeem("code-1", "alice@x.com")
    # a DIFFERENT owner cannot reuse the same code
    with pytest.raises(InviteError):
        s.redeem("code-1", "bob@x.com")
    assert s.is_admitted("bob@x.com") is False


def test_unknown_code_is_rejected():
    s = InviteStore()
    with pytest.raises(InviteError):
        s.redeem("never-minted", "alice@x.com")


def test_admitted_owner_reredeem_is_noop_no_code_burned():
    """AC3: a returning human (new token / second agent) does not burn a 2nd code."""
    s = InviteStore()
    s.mint("code-1")
    s.mint("code-2")
    s.redeem("code-1", "alice@x.com")
    # alice is already admitted — re-redeeming (even an unused code) consumes nothing
    s.redeem("code-2", "alice@x.com")
    assert s.redeemable("code-2") is True  # code-2 untouched
    assert s.stats()["redeemed"] == 1


def test_admission_is_owner_normalized():
    """Redemption admits the normalized owner, so casing/whitespace agrees with the
    quota/membership keys — a re-login with different casing is still admitted."""
    s = InviteStore()
    s.mint("code-1")
    s.redeem("code-1", "Alice@X.com")
    assert s.is_admitted("  alice@x.com ") is True
    assert s.is_admitted("ALICE@X.COM") is True


def test_mint_is_idempotent_on_replay():
    """Re-minting an existing code (event replay) leaves its redemption untouched."""
    s = InviteStore()
    s.mint("code-1")
    s.redeem("code-1", "alice@x.com")
    s.mint("code-1")  # replay of the invite_grant
    assert s.is_admitted("alice@x.com") is True
    assert s.redeemable("code-1") is False


def test_redeem_then_replay_redeem_is_consistent():
    """Replaying invite_grant + invite_redeem rebuilds the same admission state."""
    s1 = InviteStore()
    s1.mint("c")
    s1.redeem("c", "alice@x.com")
    # fresh store replays the two events
    s2 = InviteStore()
    s2.mint("c")
    s2.redeem("c", "alice@x.com")
    assert s2.is_admitted("alice@x.com") is True
    assert s1.stats() == s2.stats()


def test_stats_counts():
    s = InviteStore()
    for c in ("a", "b", "c"):
        s.mint(c)
    s.redeem("a", "alice@x.com")
    assert s.stats() == {"minted": 3, "redeemed": 1, "remaining": 2}


def test_malformed_inputs_fail_closed():
    s = InviteStore()
    with pytest.raises(ValueError):
        s.mint("")
    s.mint("code-1")
    with pytest.raises(ValueError):
        s.redeem("code-1", "")  # malformed owner reserves nothing
    assert s.redeemable("code-1") is True  # not consumed by the failed redeem
