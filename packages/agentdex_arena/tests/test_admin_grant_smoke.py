"""Handler-level smoke for POST /admin/grant-membership (ADR-0011 11b.3).

Full integration suite (event replay across restart, body-validation ordering,
audit-log shape) ships in 11b.4. This file's job is just: 'the route exists
and the happy path returns ok=true'."""

import hashlib

from adx_showdown.sidecar import Sidecar
from agentdex_arena.admin_auth import AdminAuthority
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_ADMIN_TOKEN = "smoke-admin-token"
_ADMIN_HASH = hashlib.sha256(_ADMIN_TOKEN.encode()).hexdigest()


def test_admin_grant_membership_handler_smoke(tmp_path):
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    authority = ConsentAuthority(signing_key_hex=signing)
    admin = AdminAuthority(token_hash_hex=_ADMIN_HASH)
    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        admin_authority=admin,
        now=lambda: 1_000_000.0,
    )
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        # No admin header -> 403 (NOT 422 — auth runs before body validation).
        # Send an obviously-broken body (b'{') so we can prove auth fires first.
        r = client.post("/admin/grant-membership", content=b"{", headers={})
        assert r.status_code == 403, r.text

        # Wrong admin header -> 403.
        r = client.post(
            "/admin/grant-membership",
            json={"owner": "eddie@oppie.xyz", "valid_until_epoch": 1_000_100.0},
            headers={"X-Admin-Token": "wrong"},
        )
        assert r.status_code == 403, r.text

        # Correct admin header + valid body -> 200 with the normalized owner.
        r = client.post(
            "/admin/grant-membership",
            json={"owner": "Eddie@Oppie.XYZ", "valid_until_epoch": 1_000_100.0},
            headers={"X-Admin-Token": _ADMIN_TOKEN},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"ok": True, "owner": "eddie@oppie.xyz", "valid_until_epoch": 1_000_100.0}
        # And authority.memberships was actually mutated
        assert gateway.authority.memberships["eddie@oppie.xyz"] == 1_000_100.0

        # Over-horizon grant -> 422 (now that auth passed, body validation runs).
        r = client.post(
            "/admin/grant-membership",
            json={"owner": "eddie@oppie.xyz", "valid_until_epoch": 1_000_000.0 + 500 * 86_400},
            headers={"X-Admin-Token": _ADMIN_TOKEN},
        )
        assert r.status_code == 422, r.text
