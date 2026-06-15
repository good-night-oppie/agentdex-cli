"""Handler-level smoke for the badge render + verify endpoints (ADR-0011
11c.3). Covers test scenarios 7, 8, 9 from the design spec:

  7. /badge/{agent}/{badge_token}.svg rejects mismatched agent name (404)
  8. /badge/{agent}/{badge_token}.svg SVG carries the SAME rating as /ladder
     — the Q5 anti-pay-to-rank invariant extended to badge data
  9. /badge/{agent}/{badge_token}.svg rejects expired badge_token (404)

Plus: degraded mode (503 without BadgeAuthority), verify endpoint shape
(D7), cache header presence (D5), Referer host extraction (Q2 funnel),
opaque-error parity (D7 anti-enumeration).
"""

from __future__ import annotations

import json

from adx_showdown.sidecar import Sidecar
from agentdex_arena.badge_auth import BadgeAuthority
from agentdex_arena.consent import ConsentAuthority, ConsentClaims
from agentdex_arena.gateway import (
    BADGE_ISSUER,
    BADGE_LADDER_URL,
    BADGE_SVG_CACHE_SEC,
    BADGE_TOKEN_TTL_SEC,
    ArenaGateway,
    _badge_rating_color,
    _badge_referer_host,
    create_app,
)
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


def _make_badge_authority() -> BadgeAuthority:
    return BadgeAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())


def _mint_consent_token(
    authority: ConsentAuthority, *, agent_name: str = "PolarBot", owner: str = "eddie@oppie.xyz"
) -> str:
    agent_pubkey_hex = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
    claims = ConsentClaims(
        token_id="t" + "0" * 16,
        owner=owner,
        agent_name=agent_name,
        agent_pubkey_hex=agent_pubkey_hex,
        scopes=["enroll", "battle", "evolve", "badge_mint"],
        issued_at=999_000.0,
        expires_at=2_000_000.0,
        confirmed_via="test",
    )
    return authority.mint(claims)


def _seed_ladder_entry(
    gateway: ArenaGateway, agent_name: str, *, opponent: str = "anchor-heuristic"
) -> None:
    """Append a register + period event so recompute_ladder lifts `agent_name`
    into ladder_public()'s entrants dict. Glicko-2 computes the rating from a
    single win — we don't assert on the specific value, just that the entry
    exists with a rating /ladder reports identically to the badge endpoints."""
    gateway.events.append("register", {"name": agent_name, "frozen": False})
    gateway.events.append("register", {"name": opponent, "frozen": False})
    gateway.events.append(
        "period",
        {
            "events": [
                {
                    "battle_id": f"synthetic-{agent_name}",
                    "p1": agent_name,
                    "p2": opponent,
                    "winner": agent_name,
                    "input_log_blake2b16": "0" * 32,
                }
            ]
        },
    )


def _mint_badge_via_endpoint(client: TestClient, consent_token: str) -> str:
    r = client.post("/badge/mint", json={"token": consent_token})
    assert r.status_code == 200, r.text
    return r.json()["badge_token"]


def test_badge_referer_host_extracts_clean_host():
    assert _badge_referer_host(None) == ""
    assert _badge_referer_host("") == ""
    assert _badge_referer_host("https://github.com/owner/repo") == "github.com"
    assert _badge_referer_host("HTTPS://EXAMPLE.ORG/path?q=1") == "example.org"
    # Malformed but parseable → empty string, not exception.
    assert _badge_referer_host("not-a-url") == ""


def test_badge_rating_color_thresholds():
    assert _badge_rating_color(0) == "#9f9f9f"
    assert _badge_rating_color(1499.9) == "#9f9f9f"
    assert _badge_rating_color(1500.0) == "#6cb868"
    assert _badge_rating_color(1749.9) == "#6cb868"
    assert _badge_rating_color(1750.0) == "#4ba14a"
    assert _badge_rating_color(3000.0) == "#4ba14a"


def test_badge_svg_503_when_badge_authority_not_wired(tmp_path):
    """Degraded mode parity with /badge/mint: no BadgeAuthority → 503 from
    the render endpoint too."""
    gateway = _make_gateway(tmp_path, badge_authority=None)
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/badge/PolarBot/abcd.f1234.svg")
    assert r.status_code == 503, r.text


def test_badge_verify_503_when_badge_authority_not_wired(tmp_path):
    gateway = _make_gateway(tmp_path, badge_authority=None)
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/badge/PolarBot/abcd.f1234/verify")
    assert r.status_code == 503, r.text


