"""Unit tests for ConsentAuthority membership extensions (ADR-0011 11b.2).

Covers _normalize_owner, verify_membership, grant_membership. Integration with
gateway routes lands separately in 11b.3/11b.4.
"""

from __future__ import annotations

import time

import pytest
from agentdex_arena.consent import (
    ConsentAuthority,
    ConsentClaims,
    ConsentError,
    _normalize_owner,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_SIGNING_KEY_HEX = Ed25519PrivateKey.generate().private_bytes_raw().hex()


def _make_claims(owner: str = "eddie@oppie.xyz", agent_name: str = "TestBot") -> ConsentClaims:
    return ConsentClaims(
        token_id="testtoken0001",
        owner=owner,
        agent_name=agent_name,
        agent_pubkey_hex="0" * 64,
        scopes=["enroll", "battle", "evolve"],
        issued_at=time.time(),
        expires_at=time.time() + 7 * 86_400,
        confirmed_via="test",
    )


# ---- _normalize_owner ----


def test_normalize_owner_canonicalizes_case_whitespace_and_unicode():
    assert _normalize_owner("Eddie@Oppie.XYZ") == "eddie@oppie.xyz"
    assert _normalize_owner("  eddie@oppie.xyz  ") == "eddie@oppie.xyz"
    assert _normalize_owner("\teddie@oppie.xyz\n") == "eddie@oppie.xyz"
    # NFKC: full-width @ → @ ; full-width digits → ASCII
    assert _normalize_owner("eddie＠oppie.xyz") == "eddie@oppie.xyz"


def test_normalize_owner_rejects_empty_and_whitespace_only():
    for bad in ("", "   ", "\n\t"):
        with pytest.raises(ValueError, match="empty"):
            _normalize_owner(bad)


def test_normalize_owner_rejects_control_chars():
    for bad in ("eddie@oppie.xyz\x00", "eddie@\x07oppie.xyz", "eddie\x1foppie@xyz"):
        with pytest.raises(ValueError, match="control"):
            _normalize_owner(bad)


def test_normalize_owner_rejects_oversize():
    too_long = "a" * 255 + "@b.c"
    with pytest.raises(ValueError, match="max"):
        _normalize_owner(too_long)


def test_normalize_owner_rejects_non_string():
    with pytest.raises(ValueError, match="string"):
        _normalize_owner(12345)  # type: ignore[arg-type]


# ---- ConsentAuthority memberships dict + grant_membership ----


def test_authority_constructor_defaults_memberships_to_empty_dict():
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX)
    assert auth.memberships == {}


def test_authority_constructor_accepts_injected_memberships():
    seed = {"eddie@oppie.xyz": time.time() + 1000}
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX, memberships=seed)
    assert auth.memberships is seed  # not copied — gateway can replay-mutate in place


def test_grant_membership_normalizes_and_returns_key():
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX)
    key = auth.grant_membership("Eddie@Oppie.XYZ", 1_750_000_000)
    assert key == "eddie@oppie.xyz"
    assert auth.memberships["eddie@oppie.xyz"] == 1_750_000_000.0


def test_grant_membership_last_write_wins():
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX)
    auth.grant_membership("eddie@oppie.xyz", 1000.0)
    auth.grant_membership("eddie@oppie.xyz", 2000.0)
    assert auth.memberships["eddie@oppie.xyz"] == 2000.0


def test_grant_membership_propagates_normalize_errors():
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX)
    with pytest.raises(ValueError):
        auth.grant_membership("", 1000.0)
    with pytest.raises(ValueError):
        auth.grant_membership("x\x00y", 1000.0)


# ---- verify_membership ----


def test_verify_membership_raises_when_owner_unknown():
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX)
    with pytest.raises(ConsentError, match="membership required"):
        auth.verify_membership(_make_claims())


def test_verify_membership_passes_for_current_owner():
    now = time.time()
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX, now=lambda: now)
    auth.grant_membership("eddie@oppie.xyz", now + 100)
    auth.verify_membership(_make_claims())  # should not raise


def test_verify_membership_normalizes_claims_owner_at_lookup():
    """Grant under one casing → claims with different casing/whitespace pass."""
    now = time.time()
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX, now=lambda: now)
    auth.grant_membership("Eddie@Oppie.XYZ", now + 100)
    auth.verify_membership(_make_claims(owner="eddie@oppie.xyz"))  # exact normalized
    auth.verify_membership(_make_claims(owner="  EDDIE@OPPIE.XYZ  "))  # padded uppercase


def test_verify_membership_lazy_expiry_raises_after_valid_until():
    t0 = 1_000_000.0
    clock = {"now": t0}
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX, now=lambda: clock["now"])
    auth.grant_membership("eddie@oppie.xyz", t0 + 100)
    auth.verify_membership(_make_claims())  # ok at t0
    clock["now"] = t0 + 99
    auth.verify_membership(_make_claims())  # still ok at t0+99 (< valid_until)
    clock["now"] = t0 + 100
    # valid_until_epoch <= now → expired (revocation-as-past-epoch shape)
    with pytest.raises(ConsentError, match="membership required"):
        auth.verify_membership(_make_claims())


def test_verify_membership_revocation_via_past_epoch():
    """Grant + re-grant with valid_until <= now revokes via single code path."""
    now = time.time()
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX, now=lambda: now)
    auth.grant_membership("eddie@oppie.xyz", now + 100)
    auth.verify_membership(_make_claims())  # ok
    auth.grant_membership("eddie@oppie.xyz", now - 1)  # revoke
    with pytest.raises(ConsentError, match="membership required"):
        auth.verify_membership(_make_claims())


def test_verify_membership_does_not_leak_owner_in_exception():
    """ConsentError must NOT echo the owner — keeps audit log + 403 body clean."""
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX)
    try:
        auth.verify_membership(_make_claims(owner="leaked-owner-marker@bad.com"))
    except ConsentError as e:
        assert "leaked-owner-marker" not in str(e)


# ---- check_quota ----


def test_check_quota_passes_when_under_cap():
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX)
    claims = _make_claims()
    claims = claims.model_copy(update={"quotas": {"evolve": 2}})
    auth.check_quota(claims, scope="evolve")  # 0/2 used — must not raise


def test_check_quota_raises_when_at_cap():
    now = time.time()
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX, now=lambda: now)
    claims = _make_claims()
    claims = claims.model_copy(update={"quotas": {"evolve": 2}, "agent_name": "PeekBot"})
    day = time.strftime("%Y%m%d", time.gmtime(now))
    auth.quota_used["PeekBot:evolve:" + day] = 2
    with pytest.raises(ConsentError, match="quota exhausted"):
        auth.check_quota(claims, scope="evolve")


def test_check_quota_does_not_increment_counter():
    """check_quota is read-only — calling it must not consume a slot."""
    now = time.time()
    auth = ConsentAuthority(signing_key_hex=_SIGNING_KEY_HEX, now=lambda: now)
    claims = _make_claims()
    claims = claims.model_copy(update={"quotas": {"evolve": 2}, "agent_name": "ReadOnlyBot"})
    day = time.strftime("%Y%m%d", time.gmtime(now))
    key = "ReadOnlyBot:evolve:" + day
    auth.check_quota(claims, scope="evolve")  # 0/2 — passes
    auth.check_quota(claims, scope="evolve")  # still 0/2 — no increment
    assert auth.quota_used.get(key, 0) == 0
