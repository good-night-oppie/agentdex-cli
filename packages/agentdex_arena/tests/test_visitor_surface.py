"""Phase-A8 — visiting-agent surface (A1/A3/A6 gate anchors).

Criteria:
- no injection-corpus payload mutates state, escapes the tool surface, or
  reaches rendered output unsanitized (launch-blocking gate)
- enrollment provably requires a human action an agent cannot complete alone
- design-partner full loop: license -> draft -> battle -> receipt -> mutation
  -> sandbox rematch (≤10 non-turn calls; per-turn chooses stream inside)
- rated events only from server-matchmade battles (/sandbox is unrated)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
import yaml
from adx_showdown.sidecar import Sidecar, sidecar_available
from agentdex_arena.consent import ConsentAuthority, ConsentClaims, ConsentError
from agentdex_arena.gateway import ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(sidecar_available() is not None, reason=str(sidecar_available()))

CORPUS = yaml.safe_load(
    (
        Path(__file__).resolve().parents[3] / "tests" / "redteam" / "injection_corpus.yaml"
    ).read_text()
)["payloads"]


def _payload_value(p: dict) -> str:
    if "value_repeat" in p:
        return p["value_repeat"]["char"] * p["value_repeat"]["times"]
    return str(p["value"])


# A structurally-valid packed team that is banlist-illegal in gen9ou (Koraidon is
# tagged Uber). Stable for the CI-pinned pokemon-showdown version, same posture as
# the starter-pack fixtures. Used to prove validate-on-begin rejects it server-side.
ILLEGAL_TEAM = (
    "Koraidon||Leftovers|OrichalcumPulse|FlareBlitz,CollisionCourse,DrainPunch,"
    "SwordsDance|Jolly|,252,,,,252|||||,,,,,Fire"
)


@pytest.fixture()
def arena(tmp_path: Path):
    signing_key = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    authority = ConsentAuthority(signing_key_hex=signing_key)
    owner_inbox: dict[str, str] = {}
    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: owner_inbox.__setitem__(owner, code),
    )
    app = create_app(gateway, sidecar_factory=Sidecar)
    agent_key = Ed25519PrivateKey.generate()
    # Enter the TestClient as a context manager so ALL requests share one
    # persistent event loop (matching uvicorn). The persistent sidecar binds its
    # reader task + futures to that loop; the default per-request-loop TestClient
    # would strand the cached sidecar after the first battle request.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, gateway, owner_inbox, agent_key


def _enroll(client, owner_inbox, agent_key, *, owner="eddie@oppie.xyz", name="PartnerBot"):
    r1 = client.post(
        "/enroll/request",
        json={
            "owner": owner,
            "agent_name": name,
            "agent_pubkey_hex": agent_key.public_key().public_bytes_raw().hex(),
        },
    )
    assert r1.status_code == 200
    assert "code" not in r1.text.lower() or "confirmation code sent" in r1.text
    code = owner_inbox[owner]  # OUT-OF-BAND: only the owner has this
    r2 = client.post(f"/enroll/confirm/{code}")
    assert r2.status_code == 200
    return r2.json()["token"]


def _begin_battle(client, gateway, token, agent_key, *, lane="sandbox", team=None):
    start = client.post("/battle/start", json={"token": token}).json()
    nonce = start["battle_nonce"]
    sig = agent_key.sign(start["pop_challenge"].encode()).hex()
    body = {"token": token, "battle_nonce": nonce, "pop_signature_hex": sig, "lane": lane}
    if team:
        body["team"] = team
    resp = client.post("/battle/begin", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _play_to_end(client, token, state, *, max_turns=400):
    calls = 0
    while state.get("status") == "your_move":
        resp = client.post(
            f"/battle/{state['battle_id']}/choose",
            json={"token": token, "choice_index": 1},
        )
        assert resp.status_code == 200, resp.text
        nxt = resp.json()
        nxt.setdefault("battle_id", state["battle_id"])
        state = nxt
        calls += 1
        assert calls < max_turns
    return state, calls


def test_enrollment_requires_human_out_of_band(arena):
    """A1: the agent alone cannot complete enrollment."""
    client, gateway, owner_inbox, agent_key = arena
    r1 = client.post(
        "/enroll/request",
        json={
            "owner": "owner@example.com",
            "agent_name": "LoneAgent",
            "agent_pubkey_hex": agent_key.public_key().public_bytes_raw().hex(),
        },
    )
    assert r1.status_code == 200
    body = r1.json()
    assert "token" not in body and "code" not in body, (
        "agent-visible response must not leak the code"
    )
    # agent guesses codes -> opaque 404s; no token without the owner's code
    for guess in ("0" * 22, "wrong", owner_inbox["owner@example.com"][:-2] + "xx"):
        r = client.post(f"/enroll/confirm/{guess}")
        assert r.status_code == 404
        assert r.json()["detail"].startswith("arena error (ref:")
    print("\nCONSENT_FLOW: agent-only enrollment blocked; owner code path mints below")
    token = _enroll(client, owner_inbox, agent_key, owner="owner@example.com", name="LoneAgent")
    assert token.count(".") == 1


@pytest.mark.timeout(900)
def test_design_partner_full_loop(arena):
    """The day-one loop: license -> draft -> battle -> receipt -> mutation ->
    sandbox rematch. ≤10 non-turn calls; turn chooses stream inside."""
    client, gateway, owner_inbox, agent_key = arena
    non_turn_calls = 0

    token = _enroll(client, owner_inbox, agent_key)  # 2 calls
    non_turn_calls += 2
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")  # 2 calls
    non_turn_calls += 2
    receipt, turn_calls = _play_to_end(client, token, state)
    assert receipt["status"] == "ended"
    assert "failure_signatures" in receipt and "replay" in receipt
    assert "rating" not in receipt, "sandbox battles are UNRATED (A3)"

    replay = client.get(receipt["replay"]).json()  # 1 call
    non_turn_calls += 1
    assert replay["input_log"], "replay receipt must carry the re-simulable inputLog"

    seeds = client.post(
        "/evolution/request", json={"token": token, "reasoning": "lost to gym leader"}
    ).json()  # 1 call
    non_turn_calls += 1
    assert seeds["team_candidates"], "offered seeds must include validated team mutations"
    assert all(s["application_unverified"] for s in seeds["advisory_seeds"])
    mutated_team = seeds["team_candidates"][0]["packed"]

    state2 = _begin_battle(client, gateway, token, agent_key, lane="sandbox", team=mutated_team)
    non_turn_calls += 2
    receipt2, turn_calls2 = _play_to_end(client, token, state2)
    assert receipt2["status"] == "ended"
    print(
        f"\nDESIGN_PARTNER_LOOP: non_turn_calls={non_turn_calls} (<=10), "
        f"battle1={turn_calls} turns streamed, battle2={turn_calls2}; "
        f"receipt1 win={receipt['you_won']} sigs={len(receipt['failure_signatures'])}"
    )
    assert non_turn_calls <= 10


@pytest.mark.timeout(900)
def test_rated_lane_server_matchmade_only(arena):
    """A3: rated receipts carry rating + post-result seed disclosure; the
    ladder contains ONLY rated events; sandbox leaves no rating trace."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="RatedBot")

    sandbox_state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    _play_to_end(client, token, sandbox_state)
    assert client.get("/ladder").json()["entrants"] == {}, "sandbox must not rate"

    rated_state = _begin_battle(client, gateway, token, agent_key, lane="rated")
    receipt, _ = _play_to_end(client, token, rated_state)
    assert receipt["lane"] == "rated" and "rating" in receipt
    assert receipt["rating"]["published_delta"] == "INCONCLUSIVE" or isinstance(
        receipt["rating"]["published_delta"], float
    )
    assert receipt["rating"]["seed_disclosure"], "rated seed revealed post-result (A3)"
    entrants = client.get("/ladder").json()["entrants"]
    assert "RatedBot" in entrants and entrants["RatedBot"]["games"] == 1
    print(f"\nRATED_LANE: {receipt['rating']} vs {receipt.get('winner')!r}; ladder={entrants}")


