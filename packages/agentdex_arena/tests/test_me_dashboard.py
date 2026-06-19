"""GA-CORE-5 dashboard data API: GET /me/agents, /me/battles, /me/ladder.

Session-authed, owner-scoped, FREE reads (no membership, no quota) that back the
agentdex.builders dashboard (US-2.1 roster + US-5.1 highlighted ladder). The
/me/ladder slice reads the SAME source as /ladder (anti-pay-to-rank: a /me view can
never diverge from the public ladder). All three are CI-runnable with no PS server —
ladder/W-L are seeded by appending register/period events; a live battle is a
BattleSession stub with ended=None.
"""

from __future__ import annotations

from pathlib import Path

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, BattleSession, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_OWNER = "eddie@oppie.xyz"
_OTHER = "someone@else.com"
_GH_ID = "12345678"


def _gateway(tmp_path: Path, *, with_session: bool = True) -> ArenaGateway:
    session = (
        SessionAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
        if with_session
        else None
    )
    return ArenaGateway(
        authority=ConsentAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        session_authority=session,
    )


def _client(gw: ArenaGateway) -> TestClient:
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


def _auth(gw: ArenaGateway, owner: str = _OWNER, gh: str = _GH_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {gw.session_auth.mint_session(owner, gh)}"}


def _seed_rated(gw: ArenaGateway, name: str, *, vs: str, winner: str, battle_id: str) -> None:
    """Append the durable events recompute_ladder + me_agents read: register both
    entrants, then a period naming the outcome (winner='' is a tie)."""
    gw.events.append("register", {"name": name, "frozen": False})
    gw.events.append("register", {"name": vs, "frozen": False})
    gw.events.append(
        "period",
        {
            "events": [
                {
                    "battle_id": battle_id,
                    "p1": name,
                    "p2": vs,
                    "winner": winner,
                    "input_log_blake2b16": "0" * 32,
                }
            ]
        },
    )


# --------------------------------------------------------------------------- #
# Auth posture (shared _require_session guard, exercised via /me/agents).
# --------------------------------------------------------------------------- #


def test_me_503_when_session_auth_unconfigured(tmp_path):
    gw = _gateway(tmp_path, with_session=False)
    with _client(gw) as c:
        assert c.get("/me/agents").status_code == 503
        assert c.get("/me/battles").status_code == 503
        assert c.get("/me/ladder").status_code == 503


def test_me_401_without_bearer(tmp_path):
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        assert c.get("/me/agents").status_code == 401
        assert c.get("/me/battles", headers={"Authorization": "Token x"}).status_code == 401


def test_me_403_on_bad_session(tmp_path):
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        assert (
            c.get("/me/ladder", headers={"Authorization": "Bearer not-a-token"}).status_code == 403
        )


# --------------------------------------------------------------------------- #
# /me/agents
# --------------------------------------------------------------------------- #


def test_me_agents_empty_when_none_enrolled(tmp_path):
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        body = c.get("/me/agents", headers=_auth(gw)).json()
    assert body == {"owner": _OWNER, "agents": []}


def test_me_agents_roster_with_rating_and_wl(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")
    _seed_rated(gw, "oppie", vs="scout", winner="oppie", battle_id="b1")
    with _client(gw) as c:
        body = c.get("/me/agents", headers=_auth(gw)).json()
    assert body["owner"] == _OWNER
    [row] = body["agents"]
    assert row["agent_name"] == "oppie"
    assert row["wins"] == 1 and row["losses"] == 0 and row["ties"] == 0
    assert row["games"] == 1  # rated game counted in the Glicko period
    assert row["rating"] > 0
    assert row["genome_summary"] is None  # no server-side genome store yet (PR2)
    assert row["live"] is False


def test_me_agents_loss_and_tie_tallied(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")
    gw.events.append("register", {"name": "oppie", "frozen": False})
    gw.events.append("register", {"name": "rival", "frozen": False})
    gw.events.append(
        "period",
        {
            "events": [
                {
                    "battle_id": "L",
                    "p1": "oppie",
                    "p2": "rival",
                    "winner": "rival",
                    "input_log_blake2b16": "a" * 32,
                },
                {
                    "battle_id": "T",
                    "p1": "rival",
                    "p2": "oppie",
                    "winner": "",
                    "input_log_blake2b16": "b" * 32,
                },
            ]
        },
    )
    with _client(gw) as c:
        [row] = c.get("/me/agents", headers=_auth(gw)).json()["agents"]
    assert row["wins"] == 0 and row["losses"] == 1 and row["ties"] == 1


def test_me_agents_isolated_per_owner(tmp_path):
    """Another owner's agent must NOT appear in my roster."""
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "mine")
    gw.accounts.add_agent(_OTHER, "theirs")
    with _client(gw) as c:
        names = {a["agent_name"] for a in c.get("/me/agents", headers=_auth(gw)).json()["agents"]}
    assert names == {"mine"}


def test_me_agents_live_flag_reflects_inflight_session(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")
    gw.sessions["live1"] = BattleSession(
        battle_id="live1",
        claims_token_id="tok",
        visitor_name="oppie",
        lane="sandbox",
        opponent="anchor",
        seed=[1],
        sidecar=None,
        opponent_policy=None,
    )  # ended defaults to None -> live
    with _client(gw) as c:
        [row] = c.get("/me/agents", headers=_auth(gw)).json()["agents"]
    assert row["live"] is True


# --------------------------------------------------------------------------- #
# /me/ladder
# --------------------------------------------------------------------------- #


def test_me_ladder_is_owner_scoped_slice_of_public(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")
    _seed_rated(gw, "oppie", vs="rival", winner="oppie", battle_id="b1")  # both get games>0
    with _client(gw) as c:
        public = c.get("/ladder").json()["entrants"]
        mine = c.get("/me/ladder", headers=_auth(gw)).json()["entrants"]
    assert "oppie" in public and "rival" in public  # public has both
    assert set(mine) == {"oppie"}  # /me only my agent
    assert mine["oppie"] == public["oppie"]  # SAME source — byte-identical entry


def test_me_ladder_empty_when_no_owned_entrants(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "unrated")  # enrolled but never played -> not on ladder
    _seed_rated(gw, "stranger", vs="other", winner="stranger", battle_id="b9")
    with _client(gw) as c:
        assert c.get("/me/ladder", headers=_auth(gw)).json() == {"entrants": {}}


# --------------------------------------------------------------------------- #
# /me/battles
# --------------------------------------------------------------------------- #


def test_me_battles_lists_live_and_recent(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")
    # a live (in-flight) session
    gw.sessions["live1"] = BattleSession(
        battle_id="live1",
        claims_token_id="tok",
        visitor_name="oppie",
        lane="rated",
        opponent="anchor",
        seed=[1],
        sidecar=None,
        opponent_policy=None,
    )
    # a finished battle in the durable log (begin pairs visitor; end carries winner)
    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "done1",
            "lane": "rated",
            "visitor": "oppie",
            "opponent": "anchor",
        },
    )
    gw.events.append(
        "battle_end",
        {
            "tenant_id": "tok",
            "battle_id": "done1",
            "lane": "rated",
            "winner": "oppie",
            "turns": 7,
            "input_log_blake2b16": "c" * 32,
        },
    )
    with _client(gw) as c:
        body = c.get("/me/battles", headers=_auth(gw)).json()
    assert body["live"] == ["live1"]
    [rec] = body["recent"]
    assert rec["battle_id"] == "done1"
    assert rec["agent_name"] == "oppie"
    assert rec["winner"] == "oppie" and rec["turns"] == 7
    assert rec["replay"] == "/replay/done1"


def test_me_battles_isolated_per_owner(tmp_path):
    """A finished battle for another owner's agent must not surface in my list."""
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "mine")
    gw.accounts.add_agent(_OTHER, "theirs")
    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "t2",
            "battle_id": "x",
            "lane": "rated",
            "visitor": "theirs",
            "opponent": "anchor",
        },
    )
    gw.events.append(
        "battle_end",
        {
            "tenant_id": "t2",
            "battle_id": "x",
            "lane": "rated",
            "winner": "theirs",
            "turns": 3,
            "input_log_blake2b16": "d" * 32,
        },
    )
    with _client(gw) as c:
        body = c.get("/me/battles", headers=_auth(gw)).json()
    assert body["live"] == [] and body["recent"] == []


def test_me_battles_empty_for_fresh_account(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")
    with _client(gw) as c:
        assert c.get("/me/battles", headers=_auth(gw)).json() == {
            "owner": _OWNER,
            "live": [],
            "recent": [],
        }