def test_badge_svg_rejects_malformed_token_with_404(tmp_path):
    """D7 anti-enumeration: 404 opaque on signature/shape failure, no
    info-leak about whether the token was even close."""
    gateway = _make_gateway(tmp_path, badge_authority=_make_badge_authority())
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/badge/PolarBot/not-a-valid-badge-token.svg")
    assert r.status_code == 404, r.text


def test_badge_svg_rejects_mismatched_agent_name(tmp_path):
    """Test scenario 7: a valid badge for `PolarBot` cannot render under
    `/badge/AttackerBot/...svg`. 404 opaque so the response cannot confirm
    the badge exists somewhere else."""
    badge = _make_badge_authority()
    now = 1_000_000.0
    gateway = _make_gateway(tmp_path, badge_authority=badge, now=now)
    _seed_ladder_entry(gateway, "PolarBot")
    _seed_ladder_entry(gateway, "AttackerBot")
    gateway.authority.grant_membership("eddie@oppie.xyz", valid_until_epoch=now + 30 * 86_400)
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        consent_token = _mint_consent_token(gateway.authority, agent_name="PolarBot")
        badge_token = _mint_badge_via_endpoint(client, consent_token)
        # Caller swaps the path agent to AttackerBot but keeps PolarBot's badge.
        r = client.get(f"/badge/AttackerBot/{badge_token}.svg")
    assert r.status_code == 404, r.text


def test_badge_svg_rejects_expired_token(tmp_path):
    """Test scenario 9: badge_token whose valid_until is in the past → 404.
    Implemented by advancing gateway.now past valid_until after mint."""
    badge = _make_badge_authority()
    now = 1_000_000.0
    clock = {"t": now}
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    authority = ConsentAuthority(signing_key_hex=signing, now=lambda: clock["t"])
    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        badge_authority=badge,
        now=lambda: clock["t"],
    )
    _seed_ladder_entry(gateway, "PolarBot")
    gateway.authority.grant_membership("eddie@oppie.xyz", valid_until_epoch=now + 30 * 86_400)
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        consent_token = _mint_consent_token(gateway.authority, agent_name="PolarBot")
        badge_token = _mint_badge_via_endpoint(client, consent_token)
        # Fast-forward past the badge's 30-day TTL.
        clock["t"] = now + BADGE_TOKEN_TTL_SEC + 1
        r = client.get(f"/badge/PolarBot/{badge_token}.svg")
    assert r.status_code == 404, r.text


def test_badge_svg_returns_svg_with_cache_header(tmp_path):
    """D5 — Cache-Control: public, max-age=300 on every render. Body is an
    SVG carrying the same rating/RD /ladder reports for the agent."""
    badge = _make_badge_authority()
    now = 1_000_000.0
    gateway = _make_gateway(tmp_path, badge_authority=badge, now=now)
    _seed_ladder_entry(gateway, "PolarBot")
    gateway.authority.grant_membership("eddie@oppie.xyz", valid_until_epoch=now + 30 * 86_400)
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        consent_token = _mint_consent_token(gateway.authority, agent_name="PolarBot")
        badge_token = _mint_badge_via_endpoint(client, consent_token)
        ladder_entry = client.get("/ladder").json()["entrants"]["PolarBot"]
        r = client.get(f"/badge/PolarBot/{badge_token}.svg")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/svg+xml"), r.headers["content-type"]
    assert r.headers["cache-control"] == f"public, max-age={BADGE_SVG_CACHE_SEC}"
    body = r.text
    assert body.startswith("<svg ")
    assert "PolarBot" in body
    # Rating + RD rendered as :.0f integers per D4 — must match /ladder's
    # values formatted the same way.
    assert f"{ladder_entry['rating']:.0f}" in body
    assert f"{ladder_entry['rd']:.0f}" in body
    # Color band must match what _badge_rating_color computes for the rating.
    expected_color = _badge_rating_color(float(ladder_entry["rating"]))
    assert expected_color in body


def test_badge_svg_mirrors_ladder_rating_exactly(tmp_path):
    """Test scenario 8 (Q5 carryover): the rating + RD rendered in the SVG
    MUST equal what /ladder reports for the same agent — no membership-
    derived rating boost, no paid-tier branch."""
    badge = _make_badge_authority()
    now = 1_000_000.0
    gateway = _make_gateway(tmp_path, badge_authority=badge, now=now)
    _seed_ladder_entry(gateway, "PolarBot")
    gateway.authority.grant_membership("eddie@oppie.xyz", valid_until_epoch=now + 30 * 86_400)
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        consent_token = _mint_consent_token(gateway.authority, agent_name="PolarBot")
        badge_token = _mint_badge_via_endpoint(client, consent_token)
        ladder = client.get("/ladder").json()["entrants"]["PolarBot"]
        verify = client.get(f"/badge/PolarBot/{badge_token}/verify").json()
    assert verify["rating"] == ladder["rating"]
    assert verify["rd"] == ladder["rd"]
    assert verify["games"] == ladder["games"]


