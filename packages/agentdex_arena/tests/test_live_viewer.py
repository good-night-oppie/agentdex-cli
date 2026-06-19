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

import asyncio
import json
from pathlib import Path

import pytest
from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority, ConsentClaims, _normalize_owner
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


def test_owner_stream_allows_oob_owner_via_session_owner_match(tmp_path):
    """The email/OOB-enroll path mints a battle token + stamps session.owner but does
    NOT add the agent to AccountStore (no account->agent join). The owner-match
    fallback (PR #373) keeps that owner's fog-of-war stream working — without it an
    OOB-enrolled owner is locked out of their OWN live battle. The owner still sees
    own exact HP while the opponent's exact HP stays hidden (the projection is
    unchanged — only the ownership gate gained the fallback)."""
    gw = _gateway(tmp_path)
    sess = BattleSession(
        battle_id="b_oob",
        claims_token_id="tok",
        visitor_name="oppie",
        lane="rated",
        opponent="anchor",
        seed=[1],
        sidecar=None,
        opponent_policy=None,
    )
    sess.visitor_side = "p1"
    sess.owner = _normalize_owner(_OWNER)  # OOB enroll stamps the normalized owner
    sess.frames = [dict(f) for f in _FRAMES]
    sess.frame_seq = len(_FRAMES)
    sess.ended = {"status": "ended"}  # makes the SSE stream finite
    gw.sessions[sess.battle_id] = sess
    # Precondition: the agent is deliberately NOT in the account store (the OOB path
    # has no account->agent row) — so only the session.owner match can authorize.
    assert sess.visitor_name not in gw.accounts.agents_for(_OWNER)
    with _client(gw) as c:
        r = c.get(f"/me/battle/{sess.battle_id}/live", headers=_auth(gw, _OWNER))
    assert r.status_code == 200
    frames, saw_end = _parse_sse(r.text)
    assert saw_end is True
    assert frames[0]["side"] == "p1"
    all_lines = [ln for fr in frames for ln in fr["lines"]]
    assert any("176/298" in ln for ln in all_lines)  # owner SEES own exact HP
    assert not any("88/250" in ln for ln in all_lines)  # opponent exact HP still hidden


def test_owner_stream_403_for_oob_owner_mismatch(tmp_path):
    """The session.owner fallback must NOT widen access: a different verified owner
    whose email does not match session.owner (and who owns no joined agent for this
    battle) still gets the opaque 403 — the fallback authorizes the stamped owner
    only, not any authenticated caller (anti fog-of-war-leak)."""
    gw = _gateway(tmp_path)
    sess = BattleSession(
        battle_id="b_oob2",
        claims_token_id="tok",
        visitor_name="oppie",
        lane="rated",
        opponent="anchor",
        seed=[1],
        sidecar=None,
        opponent_policy=None,
    )
    sess.visitor_side = "p1"
    sess.owner = _normalize_owner(_OWNER)  # battle belongs to _OWNER (OOB)
    sess.frames = [dict(f) for f in _FRAMES]
    sess.frame_seq = len(_FRAMES)
    sess.ended = {"status": "ended"}
    gw.sessions[sess.battle_id] = sess
    with _client(gw) as c:
        r = c.get(f"/me/battle/{sess.battle_id}/live", headers=_auth(gw, _OTHER))
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


@pytest.mark.asyncio
async def test_finish_defers_frame_buffer_eviction_then_reclaims(tmp_path):
    """GA-CORE-3 retention: _finish must NOT wipe session.frames immediately — an
    immediate clear raced an active SSE stream and dropped the winning (final) turn
    (PR #374 review). Instead it stamps frames_evict_after = now + grace so a viewer
    mid-stream at finish drains the decisive final frames + the terminal event:end
    first; _expire_if_stale then reclaims the ~hundreds-of-KB (up to 10 MiB) buffer
    lazily once past the deadline (driven by /state, /choose, or the SSE poll loop)."""
    gw = _gateway(tmp_path)
    clock = {"t": 1_000.0}
    gw.now = lambda: clock["t"]  # deterministic clock for the grace window
    sess = BattleSession(
        battle_id="b_reclaim",
        claims_token_id="tok",
        visitor_name="oppie",
        lane="sandbox",
        opponent="anchor-random",
        seed=[0, 1, 2, 3],
        sidecar=None,
        opponent_policy=None,
    )
    sess.frames = [dict(f) for f in _FRAMES]
    sess.frame_seq = len(_FRAMES)
    sess.live_viewers = 1  # a viewer is mid-stream → _finish DEFERS (PR #377 #3443669243)
    gw.sessions[sess.battle_id] = sess

    await gw._finish(sess, {"winner": "oppie", "turns": 3, "inputLog": ["l1"]})

    assert sess.ended is not None  # battle committed (receipt published)
    # DEFERRED: buffer retained so the live viewer mid-stream still drains the final frames.
    assert sess.frames != []  # NOT wiped at finish (PR #374 dropped-winning-turn race)
    assert sess.frames_evict_after is not None  # eviction deadline stamped

    # Within the grace window: _expire_if_stale is a no-op, buffer retained.
    clock["t"] = sess.frames_evict_after - 0.001
    await gw._expire_if_stale(sess)
    assert sess.frames != []

    # Past the deadline: lazy reclaim frees the buffer (no per-battle heap leak).
    clock["t"] = sess.frames_evict_after + 0.001
    await gw._expire_if_stale(sess)
    assert sess.frames == []  # buffer reclaimed once past the grace deadline