def test_quota_fail_closed(arena):
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="QuotaBot")
    # battle quota default 5/day — 6th rated begin is refused at start+begin.
    # Play each to the end so begins don't pile up against the sidecar's live-
    # battle capacity (the quota axis is independent of battle lifecycle).
    for _ in range(5):
        state = _begin_battle(client, gateway, token, agent_key, lane="rated")
        _play_to_end(client, token, state)
    start = client.post("/battle/start", json={"token": token}).json()
    sig = agent_key.sign(start["pop_challenge"].encode()).hex()
    r = client.post(
        "/battle/begin",
        json={
            "token": token,
            "battle_nonce": start["battle_nonce"],
            "pop_signature_hex": sig,
            "lane": "rated",
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"].startswith("arena error (ref:")
    print("\nQUOTA: 6th rated battle refused fail-closed")


def test_turn_budget_forfeits_stale_battle(arena):
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="SlowBot")
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    gateway.now = lambda: time.time() + 1_000  # jump past the 120s budget
    resp = client.post(
        f"/battle/{state['battle_id']}/choose", json={"token": token, "choice_index": 1}
    )
    body = resp.json()
    assert body["status"] == "ended"
    assert body["winner"].startswith("anchor-"), "stale battle forfeits to the opponent"
    print(f"\nTURN_BUDGET: stale battle forfeited to {body['winner']!r}")


def test_validate_on_begin_rejects_illegal_team(arena):
    """F3 / defense rank-1: a client-supplied team is validated against the pinned
    banlist server-side BEFORE it can enter a battle. A banlist-illegal team is
    refused at /battle/begin (422) and no battle session is created."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="DraftBot")
    start = client.post("/battle/start", json={"token": token}).json()
    sig = agent_key.sign(start["pop_challenge"].encode()).hex()
    r = client.post(
        "/battle/begin",
        json={
            "token": token,
            "battle_nonce": start["battle_nonce"],
            "pop_signature_hex": sig,
            "lane": "sandbox",
            "team": ILLEGAL_TEAM,
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"].startswith("arena error (ref:")
    assert gateway.sessions == {}, "an illegal team must not open a battle session"
    assert client.get("/ladder").json()["entrants"] == {}
    print("\nVALIDATE_ON_BEGIN: banned Koraidon team refused at /battle/begin; no session")


def test_battle_observability_foe_hp_and_recent_turns(arena):
    """G-01/G-02/G-10 (playtest): the per-turn response must carry the opponent's
    HP%% and a LIVE recent-turns trail (not frozen at battle start) — derived from
    the opponent's own request the gateway already parses; no sidecar change."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="ObsBot")
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    saw_foe_hp = state.get("foe_hp_pct") is not None
    trails = []
    calls = 0
    while state.get("status") == "your_move" and calls < 200:
        assert "foe_hp_pct" in state and "recent_turns" in state, sorted(state)
        if state.get("foe_hp_pct") is not None:
            saw_foe_hp = True
        trails.append(tuple(state["recent_turns"]))
        resp = client.post(
            f"/battle/{state['battle_id']}/choose", json={"token": token, "choice_index": 1}
        )
        assert resp.status_code == 200, resp.text
        nxt = resp.json()
        nxt.setdefault("battle_id", state["battle_id"])
        state = nxt
        calls += 1
    assert state.get("status") == "ended"
    assert saw_foe_hp, "foe HP%% never surfaced across a whole battle (G-01)"
    assert len(set(trails)) > 1, "recent_turns frozen all game (G-10)"
    assert any("you →" in line for t in trails for line in t), "own choices missing from trail"
    assert any("foe " in line for t in trails for line in t), "foe observations missing from trail"
    assert state.get("recent_turns"), "receipt must carry the closing trail"
    print(
        f"\nOBSERVABILITY: foe HP surfaced, {len(set(trails))} distinct trails over "
        f"{calls} turns; closing trail: {state['recent_turns'][-3:]}"
    )


def test_team_draft_authoring_loop(arena):
    """#2: stateless pack+validate — illegal export gets per-slot repair errors;
    a legal draft round-trips into /battle/begin."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="DraftLoop")
    bad_export = (
        "Koraidon @ Leftovers\nAbility: Orichalcum Pulse\nTera Type: Fire\n"
        "EVs: 252 Atk / 252 Spe\nJolly Nature\n- Flare Blitz\n- Collision Course\n"
        "- Drain Punch\n- Swords Dance\n"
    )
    r = client.post("/team/draft", json={"token": token, "export": bad_export})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is False and body["errors"], body
    assert any("Koraidon" in e for e in body["errors"])
    n_repair_errors = len(body["errors"])

    from adx_showdown.teams import starter_pack

    good_export = next(iter(starter_pack().values()))
    r = client.post("/team/draft", json={"token": token, "export": good_export})
    body = r.json()
    assert body["valid"] is True and body["packed"]
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox", team=body["packed"])
    assert state["status"] in ("your_move", "ended")
    # no token -> refused; nothing drafted anonymously
    r = client.post("/team/draft", json={"token": "x.y", "export": good_export})
    assert r.status_code == 403
    print(
        f"\nTEAM_DRAFT: illegal export -> {n_repair_errors} repair errors; "
        "legal draft entered battle; anonymous draft refused"
    )


def test_sandbox_mirror_broken_and_disclosed(arena):
    """#3: the sandbox gym leader fields a FIXED, DISCLOSED signature team distinct
    from the visitor's — team choice finally matters (mirror is dead)."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="ScoutBot")

    from adx_showdown.teams import starter_pack

    default_export = next(iter(starter_pack().values()))
    packed0 = client.post("/team/draft", json={"token": token, "export": default_export}).json()[
        "packed"
    ]

    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    assert state.get("opponent_team_name") in starter_pack(), state.get("opponent_team_name")
    assert state.get("opponent_team"), "sandbox must disclose the gym signature team"
    assert state["opponent_team"] != packed0, "gym team must NOT mirror the visitor default"

    receipt, _ = _play_to_end(client, token, state)
    replay = client.get(receipt["replay"]).json()
    player_lines = [ln for ln in replay["input_log"] if ln.startswith(">player")]
    assert len(player_lines) == 2 and player_lines[0] != player_lines[1]
    # rated still mirrors (until #8's i.i.d. anchor-team defense lands)
    rated = _begin_battle(client, gateway, token, agent_key, lane="rated")
    assert "opponent_team" not in rated, "rated must not pre-disclose any team info"
    _play_to_end(client, token, rated)
    print(
        f"\nMIRROR_BROKEN: gym fields '{state['opponent_team_name']}' (disclosed), "
        "visitor default differs; rated undisclosed"
    )


def test_recent_turns_contain_move_names(arena):
    """All 3 round-2 playtest agents independently requested move names in
    recent_turns. Verify: at least one trail line contains a Pokémon move name
    (not just 'move 1') and that the events log carries choice_label."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="MoveNameBot")
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    # collect all turn lines over a few real turns
    all_trails: list[str] = []
    calls = 0
    while state.get("status") == "your_move" and calls < 30:
        for line in state.get("recent_turns", []):
            all_trails.append(line)
        resp = client.post(
            f"/battle/{state['battle_id']}/choose",
            json={"token": token, "choice_index": 1},
        )
        assert resp.status_code == 200
        nxt = resp.json()
        nxt.setdefault("battle_id", state["battle_id"])
        state = nxt
        calls += 1

    # at least some lines should have a real move name (not just "move N")
    # team preview lines look like "team preview N" — also fine, not "move N"
    move_num_only = [
        ln for ln in all_trails if ln.endswith(("→ move 1", "→ move 2", "→ move 3", "→ move 4"))
    ]
    move_named = [ln for ln in all_trails if "you →" in ln and ln not in move_num_only]
    assert move_named or all_trails, "no choice lines in trail at all"
    # if we got past team preview, at least one line must be a named move
    post_preview = [ln for ln in all_trails if "you →" in ln and "preview" not in ln.lower()]
    if post_preview:
        assert any(
            ln not in [f"T{i}: you → move {j}" for i in range(400) for j in range(1, 5)]
            for ln in post_preview
        ), f"all choice lines are raw 'move N': {post_preview[:3]}"

    # events log carries choice_label field
    evts = client.post("/my/events", json={"token": token, "since_seq": -1}).json()["events"]
    battle_evts = [e for e in evts if e.get("type") == "battle"]
    if battle_evts:
        assert any("choice_label" in (e.get("payload") or {}) for e in battle_evts), (
            "battle events must carry choice_label"
        )

    print(f"\nMOVE_NAMES: {len(move_named)}/{len(post_preview)} named; sample: {post_preview[:3]}")


def test_fork_sandbox_branches_rated_refused(arena):
    """#6 remix-the-loss: sandbox forks replay the recorded prefix on the same
    seed and branch; full-replay forks reproduce the original outcome; rated and
    foreign battles are refused."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="ForkBot")
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    receipt, _ = _play_to_end(client, token, state)
    src = receipt["battle_id"]

    # full replay (turn beyond the end) must reproduce the original outcome
    r = client.post(f"/battle/{src}/fork", json={"token": token, "turn": 1000})
    assert r.status_code == 200, r.text
    full = r.json()
    if full.get("status") == "your_move":
        full, _ = _play_to_end(client, token, full)
    assert full["winner"] == receipt["winner"], "same-choice fork must reproduce the outcome"
    assert full.get("parent_battle_id") == src and full.get("fork_turn") == 1000

    # branch mid-battle: control returns to the agent at/before the fork turn
    r = client.post(f"/battle/{src}/fork", json={"token": token, "turn": 2})
    assert r.status_code == 200, r.text
    branch = r.json()
    assert branch["battle_id"].startswith("sandbox-fork-")
    assert branch["parent_battle_id"] == src and branch["fork_turn"] == 2
    if branch.get("status") == "your_move":
        branch, _ = _play_to_end(client, token, branch)
    assert branch["status"] == "ended" and "rating" not in branch

    # rated battles can never be forked (rating-laundering firewall)
    rated = _begin_battle(client, gateway, token, agent_key, lane="rated")
    rated_receipt, _ = _play_to_end(client, token, rated)
    r = client.post(f"/battle/{rated_receipt['battle_id']}/fork", json={"token": token, "turn": 1})
    assert r.status_code == 403

    # a stranger cannot fork your battle
    stranger_key = Ed25519PrivateKey.generate()
    stranger = _enroll(client, owner_inbox, stranger_key, owner="other@example.com", name="Sneak")
    r = client.post(f"/battle/{src}/fork", json={"token": stranger, "turn": 1})
    assert r.status_code == 403
    assert client.get("/ladder").json()["entrants"].get("ForkBot", {}).get("games", 1) == 1
    print(
        f"\nFORK: full-replay reproduced winner={full['winner']!r}; branch@2 ended; "
        "rated + foreign forks refused"
    )


def test_my_events_pull_into_local_sqlite(arena, tmp_path):
    """P4: /my/events is tenant-scoped; local_log materializes ~/.adx-style SQLite
    idempotently and rebuilds the battle story offline."""
    from agentdex_arena import local_log

    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="LocalBot")
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    receipt, _ = _play_to_end(client, token, state)

    r = client.post("/my/events", json={"token": token, "since_seq": -1})
    assert r.status_code == 200
    events = r.json()["events"]
    assert events and all(
        (e.get("payload") or {}).get("battle_id", "").startswith(("sandbox-",)) for e in events
    )
    db = tmp_path / "arena.sqlite"
    assert local_log.store_events(events, db) == len(events)
    assert local_log.store_events(events, db) == 0, "re-pull must be a no-op (idempotent)"
    assert local_log.max_seq(db) == events[-1]["seq"]
    rows = local_log.battles(db)
    assert any(b["battle_id"] == receipt["battle_id"] for b in rows)
    story = local_log.recent_story(receipt["battle_id"], db)
    assert story and all(line.startswith("T") for line in story)

    # tenant scoping: a second agent sees none of LocalBot's battles
    other_key = Ed25519PrivateKey.generate()
    other = _enroll(client, owner_inbox, other_key, owner="other2@example.com", name="OtherBot")
    r2 = client.post("/my/events", json={"token": other, "since_seq": -1})
    assert r2.json()["events"] == []
    print(
        f"\nLOCAL_LOG: {len(events)} events pulled tenant-scoped; idempotent; "
        f"story[0..2]={story[:2]}; stranger sees 0"
    )


def test_enroll_rejects_placeholder_owner(arena):
    """G-04 (playtest): the owner is the human contact the out-of-band code reaches —
    a template placeholder or non-address is rejected with a self-describing 422,
    never silently enrolled (which taught a playtest agent the wrong lesson)."""
    client, gateway, owner_inbox, agent_key = arena
    pub = agent_key.public_key().public_bytes_raw().hex()
    for bad in ("{OWNER}", "owner", "no-at-sign", "has space@x.com", "trailing@dotless"):
        r = client.post(
            "/enroll/request", json={"owner": bad, "agent_name": "X", "agent_pubkey_hex": pub}
        )
        assert r.status_code == 422, (bad, r.status_code)
    r = client.post(
        "/enroll/request",
        json={"owner": "real@example.com", "agent_name": "X", "agent_pubkey_hex": pub},
    )
    assert r.status_code == 200
    print("\nOWNER_VALIDATION: placeholder/non-contact owners rejected; real contact accepted")


def test_capacity_returns_retryable_503(tmp_path: Path):
    """G-03 (playtest): when the shared sim is at its live-battle cap, /battle/begin
    returns a clear RETRYABLE 503 — not an opaque 400 the agent reads as its own
    fault and blind-retries."""
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    authority = ConsentAuthority(signing_key_hex=signing)
    inbox: dict[str, str] = {}
    gateway = ArenaGateway(
        authority=authority,
        events_path=tmp_path / "e.jsonl",
        artifacts_dir=tmp_path / "a",
        notify_owner=lambda owner, code: inbox.__setitem__(owner, code),
    )
    app = create_app(gateway, sidecar_factory=lambda: Sidecar(max_battles=1))
    agent_key = Ed25519PrivateKey.generate()
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _enroll(client, inbox, agent_key, name="CapBot")
        s1 = _begin_battle(client, gateway, token, agent_key, lane="sandbox")  # holds the 1 slot
        assert s1["status"] == "your_move"
        start = client.post("/battle/start", json={"token": token}).json()
        sig = agent_key.sign(start["pop_challenge"].encode()).hex()
        r = client.post(
            "/battle/begin",
            json={
                "token": token,
                "battle_nonce": start["battle_nonce"],
                "pop_signature_hex": sig,
                "lane": "sandbox",
            },
        )
        assert r.status_code == 503, r.text
        assert "capacity" in r.json()["detail"].lower()
        print("\nCAPACITY: at-capacity begin returns retryable 503, not opaque 400")


def test_injection_corpus_gate(arena):
    """A6 launch-blocking gate: every payload through every writable field."""
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="ProbeBot")
    pub = agent_key.public_key().public_bytes_raw().hex()
    blocked = 0
    for payload in CORPUS:
        value = _payload_value(payload)
        # 1) enrollment agent_name field
        r = client.post(
            "/enroll/request",
            json={"owner": "x@example.com", "agent_name": value[:64], "agent_pubkey_hex": pub},
        )
        assert r.status_code in (200, 400, 422), (payload["id"], r.status_code)
        # 2) consent token position
        r = client.post("/battle/start", json={"token": value[:2000]})
        assert r.status_code == 403, payload["id"]
        assert r.json()["detail"].startswith("arena error (ref:"), payload["id"]
        # 3) evolution reasoning field — payload must NOT reflect raw
        r = client.post("/evolution/request", json={"token": token, "reasoning": value[:500]})
        if r.status_code == 200:
            echoed = r.json()["reasoning_echo"]
            for ch in ("<", ">", "|", "{", "}", "\x1b", "/"):
                assert ch not in echoed, (payload["id"], ch)
        else:
            assert r.json()["detail"].startswith("arena error (ref:")
        # 4) battle id path position — a payload the HTTP client itself refuses
        #    to place in the request line (bare control chars) never reaches the
        #    server; that client-side rejection is itself neutralization.
        try:
            r = client.post(
                f"/battle/{value[:40]}/choose", json={"token": token, "choice_index": 1}
            )
        except httpx.InvalidURL:
            blocked += 1
            continue
        assert r.status_code in (404, 422), payload["id"]
        if r.status_code == 404:
            detail = r.json()["detail"]
            # either the gateway's opaque "no session" 404, or FastAPI's
            # route-mismatch 404 when the payload injects a path separator —
            # both mean the payload never reached the battle handler.
            assert detail.startswith("arena error (ref:") or detail == "Not Found", payload["id"]
        blocked += 1
    # no payload minted a token, started a battle, or got itself rated
    assert client.get("/ladder").json()["entrants"] == {}
    print(f"\nINJECTION_GATE: {blocked}/{len(CORPUS)} payloads neutralized across 4 surfaces")


