"""UI-5 + UI-6 gateway integration tests: SSE frame schema includes scene + trace_lines.

UI-5 probe: every SSE data frame carries a 'scene' key with non-empty hpFrac per side.
UI-6 probe: frames containing |-reasoning| lines expose trace_lines in the SSE payload.
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

# Omniscient frames that cover the key signal lines for both UI-5 and UI-6.
_FRAMES_BASIC = [
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
            "|-damage|p2a: Rotom|88/250",
            "|-damage|p2a: Rotom|35/100",
            "|split|p1",
            "|-damage|p1a: Garchomp|176/298",
            "|-damage|p1a: Garchomp|60/100",
        ],
    },
]

_FRAMES_WITH_REASONING = [
    {
        "seq": 1,
        "turn": 0,
        "raw_lines": ["|player|p1|Alpha||", "|player|p2|Bravo||", "|start"],
    },
    {
        "seq": 2,
        "turn": 1,
        "raw_lines": [
            "|-reasoning|p1|Earthquake hits both — max damage output",
            "|say|p2|secret counter-plan",
            "|move|p1a: Garchomp|Earthquake|p2a: Rotom",
            "|-damage|p2a: Rotom|35/100",
        ],
    },
]


def _gateway(tmp_path: Path) -> ArenaGateway:
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


def _seed(gw: ArenaGateway, frames: list[dict], *, battle_id: str = "b_ui56") -> str:
    gw.accounts.add_agent(_OWNER, "oppie")
    sess = BattleSession(
        battle_id=battle_id,
        claims_token_id="tok",
        visitor_name="oppie",
        lane="sandbox",
        opponent="anchor",
        seed=[1],
        sidecar=None,
        opponent_policy=None,
    )
    sess.visitor_side = "p1"
    sess.frames = [dict(f) for f in frames]
    sess.frame_seq = len(frames)
    sess.ended = {"status": "ended"}
    gw.sessions[sess.battle_id] = sess
    return sess.battle_id


def _auth(gw: ArenaGateway) -> dict[str, str]:
    token = gw.session_auth.mint_session(_OWNER, "github:eddie")
    return {"Authorization": f"Bearer {token}"}


def _parse_sse(text: str) -> tuple[list[dict], bool]:
    frames: list[dict] = []
    saw_end = False
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("event: end"):
            saw_end = True
            continue
        for line in block.splitlines():
            if line.startswith("data: "):
                frames.append(json.loads(line[6:]))
    return frames, saw_end


# ── UI-5: scene snapshot ──────────────────────────────────────────────────────


def test_sse_frame_has_scene_key(tmp_path: Path):
    gw = _gateway(tmp_path)
    bid = _seed(gw, _FRAMES_BASIC)
    client = TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)
    r = client.get(f"/battle/{bid}/live")
    frames, _ = _parse_sse(r.text)
    assert frames, "expected at least one SSE data frame"
    for fr in frames:
        assert "scene" in fr, f"frame {fr.get('seq')} missing 'scene'"


def test_sse_scene_has_p1_p2_weather(tmp_path: Path):
    gw = _gateway(tmp_path)
    bid = _seed(gw, _FRAMES_BASIC)
    client = TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)
    r = client.get(f"/battle/{bid}/live")
    frames, _ = _parse_sse(r.text)
    last = frames[-1]["scene"]
    assert "p1" in last and "p2" in last
    assert "players" in last
    assert "field" in last
    assert "turn" in last
    assert "winner" in last
    assert "weather" in last


def test_sse_scene_hpfrac_per_mon_non_empty(tmp_path: Path):
    """After a |-damage| turn the scene carries sub-1.0 hpFrac — the key probe assertion."""
    gw = _gateway(tmp_path)
    bid = _seed(gw, _FRAMES_BASIC)
    client = TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)
    r = client.get(f"/battle/{bid}/live")
    frames, _ = _parse_sse(r.text)
    # The final frame (after the damage turn) must show reduced HP on both sides.
    last_scene = frames[-1]["scene"]
    assert last_scene["p1"]["hpFrac"] < 1.0, "p1 hpFrac should drop after |-damage|"
    assert last_scene["p2"]["hpFrac"] < 1.0, "p2 hpFrac should drop after |-damage|"


def test_sse_scene_player_names_populated(tmp_path: Path):
    gw = _gateway(tmp_path)
    bid = _seed(gw, _FRAMES_BASIC)
    client = TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)
    r = client.get(f"/battle/{bid}/live")
    frames, _ = _parse_sse(r.text)
    # After frame 1 (the |player| preamble) player labels should be set.
    scene_after_preamble = frames[0]["scene"]
    assert scene_after_preamble["players"]["p1"] == "Alpha"
    assert scene_after_preamble["players"]["p2"] == "Bravo"


def test_sse_scene_accumulates_across_frames(tmp_path: Path):
    """Scene state is cumulative — later frames carry all history, not just the delta."""
    gw = _gateway(tmp_path)
    bid = _seed(gw, _FRAMES_BASIC)
    client = TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)
    r = client.get(f"/battle/{bid}/live")
    frames, _ = _parse_sse(r.text)
    # Even the second frame (damage) retains the player labels set in the first frame.
    assert len(frames) >= 2
    assert frames[1]["scene"]["players"]["p1"] == "Alpha"


# ── UI-6: reasoning trace ─────────────────────────────────────────────────────


def test_sse_frame_has_trace_lines_key(tmp_path: Path):
    gw = _gateway(tmp_path)
    bid = _seed(gw, _FRAMES_BASIC, battle_id="b_trace_key")
    client = TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)
    r = client.get(f"/battle/{bid}/live")
    frames, _ = _parse_sse(r.text)
    for fr in frames:
        assert "trace_lines" in fr, f"frame {fr.get('seq')} missing 'trace_lines'"


def test_sse_trace_lines_empty_when_no_reasoning(tmp_path: Path):
    gw = _gateway(tmp_path)
    bid = _seed(gw, _FRAMES_BASIC, battle_id="b_trace_empty")
    client = TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)
    r = client.get(f"/battle/{bid}/live")
    frames, _ = _parse_sse(r.text)
    for fr in frames:
        assert fr["trace_lines"] == [], f"expected empty trace_lines, got {fr['trace_lines']}"


def test_sse_trace_lines_populated_on_reasoning_frame(tmp_path: Path):
    """UI-6 probe: trace_lines > 0 for a frame that carries |-reasoning| lines."""
    gw = _gateway(tmp_path)
    bid = _seed(gw, _FRAMES_WITH_REASONING, battle_id="b_trace_pop")
    client = TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)
    r = client.get(f"/me/battle/{bid}/live", headers=_auth(gw))
    frames, _ = _parse_sse(r.text)
    reasoning_frames = [fr for fr in frames if fr["trace_lines"]]
    assert reasoning_frames, "expected at least one frame with trace_lines populated"
    entry = reasoning_frames[0]["trace_lines"][0]
    assert entry["side"] == "p1"
    assert "Earthquake" in entry["text"]


def test_sse_trace_lines_redacted_for_public_spectator(tmp_path: Path):
    gw = _gateway(tmp_path)
    bid = _seed(gw, _FRAMES_WITH_REASONING, battle_id="b_trace_public_redacted")
    client = TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)
    r = client.get(f"/battle/{bid}/live")
    frames, _ = _parse_sse(r.text)
    assert frames
    assert all(fr["side"] == "spectator" for fr in frames)
    assert all(fr["trace_lines"] == [] for fr in frames)
    public_lines = [line for fr in frames for line in fr["lines"]]
    assert not any(line.startswith("|-reasoning|") for line in public_lines)
    assert not any(line.startswith("|say|") for line in public_lines)
    assert "max damage output" not in "\n".join(public_lines)
    assert "secret counter-plan" not in "\n".join(public_lines)


def test_sse_trace_lines_have_side_and_text_keys(tmp_path: Path):
    gw = _gateway(tmp_path)
    bid = _seed(gw, _FRAMES_WITH_REASONING, battle_id="b_trace_schema")
    client = TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)
    r = client.get(f"/me/battle/{bid}/live", headers=_auth(gw))
    frames, _ = _parse_sse(r.text)
    for fr in frames:
        for entry in fr["trace_lines"]:
            assert "side" in entry and "text" in entry