@pytest.mark.asyncio
async def test_forfeit_clears_frame_buffer_immediately_not_deferred(tmp_path):
    """The forfeit/abandoned path clears the live frame buffer IMMEDIATELY, NOT via the
    grace deferral. An abandoned battle timed out precisely because nobody was touching
    it, so there is no active SSE viewer to race — and the reclaim is purely touch-driven
    (the gateway is SLEEPING-tolerant with no background reaper), so deferring there would
    leak the buffer of a session nothing ever touches again. This restores the pre-PR#374
    immediate-clear behavior on the no-viewer path while keeping the deferral only for the
    /choose winning-move path."""
    gw = _gateway(tmp_path)
    clock = {"t": 5_000.0}
    gw.now = lambda: clock["t"]
    sess = BattleSession(
        battle_id="b_forfeit",
        claims_token_id="tok",
        visitor_name="oppie",
        lane="sandbox",
        opponent="anchor-random",
        seed=[0, 1],
        sidecar=None,  # skip the sidecar 'stop' request on the forfeit path
        opponent_policy=None,
    )
    sess.visitor_side = "p1"
    sess.frames = [dict(f) for f in _FRAMES]
    sess.frame_seq = len(_FRAMES)
    sess.last_touch = clock["t"]
    gw.sessions[sess.battle_id] = sess

    # Not yet stale: no forfeit, buffer retained.
    await gw._expire_if_stale(sess)
    assert sess.ended is None
    assert sess.frames != []

    # Idle past the turn budget: abandoned -> forfeit fires.
    clock["t"] = sess.last_touch + gw.turn_budget_s + 1.0
    await gw._expire_if_stale(sess)
    assert sess.ended is not None  # forfeited
    assert sess.ended.get("forfeit") == "turn budget exceeded"
    assert sess.frames == []  # buffer reclaimed IMMEDIATELY on the no-viewer path
    assert sess.frames_evict_after is None  # deferral deadline NOT stamped on forfeit


@pytest.mark.asyncio
async def test_finish_tolerates_malformed_evict_grace_env(tmp_path, monkeypatch):
    """A malformed ARENA_SSE_EVICT_GRACE_SEC must NOT raise out of the battle-commit path
    (_finish): the parse sits ahead of the durable replay-artifact write, so a ValueError
    there would 404 every battle's /replay,/fork,/dispute after a restart and 500 the
    winning /choose. It falls back to 30s; the battle still commits and the buffer is
    still deferred to the (now safe) deadline."""
    monkeypatch.setenv("ARENA_SSE_EVICT_GRACE_SEC", "not-a-number")
    gw = _gateway(tmp_path)
    clock = {"t": 2_000.0}
    gw.now = lambda: clock["t"]
    sess = BattleSession(
        battle_id="b_badenv",
        claims_token_id="tok",
        visitor_name="oppie",
        lane="sandbox",
        opponent="anchor-random",
        seed=[0],
        sidecar=None,
        opponent_policy=None,
    )
    sess.frames = [dict(f) for f in _FRAMES]
    sess.frame_seq = len(_FRAMES)
    sess.live_viewers = 1  # a viewer is mid-stream → _finish takes the defer (grace) path
    gw.sessions[sess.battle_id] = sess

    receipt = await gw._finish(sess, {"winner": "oppie", "turns": 3, "inputLog": ["l1"]})

    assert receipt is not None  # _finish ran to completion (past the artifact write)
    assert sess.ended is not None  # battle committed despite the malformed env
    assert sess.frames_evict_after == 2_030.0  # fell back to the 30s default deadline