def test_consent_unit_rails():
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    agent = Ed25519PrivateKey.generate()
    auth = ConsentAuthority(signing_key_hex=signing, now=lambda: 1000.0)
    claims = ConsentClaims(
        token_id="t" * 8,
        owner="o@example.com",
        agent_name="Bot",
        agent_pubkey_hex=agent.public_key().public_bytes_raw().hex(),
        scopes=["battle"],
        issued_at=1000.0,
        expires_at=2000.0,
        confirmed_via="test",
    )
    token = auth.mint(claims)
    assert auth.verify(token, scope="battle").token_id == claims.token_id
    with pytest.raises(ConsentError, match="scope"):
        auth.verify(token, scope="evolve")
    with pytest.raises(ConsentError, match="signature"):
        auth.verify(token[:-4] + "AAAA", scope="battle")
    auth.revoke(claims.token_id)
    with pytest.raises(ConsentError, match="revoked"):
        auth.verify(token, scope="battle")
    # PoP: the agent's own key verifies; a stranger's key fails
    auth2 = ConsentAuthority(signing_key_hex=signing, now=lambda: 1000.0)
    sig = agent.sign(ConsentAuthority.pop_challenge("nonce1", claims.token_id)).hex()
    auth2.verify_pop(claims, "nonce1", sig)
    mallory = Ed25519PrivateKey.generate()
    bad = mallory.sign(ConsentAuthority.pop_challenge("nonce1", claims.token_id)).hex()
    with pytest.raises(ConsentError, match="possession"):
        auth2.verify_pop(claims, "nonce1", bad)


