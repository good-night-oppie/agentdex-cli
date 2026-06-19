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


def test_me_battles_includes_forks(tmp_path):
    """A battle_fork carries only parent_battle_id/fork_turn (no visitor/opponent/
    lane); me_battles inherits them from the parent so the fork's battle_end is scoped
    to the owner instead of silently dropped (PR #370 review)."""
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")
    # parent battle names the visitor
    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "par",
            "lane": "sandbox",
            "visitor": "oppie",
            "opponent": "anchor",
        },
    )
    gw.events.append(
        "battle_end",
        {
            "tenant_id": "tok",
            "battle_id": "par",
            "lane": "sandbox",
            "winner": "oppie",
            "turns": 4,
            "input_log_blake2b16": "e" * 32,
        },
    )
    # a fork of par — NO visitor/opponent/lane on the fork event
    gw.events.append(
        "battle_fork",
        {"tenant_id": "tok", "battle_id": "frk", "parent_battle_id": "par", "fork_turn": 2},
    )
    gw.events.append(
        "battle_end",
        {
            "tenant_id": "tok",
            "battle_id": "frk",
            "winner": "oppie",
            "turns": 6,
            "input_log_blake2b16": "f" * 32,
        },
    )
    with _client(gw) as c:
        recent = c.get("/me/battles", headers=_auth(gw)).json()["recent"]
    by_id = {r["battle_id"]: r for r in recent}
    assert set(by_id) == {"par", "frk"}  # the fork is no longer dropped
    assert by_id["frk"]["agent_name"] == "oppie"  # visitor inherited from the parent
    assert by_id["frk"]["lane"] == "sandbox"
    assert by_id["frk"]["replay"] == "/replay/frk"


def test_me_agents_excludes_quarantined_from_wl(tmp_path):
    """A quarantined battle is dropped from the public rating/games by
    recompute_ladder; me_agents must exclude it from W/L too, else /me/agents
    diverges from /ladder for a disputed account (PR #370 review)."""
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")
    gw.events.append("register", {"name": "oppie", "frozen": False})
    gw.events.append("register", {"name": "rival", "frozen": False})
    gw.events.append(
        "period",
        {
            "events": [
                {
                    "battle_id": "clean",
                    "p1": "oppie",
                    "p2": "rival",
                    "winner": "oppie",
                    "input_log_blake2b16": "1" * 32,
                },
                {
                    "battle_id": "dirty",
                    "p1": "oppie",
                    "p2": "rival",
                    "winner": "oppie",
                    "input_log_blake2b16": "2" * 32,
                },
            ]
        },
    )
    gw.events.append("quarantine", {"battle_id": "dirty", "reason": "collusion"})
    with _client(gw) as c:
        [row] = c.get("/me/agents", headers=_auth(gw)).json()["agents"]
    # only the clean battle counts — consistent with the authoritative ladder
    assert row["wins"] == 1 and row["losses"] == 0 and row["ties"] == 0
    assert row["games"] == 1


