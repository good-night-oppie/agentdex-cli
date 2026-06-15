"""Handler-level smoke for POST /badge/mint (ADR-0011 11c.2).

Covers test scenarios 3-6 from `docs/references/2026-06-14-arena-verified-
badge-svg-design.md`:
  3. /badge/mint rejects request with missing/invalid consent token (401/403)
  4. /badge/mint rejects token whose scopes don't include `badge_mint` (403)
  5. /badge/mint rejects free-tier owner (403 "membership required")
  6. /badge/mint accepts paid-tier owner → returns badge_token + svg_url +
     verify_url + valid_until_epoch

Test scenarios 7-10 (SVG render endpoint anti-substitution, ladder mirror,
TTL expiry, admin-surface absence extension) ship with 11c.3 alongside the
public render endpoint."""

from __future__ import annotations

import json

from adx_showdown.sidecar import Sidecar
from agentdex_arena.badge_auth import BadgeAuthority
from agentdex_arena.consent import ConsentAuthority, ConsentClaims
from agentdex_arena.gateway import BADGE_TOKEN_TTL_SEC, ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient


def _make_gateway(tmp_path, *, badge_authority=None, now: float = 1_000_000.0):
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    authority = ConsentAuthority(signing_key_hex=signing, now=lambda: now)
    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        badge_authority=badge_authority,
        now=lambda: now,
    )
    return gateway


def _mint_token(authority: ConsentAuthority, *, scopes: list[str], owner: str = "eddie@oppie.xyz") -> tuple[str, str]:
    """Returns (token, agent_name). Uses an Ed25519 pubkey just for shape — no
    PoP is invoked on /badge/mint, so any 64-char hex is fine."""
    agent_pubkey_hex = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
    claims = ConsentClaims(
        token_id="t" + "0" * 16,
        owner=owner,
        agent_name="PolarBot",
        agent_pubkey_hex=agent_pubkey_hex,
        scopes=scopes,
        issued_at=999_000.0,
        expires_at=2_000_000.0,
        confirmed_via="test",
    )
    return authority.mint(claims), claims.agent_name


def _make_badge_authority() -> BadgeAuthority:
    return BadgeAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())


def test_badge_mint_503_when_badge_authority_not_wired(tmp_path):
    """Test scenario 0 (degraded mode): with no BadgeAuthority injected, the
    route responds 503 'badge mint not configured' — distinct from the 403
    auth failures so operators can tell key-missing from owner-fault."""
    gateway = _make_gateway(tmp_path, badge_authority=None)
    app = create_app(gateway, sidecar_factory=Sidecar)
    token, _ = _mint_token(gateway.authority, scopes=["enroll", "battle", "evolve", "badge_mint"])
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/badge/mint", json={"token": token})
    assert r.status_code == 503, r.text


def test_badge_mint_rejects_missing_token(tmp_path):
    """Test scenario 3: no token in body → 403 (the consent.verify path
    raises ConsentError on the empty string, collapsed to opaque 403)."""
    gateway = _make_gateway(tmp_path, badge_authority=_make_badge_authority())
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/badge/mint", json={})
    assert r.status_code == 403, r.text


def test_badge_mint_rejects_token_without_badge_mint_scope(tmp_path):
    """Test scenario 4: token carries `battle` + `evolve` but NOT
    `badge_mint` → 403 with no leakage about why (§3d posture)."""
    gateway = _make_gateway(tmp_path, badge_authority=_make_badge_authority())
    app = create_app(gateway, sidecar_factory=Sidecar)
    # NB: token does NOT include "badge_mint" in scopes.
    token, _ = _mint_token(gateway.authority, scopes=["enroll", "battle", "evolve"])
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/badge/mint", json={"token": token})
    assert r.status_code == 403, r.text