def test_enroll_rejects_reserved_and_duplicate_names(arena):
    client, gateway, owner_inbox, agent_key = arena
    pub = agent_key.public_key().public_bytes_raw().hex()

    # 1. Reject reserved names starting with "anchor-" or equal to visitor/foe/_house/_ladder
    for bad_name in ("anchor-bot", "visitor", "foe", "_house", "_ladder"):
        r = client.post(
            "/enroll/request",
            json={"owner": "real@example.com", "agent_name": bad_name, "agent_pubkey_hex": pub},
        )
        assert r.status_code == 400

    # 2. Reject duplicate names
    # First, register "LoneAgent" successfully
    token = _enroll(client, owner_inbox, agent_key, owner="owner@example.com", name="LoneAgent")
    assert token is not None

    # Simulate registration in self._registered (normally done via event log replay or battle finish)
    gateway._registered.add("LoneAgent")

    # Try to enroll "LoneAgent" again (duplicate, should be rejected)
    r = client.post(
        "/enroll/request",
        json={"owner": "real@example.com", "agent_name": "LoneAgent", "agent_pubkey_hex": pub},
    )
    assert r.status_code == 409


def test_rated_turn_budget_forfeits_on_ladder(arena):
    from agentdex_engine.modules.arena.events import recompute_ladder

    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="StaleBot")
    state = _begin_battle(client, gateway, token, agent_key, lane="rated")

    # Now jump past the 120s budget
    gateway.now = lambda: time.time() + 1_000

    resp = client.post(
        f"/battle/{state['battle_id']}/choose", json={"token": token, "choice_index": 1}
    )
    body = resp.json()
    assert body["status"] == "ended"
    assert body["forfeit"] == "turn budget exceeded"

    # Now check if the event log has been updated with "register" and "period" for StaleBot
    events = list(gateway.events.iter_events())
    types = [e["type"] for e in events]
    assert "battle_end" in types
    assert "register" in types
    assert "period" in types

    # Recompute the ladder and check if StaleBot is registered
    ladder = recompute_ladder(gateway.events.path)
    assert "StaleBot" in ladder.entrants
    print("\nTURN_BUDGET_RATED: rated stale battle forfeited and rated on ladder")