def _stale_session(gw, clock, *, battle_id):
    sess = BattleSession(
        battle_id=battle_id,
        claims_token_id="tok",
        visitor_name="oppie",
        lane="sandbox",
        opponent="anchor-random",
        seed=[0, 1],
        sidecar=None,  # skip the sidecar 'stop' request on the forfeit path
        opponent_policy=None,
    )
    sess.visitor_side = "p1"
    sess.frames = [dict(f) for f in _FRAMES]
    sess.frame_seq = len(_FRAMES)
    sess.last_touch = clock["t"]
    gw.sessions[sess.battle_id] = sess
    return sess


@pytest.mark.asyncio
async def test_concurrent_expire_forfeits_once_not_twice(tmp_path):
    """Two SSE streams polling the SAME stale battle concurrently must NOT both drive the
    forfeit branch — that would append two battle_end/period rows and let the ladder count
    the timeout twice (PR #377 review 3443669247). The synchronous session.forfeiting
    marker (set before the first await) makes the second caller short-circuit the guard."""
    gw = _gateway(tmp_path)
    clock = {"t": 9_000.0}
    gw.now = lambda: clock["t"]
    sess = _stale_session(gw, clock, battle_id="b_conc")

    calls = {"n": 0}
    real_finish = gw._finish

    async def counting_finish(*a, **k):
        calls["n"] += 1
        await asyncio.sleep(0)  # yield so the concurrent caller runs its guard meanwhile
        return await real_finish(*a, **k)

    gw._finish = counting_finish

    # Idle past the turn budget -> abandoned; fire two expiries concurrently.
    clock["t"] = sess.last_touch + gw.turn_budget_s + 1.0
    await asyncio.gather(gw._expire_if_stale(sess), gw._expire_if_stale(sess))

    assert calls["n"] == 1  # forfeit committed EXACTLY once (no double-_finish)
    assert sess.ended is not None
    assert sess.ended.get("forfeit") == "turn budget exceeded"
    assert sess.forfeiting is True  # marker stays set on a committed forfeit


@pytest.mark.asyncio
async def test_expire_skips_forfeit_when_already_forfeiting(tmp_path):
    """The guard short-circuits when session.forfeiting is already set, even for a stale
    battle — the in-flight forfeit owns the commit."""
    gw = _gateway(tmp_path)
    clock = {"t": 7_000.0}
    gw.now = lambda: clock["t"]
    sess = _stale_session(gw, clock, battle_id="b_inflight")
    sess.forfeiting = True  # another caller already claimed the forfeit

    clock["t"] = sess.last_touch + gw.turn_budget_s + 1.0
    await gw._expire_if_stale(sess)

    assert sess.ended is None  # this caller did NOT re-forfeit


@pytest.mark.asyncio
async def test_public_spectator_stream_does_not_forfeit(tmp_path):
    """allow_forfeit=False (the UNAUTHENTICATED public /battle/{id}/live spectator path)
    must NOT drive the stale-forfeit commit — a read-only spectator cannot decide when a
    rated battle is durably committed (PR #377 review 3443669242). An authenticated touch
    (default allow_forfeit=True) still forfeits the same abandoned battle."""
    gw = _gateway(tmp_path)
    clock = {"t": 8_000.0}
    gw.now = lambda: clock["t"]
    sess = _stale_session(gw, clock, battle_id="b_spec")

    clock["t"] = sess.last_touch + gw.turn_budget_s + 1.0
    await gw._expire_if_stale(sess, allow_forfeit=False)  # public/spectator: reclaim-only
    assert sess.ended is None  # NOT forfeited by the unauthenticated stream
    assert sess.forfeiting is False  # never even claimed

    await gw._expire_if_stale(sess)  # authenticated touch (owner/state/choose) DOES forfeit
    assert sess.ended is not None
    assert sess.ended.get("forfeit") == "turn budget exceeded"


@pytest.mark.asyncio
async def test_reclaim_runs_even_when_forfeit_disallowed(tmp_path):
    """allow_forfeit gates ONLY the forfeit branch — the finished-buffer reclaim still runs
    on a public spectator stream (a finished battle's buffer is freed past its grace
    regardless of who is watching)."""
    gw = _gateway(tmp_path)
    clock = {"t": 3_000.0}
    gw.now = lambda: clock["t"]
    sess = _stale_session(gw, clock, battle_id="b_recl")
    sess.ended = {"status": "ended"}
    sess.frames_evict_after = clock["t"] + 30.0

    clock["t"] = sess.frames_evict_after + 1.0
    await gw._expire_if_stale(sess, allow_forfeit=False)
    assert sess.frames == []  # reclaim still ran under allow_forfeit=False