def test_badge_mint_rejects_free_tier_owner(tmp_path):
    """Test scenario 5: token scopes include badge_mint but the owner is NOT
    in `ConsentAuthority.memberships` → 403 "membership required". This is
    the §3 paid-feature gate firing — anti-pay-to-rank stays whole because
    the badge is a SVG decoration, not a rating boost."""
    gateway = _make_gateway(tmp_path, badge_authority=_make_badge_authority())
    app = create_app(gateway, sidecar_factory=Sidecar)
    token, _ = _mint_token(gateway.authority, scopes=["enroll", "battle", "evolve", "badge_mint"])
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/badge/mint", json={"token": token})
    assert r.status_code == 403, r.text


def test_badge_mint_returns_signed_token_for_paid_owner(tmp_path):
    """Test scenario 6 (happy path): membership granted + badge_mint scope
    present + badge_authority wired → 200 with the 4 documented fields.
    The badge_token round-trips through BadgeAuthority.verify_badge and
    matches the claimed (agent_name, signed_at, valid_until, kid)."""
    badge = _make_badge_authority()
    now = 1_000_000.0
    gateway = _make_gateway(tmp_path, badge_authority=badge, now=now)
    app = create_app(gateway, sidecar_factory=Sidecar)
    owner = "eddie@oppie.xyz"
    token, agent_name = _mint_token(
        gateway.authority,
        scopes=["enroll", "battle", "evolve", "badge_mint"],
        owner=owner,
    )
    # Grant membership through the same primitive the admin endpoint uses.
    gateway.authority.grant_membership(owner, valid_until_epoch=now + 30 * 86_400)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/badge/mint", json={"token": token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"badge_token", "svg_url", "verify_url", "valid_until_epoch"}
    assert body["valid_until_epoch"] == now + BADGE_TOKEN_TTL_SEC
    assert body["svg_url"] == f"/badge/{agent_name}/{body['badge_token']}.svg"
    assert body["verify_url"] == f"/badge/{agent_name}/{body['badge_token']}/verify"
    payload = badge.verify_badge(body["badge_token"])
    assert payload["agent_name"] == agent_name
    assert payload["signed_at"] == now
    assert payload["valid_until"] == now + BADGE_TOKEN_TTL_SEC
    assert payload["kid"] == "badge-v1"


def test_badge_mint_spends_quota_per_call(tmp_path):
    """Quota wiring smoke: the route MUST call spend_quota(scope='badge_mint')
    so a paid owner can't mint unlimited badges per UTC day. Verify by
    counting calls and watching the 6th 403 with 'quota exhausted' shape."""
    badge = _make_badge_authority()
    now = 1_000_000.0
    gateway = _make_gateway(tmp_path, badge_authority=badge, now=now)
    app = create_app(gateway, sidecar_factory=Sidecar)
    owner = "eddie@oppie.xyz"
    token, _ = _mint_token(
        gateway.authority,
        scopes=["enroll", "battle", "evolve", "badge_mint"],
        owner=owner,
    )
    gateway.authority.grant_membership(owner, valid_until_epoch=now + 30 * 86_400)
    with TestClient(app, raise_server_exceptions=False) as client:
        # Default quota is 5/day (see ConsentClaims default_factory).
        for i in range(5):
            r = client.post("/badge/mint", json={"token": token})
            assert r.status_code == 200, f"call {i} unexpectedly {r.status_code}: {r.text}"
        r = client.post("/badge/mint", json={"token": token})
        assert r.status_code == 403, r.text


