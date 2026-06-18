"""Tests for `adx arena play` — render helpers + the interactive loop with a fake
ArenaClient (no network, no TTY)."""

from __future__ import annotations

import pytest
from agentdex_cli import arena_tui
from rich.console import Console


def _rec() -> Console:
    # record=True captures output; no_color keeps assertions substring-stable.
    return Console(record=True, width=100, no_color=True)


def test_hp_bar_thresholds_and_clamp() -> None:
    assert "100%" in arena_tui._hp_bar(100)
    assert "green" in arena_tui._hp_bar(80)
    assert "yellow" in arena_tui._hp_bar(40)
    assert "red" in arena_tui._hp_bar(10)
    # clamp out-of-range and handle None
    assert "100%" in arena_tui._hp_bar(250)
    assert "  0%" in arena_tui._hp_bar(-5)
    assert "HP" in arena_tui._hp_bar(None)


def test_render_turn_shows_board_foe_and_log() -> None:
    console = _rec()
    state = {
        "battle_id": "sandbox-abc123",
        "lane": "sandbox",
        "turn": 3,
        "n_choices": 4,
        "foe_active": "Garchomp",
        "foe_hp_pct": 62,
        "recent_turns": ["Pikachu used Thunderbolt", "Garchomp lost 30% HP"],
        "state": "Your active: Pikachu\n1. Thunderbolt  2. Quick Attack  3. switch  4. switch",
    }
    arena_tui._render_turn(console, state)
    out = console.export_text()
    assert "Garchomp" in out
    assert "62%" in out
    assert "Thunderbolt" in out
    assert "sandbox-abc123" in out
    assert "turn 3" in out


def test_render_receipt_win_with_rating_and_replay() -> None:
    console = _rec()
    receipt = {
        "status": "ended",
        "winner": "MyBot",
        "you_won": True,
        "turns": 17,
        "rating": {"rating": 1532.4, "rd": 88.1, "published_delta": 12.3},
        "replay": "/replay/rated-xyz",
        "badge_awarded": None,
    }
    arena_tui._render_receipt(console, receipt)
    out = console.export_text()
    assert "you won" in out
    assert "MyBot" in out
    assert "+12.3" in out
    assert "/replay/rated-xyz" in out


def test_render_receipt_loss() -> None:
    console = _rec()
    arena_tui._render_receipt(console, {"winner": "Foe", "you_won": False, "turns": 9})
    assert "you lost" in console.export_text()


class _FakeIdentity:
    name = "terminal-player"


class _FakeClient:
    """Drives one your_move turn then an ended receipt."""

    base = "https://example.test"

    def __init__(self, *a, **k) -> None:
        self.chose: list[int] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def battle_begin(self, *a, **k):
        return {
            "battle_id": "sandbox-loop",
            "lane": "sandbox",
            "status": "your_move",
            "turn": 1,
            "n_choices": 3,
            "foe_active": "Onix",
            "foe_hp_pct": 100,
            "recent_turns": [],
            "state": "1. Tackle  2. Growl  3. switch",
        }

    def battle_choose(self, token, battle_id, idx):
        self.chose.append(idx)
        return {"status": "ended", "winner": "terminal-player", "you_won": True, "turns": 1}


def test_play_loop_drives_begin_choose_end(monkeypatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(arena_tui, "ArenaClient", lambda *a, **k: fake)
    monkeypatch.setattr(
        arena_tui, "_resolve_token", lambda client, args, console: ("tok", _FakeIdentity())
    )
    monkeypatch.setattr(arena_tui, "_prompt_choice", lambda console, n: 2)

    rc = arena_tui.cmd_arena_play(["--token", "tok", "--agent", "terminal-player"])
    assert rc == 0
    assert fake.chose == [2]  # the human's choice was forwarded


def test_play_loop_quit_forfeits(monkeypatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(arena_tui, "ArenaClient", lambda *a, **k: fake)
    monkeypatch.setattr(
        arena_tui, "_resolve_token", lambda client, args, console: ("tok", _FakeIdentity())
    )
    monkeypatch.setattr(arena_tui, "_prompt_choice", lambda console, n: None)  # quit

    rc = arena_tui.cmd_arena_play(["--token", "tok"])
    assert rc == 0
    assert fake.chose == []  # quit before choosing


def test_play_requires_token_or_owner(monkeypatch) -> None:
    # No token, no owner -> a clean SystemExit, not a traceback.
    monkeypatch.delenv("ADX_ARENA_TOKEN", raising=False)
    monkeypatch.setattr(arena_tui, "ArenaClient", lambda *a, **k: _FakeClient())
    with pytest.raises(SystemExit):
        arena_tui.cmd_arena_play(["--agent", "nobody"])
