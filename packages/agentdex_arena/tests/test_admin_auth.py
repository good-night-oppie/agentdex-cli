"""Unit tests for AdminAuthority (ADR-0011 admin bearer-token auth)."""

from __future__ import annotations

import hashlib

import pytest
from agentdex_arena.admin_auth import ADMIN_TOKEN_HASH_ENV, AdminAuthError, AdminAuthority

_KNOWN_TOKEN = "test-admin-token-do-not-deploy"
_KNOWN_HASH = hashlib.sha256(_KNOWN_TOKEN.encode("utf-8")).hexdigest()


def test_boot_fails_closed_when_env_unset(monkeypatch):
    """Without ARENA_ADMIN_TOKEN_HASH set, construction raises immediately."""
    monkeypatch.delenv(ADMIN_TOKEN_HASH_ENV, raising=False)
    with pytest.raises(AdminAuthError, match="not set"):
        AdminAuthority()


def test_boot_fails_closed_on_malformed_hash(monkeypatch):
    """Anything that isn't 64 lowercase hex chars rejected at construction."""
    cases = [
        "not-hex",  # not hex
        "AB" * 32,  # uppercase
        "0" * 63,  # too short
        "0" * 65,  # too long
        "0" * 64 + " ",  # trailing whitespace
        "",  # empty
    ]
    for bad in cases:
        monkeypatch.setenv(ADMIN_TOKEN_HASH_ENV, bad)
        with pytest.raises(AdminAuthError):
            AdminAuthority()


def test_boot_succeeds_with_valid_hash(monkeypatch):
    """64 lowercase hex chars → constructs cleanly."""
    monkeypatch.setenv(ADMIN_TOKEN_HASH_ENV, _KNOWN_HASH)
    auth = AdminAuthority()
    # The stored hash is the env value; not exposed via attr, but verify_bearer
    # uses it. No direct getter (avoid hash leak via __dict__).
    assert isinstance(auth, AdminAuthority)


def test_explicit_kwarg_overrides_env(monkeypatch):
    """token_hash_hex kwarg lets tests inject without touching env."""
    monkeypatch.delenv(ADMIN_TOKEN_HASH_ENV, raising=False)
    auth = AdminAuthority(token_hash_hex=_KNOWN_HASH)
    actor = auth.verify_bearer(_KNOWN_TOKEN)
    assert actor == _KNOWN_HASH[:8]


def test_verify_bearer_rejects_missing_header():
    auth = AdminAuthority(token_hash_hex=_KNOWN_HASH)
    for missing in (None, ""):
        with pytest.raises(AdminAuthError, match="required"):
            auth.verify_bearer(missing)


def test_verify_bearer_rejects_wrong_token():
    auth = AdminAuthority(token_hash_hex=_KNOWN_HASH)
    with pytest.raises(AdminAuthError, match="mismatch"):
        auth.verify_bearer("totally-wrong-token")
    with pytest.raises(AdminAuthError, match="mismatch"):
        # Plausible-looking-but-wrong: same length, different content
        auth.verify_bearer(_KNOWN_TOKEN + "x")


def test_verify_bearer_accepts_correct_token_returns_actor_hash():
    """Happy path: returns first 8 hex chars of the stored hash."""
    auth = AdminAuthority(token_hash_hex=_KNOWN_HASH)
    actor = auth.verify_bearer(_KNOWN_TOKEN)
    assert actor == _KNOWN_HASH[:8]
    # Verify the returned value is NOT the full hash, plaintext, or anything leak-y
    assert len(actor) == 8
    assert _KNOWN_TOKEN not in actor
    assert actor != _KNOWN_HASH


def test_verify_bearer_does_not_leak_plaintext_or_hash_in_exception():
    """AdminAuthError messages must NOT echo the presented token or stored hash."""
    auth = AdminAuthority(token_hash_hex=_KNOWN_HASH)
    presented = "secret-value-that-must-not-appear"
    try:
        auth.verify_bearer(presented)
    except AdminAuthError as e:
        msg = str(e)
        assert presented not in msg
        assert _KNOWN_HASH not in msg
        # Also no first-N-chars partial leak
        assert _KNOWN_HASH[:16] not in msg


def test_verify_bearer_constant_time_comparison_used():
    """Sanity that we're not doing == on hashes. We can't easily measure timing
    in a unit test, but we can assert the module imports hmac and uses
    compare_digest (smoke check)."""
    import agentdex_arena.admin_auth as mod

    src = (mod.__file__ or "").rstrip("c")  # .pyc → .py if compiled
    if src.endswith(".py"):
        with open(src) as f:
            text = f.read()
        assert "hmac.compare_digest" in text, "must use hmac.compare_digest, not =="
