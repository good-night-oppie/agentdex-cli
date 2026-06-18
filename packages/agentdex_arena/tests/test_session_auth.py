"""Unit tests for SessionAuthority — the human-account login session (ADR-0013
§D2/D3 seam).

Covers boot key-custody (fail-closed construction, optional-at-boot is the
caller's concern), mint/verify round-trip, the verified-email-as-owner contract
(so the consent-token owner key stays single per human), expiry, and
tamper/forgery resistance. Endpoint-level coverage (/auth/device/*,
/enroll/account) lands with those routes (D2/D3 PRs)."""

from __future__ import annotations

import pytest
from agentdex_arena.session import (
    SESSION_SIGNING_KEY_ENV,
    SESSION_TTL_SEC,
    SessionAuthority,
    SessionClaims,
    SessionError,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_KNOWN_KEY_HEX = Ed25519PrivateKey.generate().private_bytes_raw().hex()
_OWNER = "yongbing.e.tang@gmail.com"
_GH_ID = "12345678"


def _auth(now=None) -> SessionAuthority:
    if now is None:
        return SessionAuthority(signing_key_hex=_KNOWN_KEY_HEX)
    return SessionAuthority(signing_key_hex=_KNOWN_KEY_HEX, now=now)


# ---- boot / key custody ----


def test_boot_fails_closed_when_env_unset(monkeypatch):
    monkeypatch.delenv(SESSION_SIGNING_KEY_ENV, raising=False)
    with pytest.raises(SessionError, match="not set"):
        SessionAuthority()


def test_boot_fails_closed_on_malformed_key():
    for bad in ["not-hex", "AB" * 32, "0" * 63, "0" * 65]:
        with pytest.raises(SessionError):
            SessionAuthority(signing_key_hex=bad)


def test_boot_reads_env_when_no_arg(monkeypatch):
    monkeypatch.setenv(SESSION_SIGNING_KEY_ENV, _KNOWN_KEY_HEX)
    auth = SessionAuthority()
    assert (
        auth.public_key_hex
        == Ed25519PrivateKey.from_private_bytes(bytes.fromhex(_KNOWN_KEY_HEX))
        .public_key()
        .public_bytes_raw()
        .hex()
    )


def test_session_key_is_separate_from_consent_key():
    """Two independently-generated seeds yield different public keys — the D2
    blast-radius isolation only holds if the session authority is genuinely a
    distinct keypair, not a re-derivation of the consent key."""
    other = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    a = SessionAuthority(signing_key_hex=_KNOWN_KEY_HEX)
    b = SessionAuthority(signing_key_hex=other)
    assert a.public_key_hex != b.public_key_hex


# ---- mint / verify round-trip ----


def test_mint_verify_round_trip():
    auth = _auth()
    token = auth.mint_session(_OWNER, _GH_ID)
    claims = auth.verify_session(token)
    assert isinstance(claims, SessionClaims)
    assert claims.owner == _OWNER
    assert claims.github_id == _GH_ID
    assert len(claims.session_id) >= 8
    assert claims.expires_at == pytest.approx(claims.issued_at + SESSION_TTL_SEC)


def test_owner_is_verified_email_stored_verbatim():
    """D3 seam: the session owner must be the verified email VERBATIM (case
    preserved) so the account store records what federation returned; the
    consent/membership/quota key normalization happens downstream, not here."""
    mixed = "Yongbing.E.Tang@GMail.com"
    auth = _auth()
    claims = auth.verify_session(auth.mint_session(mixed, _GH_ID))
    assert claims.owner == mixed  # not lowercased at mint


def test_each_mint_has_unique_session_id():
    auth = _auth()
    ids = {auth.verify_session(auth.mint_session(_OWNER, _GH_ID)).session_id for _ in range(8)}
    assert len(ids) == 8


def test_custom_ttl_is_honored():
    auth = _auth(now=lambda: 1_000.0)
    claims = auth.verify_session(auth.mint_session(_OWNER, _GH_ID, ttl_sec=60.0))
    assert claims.issued_at == 1_000.0
    assert claims.expires_at == 1_060.0


# ---- rejection paths ----


def test_expired_token_rejected():
    clock = {"t": 1_000.0}
    auth = SessionAuthority(signing_key_hex=_KNOWN_KEY_HEX, now=lambda: clock["t"])
    token = auth.mint_session(_OWNER, _GH_ID, ttl_sec=100.0)
    clock["t"] = 1_101.0  # one second past expiry
    with pytest.raises(SessionError, match="expired"):
        auth.verify_session(token)


def test_tampered_payload_rejected():
    auth = _auth()
    token = auth.mint_session(_OWNER, _GH_ID)
    payload_b64, sig_b64 = token.split(".", 1)
    # flip a char in the payload — signature no longer matches
    flipped = payload_b64[:-1] + ("A" if payload_b64[-1] != "A" else "B")
    with pytest.raises(SessionError, match="signature"):
        auth.verify_session(f"{flipped}.{sig_b64}")


def test_token_from_other_key_rejected():
    """A session token minted by a DIFFERENT key (a forger) must not verify —
    this is the whole point of the dedicated keypair."""
    forger = SessionAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    victim = _auth()
    forged = forger.mint_session(_OWNER, _GH_ID)
    with pytest.raises(SessionError, match="signature"):
        victim.verify_session(forged)


def test_malformed_token_shapes_rejected():
    auth = _auth()
    for bad in ["", "no-dot", "only.", ".only", "a.b.c.d"]:
        with pytest.raises(SessionError):
            auth.verify_session(bad)


def test_consent_token_does_not_verify_as_session():
    """A consent token is a different trust domain; presenting one where a
    session token is expected must fail (cross-key, even if shape matches)."""
    from agentdex_arena.consent import ConsentAuthority, ConsentClaims

    consent = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    ctoken = consent.mint(
        ConsentClaims(
            token_id="abcd1234",
            owner=_OWNER,
            agent_name="oppie",
            agent_pubkey_hex="0" * 64,
            scopes=["battle"],
            issued_at=0.0,
            expires_at=9_999_999_999.0,
            confirmed_via="test",
        )
    )
    with pytest.raises(SessionError):
        _auth().verify_session(ctoken)


# ---- owner validation at mint ----


def test_mint_rejects_empty_owner():
    with pytest.raises(ValueError):
        _auth().mint_session("", _GH_ID)


def test_mint_rejects_control_char_owner():
    with pytest.raises(ValueError):
        _auth().mint_session("bad\nowner@x.com", _GH_ID)


def test_mint_rejects_blank_github_id():
    with pytest.raises(SessionError, match="github_id"):
        _auth().mint_session(_OWNER, "   ")