@pytest.mark.asyncio
async def test_finish_clears_immediately_when_no_live_viewer(tmp_path):
    """A /choose finish with NO live SSE viewer reclaims the buffer IMMEDIATELY — there is
    no viewer to race, and deferring would leak the buffer of a finished-but-unobserved
    session forever (no background reaper, sessions linger; PR #377 review 3443669243)."""
    gw = _gateway(tmp_path)
    clock = {"t": 4_000.0}
    gw.now = lambda: clock["t"]
    sess = BattleSession(
        battle_id="b_noviewer",
        claims_token_id="tok",
        visitor_name="oppie",
        lane="sandbox",
        opponent="anchor-random",
        seed=[0, 1],
        sidecar=None,
        opponent_policy=None,
    )
    sess.frames = [dict(f) for f in _FRAMES]
    sess.frame_seq = len(_FRAMES)
    assert sess.live_viewers == 0  # nobody streaming
    gw.sessions[sess.battle_id] = sess

    await gw._finish(sess, {"winner": "oppie", "turns": 3, "inputLog": ["l1"]})

    assert sess.ended is not None  # battle committed
    assert sess.frames == []  # reclaimed immediately (no viewer to race)
    assert sess.frames_evict_after is None  # no deferral deadline stamped


def test_finished_stream_reclaims_buffer_on_last_viewer_exit(tmp_path):
    """The last SSE viewer of a finished battle reclaims the frame buffer when its stream
    ends, so a /choose-then-leave battle does not leak it — touch-driven, no background
    reaper (PR #377 review 3443669243)."""
    gw = _gateway(tmp_path)
    bid = _seed_battle(gw)  # finished battle (ended set), frames pre-populated
    assert gw.sessions[bid].frames != []
    with _client(gw) as c:
        r = c.get(f"/battle/{bid}/live")  # public spectator drains, emits event:end, exits
    assert r.status_code == 200
    frames, saw_end = _parse_sse(r.text)
    assert saw_end is True  # the viewer DID drain + see the terminal event:end first
    assert len(frames) == 2  # frames were streamed BEFORE the buffer was reclaimed
    assert gw.sessions[bid].frames == []  # buffer reclaimed on the last viewer's exit
    assert gw.sessions[bid].live_viewers == 0  # refcount balanced


def test_state_and_choose_409_during_inflight_forfeit(tmp_path, caplog):
    """While a concurrent caller is mid-forfeit (session.forfeiting set, awaiting
    stop/_finish behind the rated finish lock), session.ended is not set YET. /state must
    NOT render a stale ``your_move`` and /choose must NOT attempt a sidecar step that races
    the stop — both return a transient 409 the client retries (PR #378 review 3443735244).
    The opaque 409 body hides the reason, so we assert it via the server-side log."""
    gw = _gateway(tmp_path)
    pub = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
    claims = ConsentClaims(
        token_id="tok_inflight",
        owner=_OWNER,
        agent_name="oppie",
        agent_pubkey_hex=pub,
        scopes=["battle"],
        issued_at=0.0,
        expires_at=4.0e12,
        confirmed_via="test",
    )
    token = gw.authority.mint(claims)
    sess = BattleSession(
        battle_id="b_forf",
        claims_token_id=claims.token_id,
        visitor_name="oppie",
        lane="sandbox",
        opponent="anchor-random",
        seed=[1],
        sidecar=None,
        opponent_policy=None,
    )
    sess.forfeiting = True  # a concurrent caller already claimed the forfeit; ended is None
    gw.sessions[sess.battle_id] = sess

    with _client(gw) as c, caplog.at_level("WARNING"):
        rs = c.get(
            f"/battle/{sess.battle_id}/state",
            headers={"Authorization": f"Bearer {token}"},
        )
        rc = c.post(f"/battle/{sess.battle_id}/choose", json={"token": token, "choice_index": 1})

    assert rs.status_code == 409  # /state: not a stale your_move
    assert rc.status_code == 409  # /choose: not a sidecar step racing the stop
    # The opaque body hides the detail; the server logs the real reason — assert BOTH
    # handlers took the in-flight-forfeit branch (not the no-pending fallback 409).
    finishing = [r for r in caplog.records if "battle is finishing (timed out)" in r.getMessage()]
    assert len(finishing) >= 2
