"""Unit tests for BadgeAuthority (ADR-0011 §11c first paid feature substrate).

Covers test scenarios 1+2 from
`docs/references/2026-06-14-arena-verified-badge-svg-design.md` (boot
fail-closed paths) plus round-trip and tamper-resistance smoke. The other 8
scenarios in that file are gateway-level (depend on /badge/mint + /badge/
endpoints landing in 11c.2/11c.3)."""

from __future__ import annotations

import json

import pytest
from agentdex_arena.badge_auth import (
    BADGE_KID_V1,
    BADGE_SIGNING_KEY_ENV,
    BadgeAuthError,
    BadgeAuthority,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_KNOWN_KEY_HEX = Ed25519PrivateKey.generate().private_bytes_raw().hex()


def _payload(agent_name: str = "PolarBot", valid_until: float = 9_999_999_999.0) -> dict:
    return {
        "agent_name": agent_name,
        "signed_at": 1_750_000_000.0,
        "valid_until": valid_until,
        "kid": BADGE_KID_V1,
    }


def test_boot_fails_closed_when_env_unset(monkeypatch):
    """Without ARENA_BADGE_SIGNING_KEY_HEX set, construction raises immediately
    (Test scenario #1)."""
    monkeypatch.delenv(BADGE_SIGNING_KEY_ENV, raising=False)
    with pytest.raises(BadgeAuthError, match="not set"):
        BadgeAuthority()


def test_boot_fails_closed_on_malformed_key(monkeypatch):
    """Anything that isn't 64 lowercase hex chars rejected at construction
    (Test scenario #2)."""
    cases = [
        "not-hex",  # not hex
        "AB" * 32,  # uppercase
        "0" * 63,  # too short
        "0" * 65,  # too long
        "0" * 64 + " ",  # trailing whitespace
        "",  # empty (also hit by the "not set" branch when env-fed,
        #        but the explicit-arg path validates length)
    ]
    for bad in cases:
        monkeypatch.setenv(BADGE_SIGNING_KEY_ENV, bad)
        with pytest.raises(BadgeAuthError):
            BadgeAuthority()


def test_boot_succeeds_with_valid_key(monkeypatch):
    """64 lowercase hex chars → constructs cleanly + exposes public_key_hex."""
    monkeypatch.setenv(BADGE_SIGNING_KEY_ENV, _KNOWN_KEY_HEX)
    auth = BadgeAuthority()
    assert len(auth.public_key_hex) == 64
    assert all(c in "0123456789abcdef" for c in auth.public_key_hex)


def test_explicit_kwarg_overrides_env(monkeypatch):
    """signing_key_hex kwarg lets tests inject without touching env."""
    monkeypatch.delenv(BADGE_SIGNING_KEY_ENV, raising=False)
    auth = BadgeAuthority(signing_key_hex=_KNOWN_KEY_HEX)
    assert len(auth.public_key_hex) == 64


def test_sign_then_verify_round_trip():
    """Happy path: a freshly-signed badge verifies + returns the same payload."""
    auth = BadgeAuthority(signing_key_hex=_KNOWN_KEY_HEX)
    p = _payload()
    token = auth.sign_badge(p)
    out = auth.verify_badge(token)
    assert out == p


def test_sign_uses_canonical_json():
    """The same payload dict (regardless of insertion order) must always sign
    to the SAME token bytes — sort_keys + no whitespace are load-bearing for
    deterministic 5-minute caching (D5) and for the verify endpoint's bit-for-
    bit equality check across rotations of the same membership."""
    auth = BadgeAuthority(signing_key_hex=_KNOWN_KEY_HEX)
    p1 = {"agent_name": "A", "signed_at": 1.0, "valid_until": 2.0, "kid": BADGE_KID_V1}
    p2 = {"kid": BADGE_KID_V1, "valid_until": 2.0, "signed_at": 1.0, "agent_name": "A"}
    assert auth.sign_badge(p1) == auth.sign_badge(p2)


def test_verify_rejects_empty_token():
    auth = BadgeAuthority(signing_key_hex=_KNOWN_KEY_HEX)
    for missing in (None, ""):
        with pytest.raises(BadgeAuthError, match="required"):
            auth.verify_badge(missing)


def test_verify_rejects_malformed_token():
    """No `.` separator, wrong-length signature hex, non-hex chars all rejected
    uniformly as `malformed` — no info-leak about how close the caller was."""
    auth = BadgeAuthority(signing_key_hex=_KNOWN_KEY_HEX)
    for bad in [
        "no-dot-here-at-all",
        "abcd." + "f" * 127,  # signature too short
        "abcd." + "f" * 129,  # signature too long
        "ZZZZ." + "0" * 128,  # payload not hex
        "abcd." + "Z" * 128,  # signature not hex
        ".",  # both empty
        "abcd",  # no signature half
    ]:
        with pytest.raises(BadgeAuthError, match="malformed"):
            auth.verify_badge(bad)


def test_verify_rejects_bad_signature():
    """Right shape, wrong signature → `bad signature`. Flipping a single byte
    of the payload bytes invalidates the signature, surfacing as a clean
    BadgeAuthError (not InvalidSignature leaking out of cryptography)."""
    auth = BadgeAuthority(signing_key_hex=_KNOWN_KEY_HEX)
    token = auth.sign_badge(_payload())
    payload_hex, sig_hex = token.split(".", 1)
    # Tamper the payload (last hex char) without touching the signature
    tampered_payload = payload_hex[:-1] + ("0" if payload_hex[-1] != "0" else "1")
    tampered = f"{tampered_payload}.{sig_hex}"
    with pytest.raises(BadgeAuthError, match="bad badge signature"):
        auth.verify_badge(tampered)


def test_verify_rejects_signature_from_wrong_key():
    """A badge signed by a different BadgeAuthority instance MUST NOT verify."""
    auth_a = BadgeAuthority(signing_key_hex=_KNOWN_KEY_HEX)
    auth_b = BadgeAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
    token = auth_b.sign_badge(_payload())
    with pytest.raises(BadgeAuthError, match="bad badge signature"):
        auth_a.verify_badge(token)


def test_verify_rejects_non_json_payload():
    """A correctly-signed payload that ISN'T JSON surfaces as a clean
    BadgeAuthError, not a JSONDecodeError. (The /badge/mint endpoint always
    serializes via sign_badge so this path only fires on a maliciously-crafted
    token whose attacker controlled the signing key AND chose non-JSON bytes —
    defense-in-depth.)"""
    # We need a key the test controls so we can sign garbage.
    other_key = Ed25519PrivateKey.generate()
    payload_bytes = b"\xff\xfe not json"
    sig = other_key.sign(payload_bytes)
    # Build a BadgeAuthority that uses the SAME key, so the sig verifies,
    # but the payload deserialization fails.
    auth = BadgeAuthority(signing_key_hex=other_key.private_bytes_raw().hex())
    token = f"{payload_bytes.hex()}.{sig.hex()}"
    with pytest.raises(BadgeAuthError, match="not valid JSON"):
        auth.verify_badge(token)


def test_verify_rejects_non_dict_payload():
    """A correctly-signed payload that JSON-decodes to a list / string / null
    is rejected (badge claims MUST be an object). Same defense-in-depth as
    the non-JSON case above."""
    other_key = Ed25519PrivateKey.generate()
    payload_bytes = json.dumps([1, 2, 3]).encode("utf-8")
    sig = other_key.sign(payload_bytes)
    auth = BadgeAuthority(signing_key_hex=other_key.private_bytes_raw().hex())
    token = f"{payload_bytes.hex()}.{sig.hex()}"
    with pytest.raises(BadgeAuthError, match="JSON object"):
        auth.verify_badge(token)


def test_public_key_hex_matches_signing_key():
    """The exposed public_key_hex is the deterministic Ed25519 public derivation
    of the signing seed — third-party verifiers can pin this string."""
    seed = Ed25519PrivateKey.generate()
    auth = BadgeAuthority(signing_key_hex=seed.private_bytes_raw().hex())
    expected = seed.public_key().public_bytes_raw().hex()
    assert auth.public_key_hex == expected


def test_signing_key_not_exposed_via_attribute():
    """The private signing key MUST NOT be accessible via a public attribute —
    only the public key is exposed. (BadgeAuthority is constructed at boot
    from env; any code path that wanted the private key would have to read
    the env directly, which is auditable.)"""
    auth = BadgeAuthority(signing_key_hex=_KNOWN_KEY_HEX)
    public_attrs = [a for a in dir(auth) if not a.startswith("_")]
    # `public_key_hex` is intended; `sign_badge` and `verify_badge` are
    # methods. No `signing_key`, `private_key`, `key` attribute leaks.
    leaky = {a for a in public_attrs if "key" in a.lower() and "public" not in a.lower()}
    assert leaky == set(), f"unexpected key-related public attrs: {leaky}"
