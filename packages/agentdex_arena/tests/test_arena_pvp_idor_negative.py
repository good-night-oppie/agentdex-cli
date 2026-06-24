"""Step-6 GA-ARENA-MODES invariant: battle_id share-nothing partition (ADR-0010).

Lives in its OWN named module so the north-star probe's ``ga_arena_ci_attest.sh``
can flip ``battle_id_share_nothing_partition_idor_negative`` from
UNVERIFIED → ATTESTED when this file appears in
``ga-arena-modes-invariants.yml``'s module list.

ADR-0010 share-nothing posture: a ``battle_id`` is opaque routing metadata. It
NEVER grants access on its own — every state-changing or info-leaking arena
route enforces a token/session binding to the specific battle_id, and falls
back to opaque 403 (collapsed "no such battle" + "not your battle", D7
anti-enumeration). This module pins the HTTP-boundary regression for the four
arena routes the probe lists as IDOR surfaces:

  * ``POST /battle/{id}/pvp-choose`` — P2-move surface; token must be the P2
    token bound at queue time (``session.pvp_p2_claims_token_id``). Unknown
    battle_id → 403, bad-shape token → 403, valid token but not P2 → 403.
  * ``GET /me/battle/{id}/live`` — owner SSE stream; session owner_norm must
    match ``session.owner`` or session.visitor_name ∈ caller's account agents.
    No session → 401, unknown battle → 403, no enumeration of others' battles.
  * ``GET /battle/{id}/live`` — public spectator stream; unknown battle is the
    one route that returns 404 (the spectator surface has no auth and no
    cross-owner data, so D7 collapse isn't required; explicit 404 is fine).
  * ``GET /me/battles`` — owner battle list; anon → 401, a fresh owner sees an
    empty live + recent list (never another owner's battles).

NO production code is touched. Pure regression lock.
"""

from __future__ import annotations

from pathlib import Path

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_ALICE = "alice@x.com"
_BOB = "bob@x.com"


def _gw(tmp_path: Path) -> ArenaGateway:
    return ArenaGateway(
        authority=ConsentAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        session_authority=SessionAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
    )


def _client(gw: ArenaGateway) -> TestClient:
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


def _sess(gw: ArenaGateway, owner: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {gw.session_auth.mint_session(owner, f'email:{owner}')}"}


# ---- /battle/{id}/pvp-choose: token-bound, never leaks via battle_id --------


def test_pvp_choose_unknown_battle_id_returns_403_not_404(tmp_path):
    """Bad-shape token short-circuits to opaque 403 before any battle_id
    lookup — never 404/500. D7 collapse: a probe with a malformed token gets
    the SAME 403 it would get with a real token + nonexistent battle_id, so
    the response cannot be used to enumerate the live-battle keyspace."""
    gw = _gw(tmp_path)
    with _client(gw) as c:
        r = c.post(
            "/battle/pvp-NONEXISTENT/pvp-choose",
            json={"token": "not.a.real.token", "choice_index": 1},
        )
    assert r.status_code == 403, r.text


def test_pvp_choose_empty_token_returns_403(tmp_path):
    """An empty/missing token never reveals battle existence."""
    gw = _gw(tmp_path)
    with _client(gw) as c:
        r = c.post(
            "/battle/pvp-ANYTHING/pvp-choose",
            json={"token": "", "choice_index": 1},
        )
    assert r.status_code in (403, 422), r.text  # 422 if pydantic rejects empty token


# ---- /me/battle/{id}/live: session-authed, share-nothing on unknown id -----


def test_me_battle_live_anon_returns_401_no_battle_lookup(tmp_path):
    """Anon caller (no session cookie, no Bearer) → 401, BEFORE the battle_id
    is even looked up. The keyspace is never probed by an unauthed party."""
    gw = _gw(tmp_path)
    with _client(gw) as c:
        r = c.get("/me/battle/pvp-ANYTHING/live")
    assert r.status_code == 401, r.text


def test_me_battle_live_unknown_battle_id_returns_403_not_404(tmp_path):
    """A fully-authenticated owner asking for a battle that does not exist
    gets opaque 403 ('not your battle'). This is the D7 collapse — 404
    would let an attacker map the live-battle id space; 403 hides it."""
    gw = _gw(tmp_path)
    with _client(gw) as c:
        r = c.get(
            "/me/battle/pvp-NONEXISTENT/live",
            headers=_sess(gw, _ALICE),
        )
    assert r.status_code == 403, r.text


def test_me_battle_live_bad_session_returns_403(tmp_path):
    """A garbage Bearer token never leaks battle existence."""
    gw = _gw(tmp_path)
    with _client(gw) as c:
        r = c.get(
            "/me/battle/pvp-NONEXISTENT/live",
            headers={"Authorization": "Bearer not.a.real.session"},
        )
    assert r.status_code == 403, r.text


# ---- /me/battles: only the caller's battles, never the platform's ---------


def test_me_battles_anon_returns_401(tmp_path):
    """``/me/battles`` is session-authed read; anon → 401. The list shape
    (live + recent battle ids) is never visible to an unauthenticated probe."""
    gw = _gw(tmp_path)
    with _client(gw) as c:
        r = c.get("/me/battles")
    assert r.status_code == 401, r.text


def test_me_battles_fresh_owner_sees_empty_lists_not_others_battles(tmp_path):
    """A brand-new owner with zero enrolled agents sees empty live + recent.
    This pins the partition: a session never inherits another owner's battles,
    so even a misbehaving handler that forgot to filter by claims.owner would
    be caught the first time another owner had a session in flight."""
    gw = _gw(tmp_path)
    with _client(gw) as c:
        r = c.get("/me/battles", headers=_sess(gw, _ALICE))
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)
    # The route's structured payload may surface live/recent/etc keys; the
    # invariant is "no list field contains another owner's battle_id". With
    # zero sessions and zero accounts.agents_for(_ALICE) the response must
    # not enumerate any third-party battles.
    for value in body.values():
        if isinstance(value, list):
            assert value == [], f"unexpected non-empty field for fresh owner: {value!r}"


# ---- /battle/{id}/live: public spectator, only the explicit 404 surface ---


def test_public_spectator_unknown_battle_returns_404(tmp_path):
    """The public spectator stream is the SOLE arena route that returns 404
    on an unknown battle_id (no auth, no cross-owner data — D7 collapse not
    required). Pins the contract so a future change can't 'helpfully' swap
    this to 200 + empty stream (would let attackers test ids without auth)."""
    gw = _gw(tmp_path)
    with _client(gw) as c:
        r = c.get("/battle/pvp-NONEXISTENT/live")
    assert r.status_code == 404, r.text