def test_me_agent_team_and_genome_endpoints(tmp_path):
    import hashlib
    import json

    from agentdex_arena.consent import _normalize_owner

    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")

    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b_team",
            "lane": "rated",
            "visitor": "oppie",
            "opponent": "scout",
            "team_hash": "dummy_team_hash",
        },
    )
    gw.events.append(
        "battle_end",
        {
            "tenant_id": "tok",
            "battle_id": "b_team",
            "lane": "rated",
            "winner": "oppie",
            "turns": 5,
            "input_log_blake2b16": "a" * 32,
        },
    )

    owner_norm = _normalize_owner(_OWNER)
    owner_dir = hashlib.blake2b(owner_norm.encode("utf-8"), digest_size=8).hexdigest()
    team_dir = tmp_path / "arena" / "teams" / owner_dir
    team_dir.mkdir(parents=True, exist_ok=True)
    team_file = team_dir / "dummy_team_hash.json"
    team_file.write_text(json.dumps({"team_packed": "packed_payload_here"}))

    with _client(gw) as c:
        # GET /me/agents/oppie/team
        resp_team = c.get("/me/agents/oppie/team", headers=_auth(gw))
        assert resp_team.status_code == 200
        data_team = resp_team.json()
        assert data_team["agent_name"] == "oppie"
        assert data_team["team_hash"] == "dummy_team_hash"
        assert data_team["team_packed"] == "packed_payload_here"
        assert data_team["genome_hash"] == "dummy_team_hash"
        assert data_team["genome_packed"] == "packed_payload_here"

        # GET /me/agents/oppie/genome
        resp_genome = c.get("/me/agents/oppie/genome", headers=_auth(gw))
        assert resp_genome.status_code == 200
        data_genome = resp_genome.json()
        assert data_genome["agent_name"] == "oppie"
        assert data_genome["team_hash"] == "dummy_team_hash"
        assert data_genome["team_packed"] == "packed_payload_here"
        assert data_genome["genome_hash"] == "dummy_team_hash"
        assert data_genome["genome_packed"] == "packed_payload_here"

        # Check authorization failure cases
        assert c.get("/me/agents/oppie/team").status_code == 401
        assert c.get("/me/agents/oppie/genome").status_code == 401

        # Check someone else's agent / non-existent agent
        assert c.get("/me/agents/rival/team", headers=_auth(gw)).status_code == 403
        assert c.get("/me/agents/rival/genome", headers=_auth(gw)).status_code == 403


def test_me_agent_team_mixed_window(tmp_path):
    # Case 1: Multiple different team hashes -> True
    gw = _gateway(tmp_path / "mixed_1")
    gw.accounts.add_agent(_OWNER, "oppie")
    gw.events.append("register", {"name": "oppie", "frozen": False})
    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b1",
            "lane": "rated",
            "visitor": "oppie",
            "team_hash": "hash1",
        },
    )
    gw.events.append("battle_end", {"tenant_id": "tok", "battle_id": "b1", "winner": "oppie"})
    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b2",
            "lane": "rated",
            "visitor": "oppie",
            "team_hash": "hash2",
        },
    )
    gw.events.append("battle_end", {"tenant_id": "tok", "battle_id": "b2", "winner": "oppie"})
    with _client(gw) as c:
        agents_resp = c.get("/me/agents", headers=_auth(gw)).json()
        team_resp = c.get("/me/agents/oppie/team", headers=_auth(gw)).json()
    assert agents_resp["agents"][0]["team_summary"]["mixed_window"] is True
    assert team_resp["rating_context"]["mixed_window"] is True

    # Case 2: One captured team, one uncaptured battle -> True
    gw2 = _gateway(tmp_path / "mixed_2")
    gw2.accounts.add_agent(_OWNER, "oppie")
    gw2.events.append("register", {"name": "oppie", "frozen": False})
    gw2.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b3",
            "lane": "rated",
            "visitor": "oppie",
            "team_hash": "hash1",
        },
    )
    gw2.events.append("battle_end", {"tenant_id": "tok", "battle_id": "b3", "winner": "oppie"})
    gw2.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b4",
            "lane": "rated",
            "visitor": "oppie",
            "team_hash": None,
        },
    )
    gw2.events.append("battle_end", {"tenant_id": "tok", "battle_id": "b4", "winner": "oppie"})
    with _client(gw2) as c:
        agents_resp = c.get("/me/agents", headers=_auth(gw2)).json()
        team_resp = c.get("/me/agents/oppie/team", headers=_auth(gw2)).json()
    assert agents_resp["agents"][0]["team_summary"]["mixed_window"] is True
    assert team_resp["rating_context"]["mixed_window"] is True

    # Case 3: Single team, no uncaptured -> False
    gw3 = _gateway(tmp_path / "mixed_3")
    gw3.accounts.add_agent(_OWNER, "oppie")
    gw3.events.append("register", {"name": "oppie", "frozen": False})
    gw3.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b5",
            "lane": "rated",
            "visitor": "oppie",
            "team_hash": "hash1",
        },
    )
    gw3.events.append("battle_end", {"tenant_id": "tok", "battle_id": "b5", "winner": "oppie"})
    with _client(gw3) as c:
        agents_resp = c.get("/me/agents", headers=_auth(gw3)).json()
        team_resp = c.get("/me/agents/oppie/team", headers=_auth(gw3)).json()
    assert agents_resp["agents"][0]["team_summary"]["mixed_window"] is False
    assert team_resp["rating_context"]["mixed_window"] is False