def test_badge_verify_returns_d7_shape(tmp_path):
    """D7 — verify endpoint JSON carries the documented field set so
    third-party tooling can re-derive the signed payload + cross-check
    against /ladder."""
    badge = _make_badge_authority()
    now = 1_000_000.0
    gateway = _make_gateway(tmp_path, badge_authority=badge, now=now)
    _seed_ladder_entry(gateway, "PolarBot")
    gateway.authority.grant_membership("eddie@oppie.xyz", valid_until_epoch=now + 30 * 86_400)
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        consent_token = _mint_consent_token(gateway.authority, agent_name="PolarBot")
        badge_token = _mint_badge_via_endpoint(client, consent_token)
        r = client.get(f"/badge/PolarBot/{badge_token}/verify")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "agent_name",
        "rating",
        "rd",
        "games",
        "signed_at_epoch",
        "valid_until_epoch",
        "badge_public_key_hex",
        "kid",
        "ladder_url",
        "issuer",
    }
    assert body["agent_name"] == "PolarBot"
    assert body["signed_at_epoch"] == now
    assert body["valid_until_epoch"] == now + BADGE_TOKEN_TTL_SEC
    assert body["kid"] == "badge-v1"
    assert body["badge_public_key_hex"] == badge.public_key_hex
    assert body["ladder_url"] == BADGE_LADDER_URL
    assert body["issuer"] == BADGE_ISSUER


def test_badge_verify_payload_round_trips_to_signed_form(tmp_path):
    """The verify endpoint must surface (agent_name, signed_at, valid_until,
    kid) that re-serialize to the canonical-JSON bytes the badge_token was
    signed over. Third-party verifiers depend on this — they reconstruct the
    payload from the JSON, then verify the ed25519 sig themselves."""
    badge = _make_badge_authority()
    now = 1_000_000.0
    gateway = _make_gateway(tmp_path, badge_authority=badge, now=now)
    _seed_ladder_entry(gateway, "PolarBot")
    gateway.authority.grant_membership("eddie@oppie.xyz", valid_until_epoch=now + 30 * 86_400)
    app = create_app(gateway, sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        consent_token = _mint_consent_token(gateway.authority, agent_name="PolarBot")
        badge_token = _mint_badge_via_endpoint(client, consent_token)
        verify_body = client.get(f"/badge/PolarBot/{badge_token}/verify").json()
    # Reconstruct payload from verify JSON exactly as a third-party would.
    reconstructed = {
        "agent_name": verify_body["agent_name"],
        "signed_at": verify_body["signed_at_epoch"],
        "valid_until": verify_body["valid_until_epoch"],
        "kid": verify_body["kid"],
    }
    expected_payload_bytes = json.dumps(
        reconstructed, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    # The badge_token's payload_hex half must decode to exactly these bytes.
    payload_hex, _sig_hex = badge_token.split(".", 1)
    assert bytes.fromhex(payload_hex) == expected_payload_bytes


def test_badge_svg_xml_escapes_agent_name(tmp_path):
    """An agent_name containing XML special chars (defense-in-depth — the
    enrollment validator sanitize_name()s, but the render boundary should
    NOT trust the upstream filter). Pre-existing names go through
    sanitize_name; we synthesize a malicious one and bypass the registry
    by writing directly to the ladder + minting a badge claim. The SVG
    rendered output MUST NOT contain raw `<script>`-style tokens."""
    # Note: agent_name with `<>&` would normally be rejected by sanitize_name;
    # _render_badge_svg is tested via its module-level helper to confirm it
    # XML-escapes regardless of upstream guarantees. No gateway needed.
    from agentdex_arena.gateway import _render_badge_svg

    svg = _render_badge_svg(
        agent_name="Polar<script>Bot</script>",
        rating=1700.0,
        rd=30.0,
        verify_url='/badge/x/y/verify"&injected',
    )
    # No raw `<script>` token survives the render — the escape converts the
    # `<` into `&lt;`.
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    # Verify URL is also escaped (the `&` in the attacker URL becomes &amp;).
    assert "&amp;injected" in svg