def test_choose_step_failure_safety(arena):
    from adx_showdown.sidecar import SidecarError

    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="SafetyBot")
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    battle_id = state["battle_id"]

    session = gateway.sessions[battle_id]

    choices_len_before = len(session.visitor_choices)
    events_len_before = len(list(gateway.events.iter_events()))

    original_request = session.sidecar.request

    async def mock_request_fail(method, **kwargs):
        if method == "step":
            raise SidecarError("mock step failure")
        return await original_request(method, **kwargs)

    session.sidecar.request = mock_request_fail

    resp = client.post(f"/battle/{battle_id}/choose", json={"token": token, "choice_index": 1})
    assert resp.status_code == 400

    session.sidecar.request = original_request

    assert len(session.visitor_choices) == choices_len_before
    assert len(list(gateway.events.iter_events())) == events_len_before


@pytest.mark.timeout(90)
def test_collusion_forensics_quarantine(arena):
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="CollusionBot")

    # 1. Test early forfeit collusion (turns < 3)
    # Start a rated battle and end it immediately by forcing a timeout or early exit.
    state = _begin_battle(client, gateway, token, agent_key, lane="rated")

    # Simulate a turn budget exceed / early forfeit
    gateway.now = lambda: time.time() + 1000
    resp = client.post(
        f"/battle/{state['battle_id']}/choose", json={"token": token, "choice_index": 1}
    )
    assert resp.status_code == 200
    receipt = resp.json()
    assert receipt["status"] == "ended"
    assert receipt.get("quarantined") is True
    assert "early forfeit" in receipt.get("quarantine_reason", "")

    # Ensure quarantine event is written
    events = list(gateway.events.iter_events())
    assert any(
        e.get("type") == "quarantine"
        and e.get("payload", {}).get("battle_id") == state["battle_id"]
        for e in events
    )