def test_badge_mint_quota_keys_per_agent_not_per_token(tmp_path):
    """§3b 5e: non-`battle` scopes key on claims.agent_name so /enroll/reissue
    (fresh token_id, same agent_name) cannot reset the daily mint budget. We
    simulate the reissue by minting a SECOND consent token with a different
    `token_id` but the same `agent_name` + `owner`, then verify the
    second token shares the first's quota counter."""
    badge = _make_badge_authority()
    now = 1_000_000.0
    gateway = _make_gateway(tmp_path, badge_authority=badge, now=now)
    app = create_app(gateway, sidecar_factory=Sidecar)
    owner = "eddie@oppie.xyz"
    agent_pubkey_hex = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()

    def _mint_with_token_id(token_id: str) -> str:
        claims = ConsentClaims(
            token_id=token_id,
            owner=owner,
            agent_name="PolarBot",
            agent_pubkey_hex=agent_pubkey_hex,
            scopes=["enroll", "battle", "evolve", "badge_mint"],
            issued_at=999_000.0,
            expires_at=2_000_000.0,
            confirmed_via="test",
        )
        return gateway.authority.mint(claims)

    gateway.authority.grant_membership(owner, valid_until_epoch=now + 30 * 86_400)
    first = _mint_with_token_id("first-tid-aaaaa")
    second = _mint_with_token_id("second-tid-aaaa")

    with TestClient(app, raise_server_exceptions=False) as client:
        # 3 mints on first token.
        for _ in range(3):
            r = client.post("/badge/mint", json={"token": first})
            assert r.status_code == 200, r.text
        # 2 mints on second token should still be allowed (5/day per agent).
        for _ in range(2):
            r = client.post("/badge/mint", json={"token": second})
            assert r.status_code == 200, r.text
        # 6th total on the AGENT (regardless of token_id) → 403.
        r = client.post("/badge/mint", json={"token": second})
        assert r.status_code == 403, r.text


def test_badge_mint_signature_unforgeable_by_a_different_authority(tmp_path):
    """The badge_token returned by /badge/mint MUST NOT verify under a
    different BadgeAuthority — defense against a deploy-time key swap that
    would otherwise silently render all previously-minted badges fake."""
    badge_a = _make_badge_authority()
    now = 1_000_000.0
    gateway = _make_gateway(tmp_path, badge_authority=badge_a, now=now)
    app = create_app(gateway, sidecar_factory=Sidecar)
    owner = "eddie@oppie.xyz"
    token, _ = _mint_token(
        gateway.authority,
        scopes=["enroll", "battle", "evolve", "badge_mint"],
        owner=owner,
    )
    gateway.authority.grant_membership(owner, valid_until_epoch=now + 30 * 86_400)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/badge/mint", json={"token": token})
    badge_token = r.json()["badge_token"]
    badge_b = _make_badge_authority()
    # badge_b's key is different from badge_a's; verify_badge must reject.
    import pytest
    from agentdex_arena.badge_auth import BadgeAuthError
    with pytest.raises(BadgeAuthError):
        badge_b.verify_badge(badge_token)


def test_badge_mint_payload_is_canonical_json(tmp_path):
    """The badge payload signed by /badge/mint must be canonical-JSON-encoded
    so the verify endpoint (11c.3) can decide cacheability bit-for-bit. We
    parse the payload hex out of the returned badge_token and verify
    sort_keys+no-whitespace shape."""
    badge = _make_badge_authority()
    now = 1_000_000.0
    gateway = _make_gateway(tmp_path, badge_authority=badge, now=now)
    app = create_app(gateway, sidecar_factory=Sidecar)
    owner = "eddie@oppie.xyz"
    token, _ = _mint_token(
        gateway.authority,
        scopes=["enroll", "battle", "evolve", "badge_mint"],
        owner=owner,
    )
    gateway.authority.grant_membership(owner, valid_until_epoch=now + 30 * 86_400)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/badge/mint", json={"token": token})
    badge_token = r.json()["badge_token"]
    payload_hex, _sig_hex = badge_token.split(".", 1)
    payload_bytes = bytes.fromhex(payload_hex)
    decoded = payload_bytes.decode("utf-8")
    # canonical = exactly the form json.dumps(..., sort_keys=True, separators=(",", ":")) emits
    parsed = json.loads(decoded)
    assert decoded == json.dumps(parsed, sort_keys=True, separators=(",", ":"))
