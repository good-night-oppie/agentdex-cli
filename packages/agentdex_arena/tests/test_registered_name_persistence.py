"""Locks the invariant that `ArenaGateway._registered` is append-only —
once `enroll_confirm` adds an `agent_name`, neither token expiry, nor
membership lapse, nor clock advancement ever frees it.

SKILL.md and ENROLLMENT.md previously documented a "wait for the legacy
token's 7-day expiry, then re-enroll under the SAME agent_name"
workaround for the legacy-token / `badge_mint` scope gap. That workaround
is fiction — `_registered` carries every ever-confirmed name forever, so
the duplicate-name guard at `enroll_request` / `enroll_confirm`
permanently rejects the same name. PR #137 review #3411165981 caught the
documentation lie; the corrected docs ship in the same PR. This test
locks the underlying gateway behaviour so the corrected docs cannot
silently regress (any future change that introduces an expiry-driven
release of `_registered` would need a matching docs update).

Stand-alone module instead of bolting on to `test_visitor_surface.py`
because the latter is gated by `pytest.mark.skipif(sidecar_available()
is not None, ...)` — the showdown sidecar is not needed for enrollment-
only assertions and gating the regression lock on it would silently skip
the assertion every time the worktree lacks the pokemon-showdown CLI.
"""

from __future__ import annotations

from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient


def _make_gateway(tmp_path, *, now_box: list[float]):
    """A minimal gateway exposing `now` via a mutable box so the test can
    advance the clock past an enrollment without re-constructing."""
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    authority = ConsentAuthority(signing_key_hex=signing, now=lambda: now_box[0])
    return ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        now=lambda: now_box[0],
    )


def _confirm_enrollment(gateway: ArenaGateway, *, owner: str, name: str) -> str:
    """Drive the enrollment OOB confirmation directly against the gateway
    object. `notify_owner` is a no-op, so the request side never gives us
    the code over the wire — pull it from `pending_enrollments` instead."""
    from agentdex_arena.gateway import EnrollRequest

    pub = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
    gateway.enroll_request(
        EnrollRequest(owner=owner, agent_name=name, agent_pubkey_hex=pub)
    )
    # Exactly one pending code exists right after enroll_request — pull it.
    (code,) = gateway.pending_enrollments.keys()
    result = gateway.enroll_confirm(code)
    return result["token"]


def test_registered_name_persists_past_token_expiry(tmp_path):
    """Confirm enroll for "ExpiryGhost"; advance the clock past the
    token's `expires_at`; assert a re-enrollment under the SAME name
    still hits the 409 duplicate-name guard.

    Closes PR #137 review #3411165981.
    """
    now_box = [1_000_000.0]
    gateway = _make_gateway(tmp_path, now_box=now_box)

    token = _confirm_enrollment(gateway, owner="ghost@example.com", name="ExpiryGhost")
    assert token  # token shape doesn't matter; the side-effect on _registered does
    assert "ExpiryGhost" in gateway._registered

    # Advance the clock 30 days past enrollment — well beyond the 7-day
    # token expiry the deprecated docs guidance hinged on.
    now_box[0] += 30 * 86_400

    # Re-enroll under the SAME name. The duplicate-name guard fires
    # regardless of the clock — `_registered` has no expiry mechanism.
    app = create_app(gateway, sidecar_factory=lambda: None)
    pub = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(
            "/enroll/request",
            json={
                "owner": "ghost@example.com",
                "agent_name": "ExpiryGhost",
                "agent_pubkey_hex": pub,
            },
        )
    assert r.status_code == 409, (
        f"Re-enrollment under the same name must stay rejected after token "
        f"expiry (got {r.status_code}: {r.text}). The deprecated 'wait for "
        f"7d expiry' workaround does NOT work and any future change here "
        f"means SKILL.md / ENROLLMENT.md guidance need a matching update."
    )


def test_registered_set_never_releases_a_name(tmp_path):
    """Tighter assertion than the wire-level test above: the
    `_registered` set itself is append-only across the gateway's
    lifetime. No internal API releases a name; any future change here
    means the docs guidance needs revisiting."""
    now_box = [1_000_000.0]
    gateway = _make_gateway(tmp_path, now_box=now_box)

    _confirm_enrollment(gateway, owner="a@example.com", name="AlphaBot")
    _confirm_enrollment(gateway, owner="b@example.com", name="BetaBot")
    assert {"AlphaBot", "BetaBot"} <= gateway._registered

    # Time advance — set is invariant under the gateway's clock.
    now_box[0] += 365 * 86_400
    assert {"AlphaBot", "BetaBot"} <= gateway._registered
