"""GA-CORE-3 live battle viewer: GET /battle/{id}/live (public spectator) +
GET /me/battle/{id}/live (authenticated owner).

SSE streams of the captured omniscient frame buffer, projected per side via
lineproto.project_frame (LIVE_VIEWER_CONTRACT.md). CI-runnable with no PS server: a
BattleSession is stubbed with a pre-populated frame buffer + ended set, so the stream
replays the buffer then emits the terminal event:end and returns (finite).

The load-bearing properties under test: the owner sees their OWN exact HP (the private
|split| line) but only the opponent's PUBLIC %; the spectator sees only public %; the
|split| marker is NEVER emitted; ratings are blanked except on the owner's own side;
and the owner stream is ownership-scoped (a battle for another account's agent 403s).
"""

from __future__ import annotations

import json
from pathlib import Path

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, BattleSession, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_OWNER = "eddie@oppie.xyz"
_OTHER = "rival@elsewhere.com"
_GH = "12345678"

# Two omniscient frames: a preamble (|player| with ratings) and a damage turn with two
# |split| blocks — p2 (opponent) and p1 (own) — plus a |t:| wall-clock line.
_FRAMES = [
    {
        "seq": 1,
        "turn": 0,
        "raw_lines": ["|player|p1|Alpha||1500", "|player|p2|Bravo||1820", "|start"],
    },
    {
        "seq": 2,
        "turn": 1,
        "raw_lines": [
            "|move|p1a: Garchomp|Earthquake|p2a: Rotom",
            "|split|p2",
            "|-damage|p2a: Rotom|88/250",  # opponent's PRIVATE exact HP — must never leak
            "|-damage|p2a: Rotom|35/100",  # public %
            "|split|p1",
            "|-damage|p1a: Garchomp|176/298",  # owner's OWN exact HP — owner may see it
            "|-damage|p1a: Garchomp|60/100",  # public %
            # the opponent's |request| sideupdate — full private team (bench HP + moves);
            # 330/330 appears ONLY here, so asserting its absence proves |request| is dropped
            # (not the |split| handling).
            '|request|{"side":{"id":"p2","pokemon":['
            '{"ident":"p2: Rotom","condition":"88/250"},'
            '{"ident":"p2: Ferrothorn","condition":"330/330","moves":["spikes"]}]}}',
            "|t:|1700000000",
        ],
    },
]


def _gateway(tmp_path: Path, *, with_session: bool = True) -> ArenaGateway:
    return ArenaGateway(
        authority=ConsentAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        session_authority=(
            SessionAuthority(signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex())
            if with_session
            else None
        ),
    )


def _client(gw: ArenaGateway) -> TestClient:
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


def _seed_battle(gw: ArenaGateway, *, owner: str = _OWNER, agent: str = "oppie") -> str:
    """A finished battle (ended set) for `agent`, with the frame buffer pre-populated."""
    gw.accounts.add_agent(owner, agent)
    sess = BattleSession(
        battle_id="b_live",
        claims_token_id="tok",
        visitor_name=agent,
        lane="rated",
        opponent="anchor",
        seed=[1],
        sidecar=None,
        opponent_policy=None,
    )
    sess.visitor_side = "p1"
    sess.frames = [dict(f) for f in _FRAMES]
    sess.frame_seq = len(_FRAMES)
    sess.ended = {"status": "ended"}  # makes the SSE stream finite
    gw.sessions[sess.battle_id] = sess
    return sess.battle_id


def _parse_sse(text: str) -> tuple[list[dict], bool]:
    """Return (data-frames, saw_end) from an SSE body."""
    frames: list[dict] = []
    saw_end = False
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("event: end"):
            saw_end = True
            continue
        if block.startswith("data: "):
            frames.append(json.loads(block[len("data: ") :]))
    return frames, saw_end


def _auth(gw: ArenaGateway, owner: str = _OWNER) -> dict[str, str]:
    return {"Authorization": f"Bearer {gw.session_auth.mint_session(owner, _GH)}"}


# --------------------------------------------------------------------------- #
# public spectator stream
# --------------------------------------------------------------------------- #


