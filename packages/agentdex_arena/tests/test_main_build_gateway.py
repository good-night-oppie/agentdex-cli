"""Smoke for build_gateway() boot posture (ADR-0011 11c review #3410920013).

build_gateway() must NOT hard-require the badge signing key — the previous
fail-closed boot took down enrollment / ladder / battle / replay routes
when ARENA_BADGE_SIGNING_KEY_HEX was missing. The fix degrades to
badge_authority=None, which makes /badge/mint return 503 'badge mint not
configured' while leaving every other route operational.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_HEX64_A = "a" * 64
_HEX64_B = Ed25519PrivateKey.generate().private_bytes_raw().hex()


def _scrub_env(monkeypatch) -> None:
    for var in (
        "ARENA_BADGE_SIGNING_KEY_HEX",
        "ARENA_SIGNING_KEY_HEX",
        "ARENA_ADMIN_TOKEN_HASH",
        "AI_BUILDER_TOKEN",
        "ARENA_RUNTIME_DIR",
        "ARENA_OWNER_INBOX_DIR",
        "ARENA_PG_DSN",
    ):
        monkeypatch.delenv(var, raising=False)


def test_build_gateway_degrades_when_badge_env_unset(monkeypatch, tmp_path: Path):
    """ARENA_BADGE_SIGNING_KEY_HEX unset → build_gateway succeeds + badge_auth=None.
    Other authorities still constructed and boot is otherwise unaffected."""
    _scrub_env(monkeypatch)
    monkeypatch.setenv("ARENA_ADMIN_TOKEN_HASH", "0" * 64)
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _HEX64_B)
    monkeypatch.setenv("ARENA_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ARENA_OWNER_INBOX_DIR", str(tmp_path / "inbox"))

    from agentdex_arena.__main__ import build_gateway

    gw = build_gateway()
    assert gw.badge_auth is None
    assert gw.admin is not None
    assert gw.authority is not None


def test_build_gateway_degrades_when_badge_env_malformed(monkeypatch, tmp_path: Path):
    """Malformed key (wrong length / not hex) follows the same degraded path."""
    _scrub_env(monkeypatch)
    monkeypatch.setenv("ARENA_ADMIN_TOKEN_HASH", "0" * 64)
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _HEX64_B)
    monkeypatch.setenv("ARENA_BADGE_SIGNING_KEY_HEX", "not-hex")
    monkeypatch.setenv("ARENA_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ARENA_OWNER_INBOX_DIR", str(tmp_path / "inbox"))

    from agentdex_arena.__main__ import build_gateway

    gw = build_gateway()
    assert gw.badge_auth is None


def test_build_gateway_wires_badge_when_env_valid(monkeypatch, tmp_path: Path):
    """Happy path: when the env is set + valid, badge_auth is a real
    BadgeAuthority — degraded mode does NOT silently kick in."""
    from agentdex_arena.badge_auth import BadgeAuthority

    _scrub_env(monkeypatch)
    monkeypatch.setenv("ARENA_ADMIN_TOKEN_HASH", "0" * 64)
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _HEX64_B)
    monkeypatch.setenv("ARENA_BADGE_SIGNING_KEY_HEX", _HEX64_A)
    monkeypatch.setenv("ARENA_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ARENA_OWNER_INBOX_DIR", str(tmp_path / "inbox"))

    from agentdex_arena.__main__ import build_gateway

    gw = build_gateway()
    assert isinstance(gw.badge_auth, BadgeAuthority)


def test_build_gateway_still_fails_closed_on_admin_env_missing(monkeypatch, tmp_path: Path):
    """The boot soft-fail is ONLY for BadgeAuthority. Other fail-closed
    authorities (AdminAuthority) still hard-stop boot — only the paid badge
    feature is allowed to come up unconfigured."""
    from agentdex_arena.admin_auth import AdminAuthError

    _scrub_env(monkeypatch)
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _HEX64_B)
    monkeypatch.setenv("ARENA_BADGE_SIGNING_KEY_HEX", _HEX64_A)
    monkeypatch.setenv("ARENA_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ARENA_OWNER_INBOX_DIR", str(tmp_path / "inbox"))
    # ARENA_ADMIN_TOKEN_HASH stays unset → AdminAuthority should raise.

    from agentdex_arena.__main__ import build_gateway

    with pytest.raises(AdminAuthError):
        build_gateway()