@pytest.mark.timeout(90)
def test_dispute_endpoint_success(arena):
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="DisputeBot")

    # Start and play a sandbox battle to completion
    state = _begin_battle(client, gateway, token, agent_key, lane="sandbox")
    receipt, _ = _play_to_end(client, token, state)
    battle_id = receipt["battle_id"]

    # Dispute with correct winner (should be rejected since it matches)
    r = client.post(f"/battle/{battle_id}/dispute", json={"token": token})
    assert r.status_code == 200
    res = r.json()
    assert res["disputed"] is False
    assert res["match"] is True

    # Falsify the winner in replays memory to trigger a mismatch
    gateway.replays[battle_id]["winner"] = "FalsifiedWinner"

    # Dispute again (now should succeed because of winner mismatch)
    r2 = client.post(f"/battle/{battle_id}/dispute", json={"token": token})
    assert r2.status_code == 200
    res2 = r2.json()
    assert res2["disputed"] is True
    assert res2["match"] is False
    assert "dispute successful" in res2["detail"]

    # Verify quarantine event was written
    events = list(gateway.events.iter_events())
    assert any(
        e.get("type") == "quarantine"
        and e.get("payload", {}).get("battle_id") == battle_id
        and "dispute successful" in e.get("payload", {}).get("reason", "")
        for e in events
    )