def test_me_agent_team_quarantine_exclusion(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")
    gw.events.append("register", {"name": "oppie", "frozen": False})

    # First rated battle, ends successfully. team_hash is hash1.
    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b1",
            "lane": "rated",
            "visitor": "oppie",
            "team_hash": "hash1",
        },
    )
    gw.events.append("battle_end", {"tenant_id": "tok", "battle_id": "b1", "winner": "oppie"})

    # Second rated battle, ends successfully. team_hash is hash2.
    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b2",
            "lane": "rated",
            "visitor": "oppie",
            "team_hash": "hash2",
        },
    )
    gw.events.append("battle_end", {"tenant_id": "tok", "battle_id": "b2", "winner": "oppie"})

    # Quarantine the second battle
    gw.events.append("quarantine", {"battle_id": "b2", "reason": "collusion"})

    with _client(gw) as c:
        agents_resp = c.get("/me/agents", headers=_auth(gw)).json()
        team_resp = c.get("/me/agents/oppie/team", headers=_auth(gw)).json()

    # HUD should fall back to previous team_hash ("hash1"), and mixed_window should be False since hash2 is ignored.
    assert agents_resp["agents"][0]["team_summary"]["team_hash"] == "hash1"
    assert agents_resp["agents"][0]["team_summary"]["mixed_window"] is False

    assert team_resp["team_hash"] == "hash1"
    assert team_resp["rating_context"]["mixed_window"] is False


def test_me_agent_team_capture_failure_fail_safe(tmp_path, caplog):
    import asyncio
    import logging
    from unittest import mock

    from agentdex_arena.consent import ConsentClaims
    from agentdex_arena.gateway import BeginRequest

    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")

    # Construct the BeginRequest and ConsentClaims
    req = BeginRequest(
        token="tok12345",
        battle_nonce="rated-nonce-test",
        pop_signature_hex="sig_hex",
        lane="sandbox",
        team="p1_team_packed",
    )

    claims = ConsentClaims(
        token_id="tok12345",
        owner=_OWNER,
        agent_name="oppie",
        agent_pubkey_hex="0" * 64,
        scopes=["battle"],
        issued_at=0.0,
        expires_at=9_999_999_999.0,
        confirmed_via="test",
    )

    # Set up our mocked artifacts_dir that raises an exception when division or write is attempted
    mock_artifacts_dir = mock.MagicMock()
    mock_artifacts_dir.__truediv__.side_effect = Exception("mocked write failure")
    gw.artifacts_dir = mock_artifacts_dir

    class _FakeSidecar:
        async def request(self, cmd: str, **kwargs):
            return {"state": {}}

    async def _fake_pack_team(sidecar, team_spec):
        return "fakepacked"

    async def _fake_validate_team(sidecar, team_packed):
        return True, []

    # Mock _advance so we don't execute a real battle simulation step
    async def _fake_advance(session, state, visitor_choice=None):
        return {"state": {}}

    with (
        mock.patch("agentdex_arena.gateway.pack_team", _fake_pack_team),
        mock.patch("agentdex_arena.gateway.validate_team", _fake_validate_team),
        mock.patch.object(gw, "_advance", _fake_advance),
        caplog.at_level(logging.WARNING),
    ):
        res = asyncio.run(
            gw._run_battle_begin(
                req=req,
                claims=claims,
                owner_norm=_OWNER,
                sidecar=_FakeSidecar(),
                on_published=lambda: None,
            )
        )

    assert res is not None
    assert "battle_id" in res

    # Verify that the warning log was recorded
    assert "Failed to capture team/build identity" in caplog.text

    # Verify that the battle_begin event was written to the event log with team_hash=None
    events = list(gw.events.iter_events())
    assert len(events) == 1
    begin_event = events[0]
    assert begin_event["type"] == "battle_begin"
    assert begin_event["payload"]["team_hash"] is None