def test_spectator_stream_projects_public_only_and_ends(tmp_path):
    gw = _gateway(tmp_path)
    bid = _seed_battle(gw)
    with _client(gw) as c:
        r = c.get(f"/battle/{bid}/live")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    frames, saw_end = _parse_sse(r.text)
    assert saw_end is True
    assert len(frames) == 2
    all_lines = [ln for fr in frames for ln in fr["lines"]]
    # no |split| marker ever; opponent AND own exact HP both absent; public % present
    assert not any(ln.startswith("|split|") for ln in all_lines)
    assert not any("176/298" in ln for ln in all_lines)  # p1 private exact
    assert not any("88/250" in ln for ln in all_lines)  # p2 private exact
    assert any("35/100" in ln for ln in all_lines)  # opponent public %
    assert any("60/100" in ln for ln in all_lines)  # own public %
    # |request| sideupdate (full private team) NEVER reaches a viewer
    assert not any(ln.startswith("|request|") for ln in all_lines)
    assert not any("330/330" in ln for ln in all_lines)  # bench HP only in |request|
    # ratings blanked on the public stream
    assert "|player|p1|Alpha||" in all_lines
    assert "|player|p2|Bravo||" in all_lines
    # frame schema
    f0 = frames[0]
    assert f0["battle_id"] == bid and f0["side"] == "spectator"
    assert set(f0) == {"battle_id", "turn", "seq", "side", "lines", "ts_ms"}


def test_spectator_stream_404_on_unknown_battle(tmp_path):
    gw = _gateway(tmp_path)
    with _client(gw) as c:
        assert c.get("/battle/nope/live").status_code == 404


# --------------------------------------------------------------------------- #
# authenticated owner stream
# --------------------------------------------------------------------------- #


def test_owner_stream_keeps_own_exact_hp_hides_opponent(tmp_path):
    gw = _gateway(tmp_path)
    bid = _seed_battle(gw)
    with _client(gw) as c:
        r = c.get(f"/me/battle/{bid}/live", headers=_auth(gw))
    assert r.status_code == 200
    frames, saw_end = _parse_sse(r.text)
    assert saw_end is True
    all_lines = [ln for fr in frames for ln in fr["lines"]]
    assert frames[0]["side"] == "p1"
    assert not any(ln.startswith("|split|") for ln in all_lines)
    assert any("176/298" in ln for ln in all_lines)  # owner SEES own exact HP
    assert not any("88/250" in ln for ln in all_lines)  # opponent exact HP hidden
    assert any("35/100" in ln for ln in all_lines)  # opponent public %
    # |request| (opponent's full team) NEVER reaches the owner viewer either
    assert not any(ln.startswith("|request|") for ln in all_lines)
    assert not any("330/330" in ln for ln in all_lines)  # opponent bench HP hidden
    # owner keeps own rating, opponent's blanked
    assert "|player|p1|Alpha||1500" in all_lines
    assert "|player|p2|Bravo||" in all_lines


def test_owner_stream_401_without_bearer(tmp_path):
    gw = _gateway(tmp_path)
    bid = _seed_battle(gw)
    with _client(gw) as c:
        assert c.get(f"/me/battle/{bid}/live").status_code == 401


def test_owner_stream_403_on_bad_session(tmp_path):
    gw = _gateway(tmp_path)
    bid = _seed_battle(gw)
    with _client(gw) as c:
        r = c.get(f"/me/battle/{bid}/live", headers={"Authorization": "Bearer bogus"})
    assert r.status_code == 403


def test_owner_stream_403_for_another_owners_battle(tmp_path):
    """The battle is for _OWNER's agent; _OTHER must not be able to open the owner
    stream (opaque 403 — collapses not-found + not-yours)."""
    gw = _gateway(tmp_path)
    bid = _seed_battle(gw, owner=_OWNER, agent="oppie")
    with _client(gw) as c:
        r = c.get(f"/me/battle/{bid}/live", headers=_auth(gw, _OTHER))
    assert r.status_code == 403


def test_owner_stream_503_when_session_auth_unconfigured(tmp_path):
    gw = _gateway(tmp_path, with_session=False)
    sess = BattleSession(
        battle_id="b1",
        claims_token_id="t",
        visitor_name="oppie",
        lane="rated",
        opponent="anchor",
        seed=[1],
        sidecar=None,
        opponent_policy=None,
    )
    sess.ended = {"status": "ended"}
    gw.sessions["b1"] = sess
    with _client(gw) as c:
        assert c.get("/me/battle/b1/live").status_code == 503