@pytest.mark.timeout(90)
def test_nightly_self_test_halts_publication(arena, monkeypatch, tmp_path):
    client, gateway, owner_inbox, agent_key = arena
    token = _enroll(client, owner_inbox, agent_key, name="HaltBot")

    # Set ARENA_SELFTEST_DIR to our tmp_path using monkeypatch
    monkeypatch.setenv("ARENA_SELFTEST_DIR", str(tmp_path / "selftest"))

    # Default should be publication allowed (True) since no report file exists yet
    assert gateway.publication_allowed is True

    # 1. Create a failing report
    selftest_dir = tmp_path / "selftest"
    selftest_dir.mkdir(parents=True, exist_ok=True)
    report_file = selftest_dir / "20260613T010000Z.report.json"
    report_file.write_text(json.dumps({"publication_allowed": False}))

    # Verify gateway publication_allowed is now False
    assert gateway.publication_allowed is False

    # Try to start a rated battle -> should fail with 403 (rated lane paused: instrument self-test red)
    start = client.post("/battle/start", json={"token": token}).json()
    sig = agent_key.sign(start["pop_challenge"].encode()).hex()
    r = client.post(
        "/battle/begin",
        json={
            "token": token,
            "battle_nonce": start["battle_nonce"],
            "pop_signature_hex": sig,
            "lane": "rated",
        },
    )
    assert r.status_code == 403
    assert "arena error (ref: " in r.json()["detail"]

    # 2. Write a passing report
    report_file.write_text(json.dumps({"publication_allowed": True}))
    assert gateway.publication_allowed is True

    # Rated battle begin should now succeed (needs a fresh nonce since the first was consumed/popped)
    start2 = client.post("/battle/start", json={"token": token}).json()
    sig2 = agent_key.sign(start2["pop_challenge"].encode()).hex()
    r2 = client.post(
        "/battle/begin",
        json={
            "token": token,
            "battle_nonce": start2["battle_nonce"],
            "pop_signature_hex": sig2,
            "lane": "rated",
        },
    )
    assert r2.status_code == 200
