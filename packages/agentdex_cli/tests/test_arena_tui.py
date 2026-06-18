"""Tests for `adx arena play` — render helpers + the interactive loop with a fake
ArenaClient (no network, no TTY)."""

from __future__ import annotations

import pytest
from agentdex_cli import arena_tui
from rich.console import Console


def _rec() -> Console:
    # record=True captures output; no_color keeps assertions substring-stable.
    return Console(record=True, width=100, no_color=True)


class _TTY:
    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _interactive_stdin(monkeypatch):
    # cmd_arena_play now fails fast if stdin is not a TTY; pytest's stdin is not,
    # so present an interactive stdin for the play-loop tests (render-only tests
    # are unaffected).
    monkeypatch.setattr("sys.stdin", _TTY())


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
    arena_tui._render_receipt(console, receipt, "https://arena.example")
    out = console.export_text()
    assert "you won" in out
    assert "MyBot" in out
    assert "+12.3" in out
    assert "https://arena.example/replay/rated-xyz" in out  # uses the passed base


def test_render_receipt_loss() -> None:
    console = _rec()
    arena_tui._render_receipt(console, {"winner": "Foe", "you_won": False, "turns": 9}, "https://x")
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


class _MultiTurnClient(_FakeClient):
    """Turn 1 choose returns another your_move that OMITS battle_id (the gateway
    need not echo it); turn 2 ends. Records the battle_id passed to each choose."""

    def __init__(self, *a, **k) -> None:
        super().__init__(*a, **k)
        self.chose_ids: list[str] = []
        self._n = 0

    def battle_choose(self, token, battle_id, idx):
        self.chose.append(idx)
        self.chose_ids.append(battle_id)
        self._n += 1
        if self._n == 1:
            # no "battle_id" key here on purpose
            return {"status": "your_move", "turn": 2, "n_choices": 2, "state": "1. a  2. b"}
        return {"status": "ended", "winner": "x", "you_won": True, "turns": 2}


def test_play_loop_preserves_battle_id_across_turns(monkeypatch) -> None:
    fake = _MultiTurnClient()
    monkeypatch.setattr(arena_tui, "ArenaClient", lambda *a, **k: fake)
    monkeypatch.setattr(
        arena_tui, "_resolve_token", lambda client, args, console: ("tok", _FakeIdentity())
    )
    monkeypatch.setattr(arena_tui, "_prompt_choice", lambda console, n: 1)

    rc = arena_tui.cmd_arena_play(["--token", "tok"])
    assert rc == 0
    # both choices routed to the begin battle_id even though turn-1's response omitted it
    assert fake.chose_ids == ["sandbox-loop", "sandbox-loop"]


class _PackingClient(_FakeClient):
    def __init__(self, *a, **k) -> None:
        super().__init__(*a, **k)
        self.drafted: list[str] = []
        self.began_team = "UNSET"

    def team_draft(self, token, export):
        self.drafted.append(export)
        return {"packed": "PACKED|gen9ou|...", "valid": True, "errors": []}

    def battle_begin(self, token, identity, *, team_packed=None, lane="sandbox", gym_leader=None):
        self.began_team = team_packed
        return super().battle_begin()


def test_play_packs_exported_team_before_begin(monkeypatch, tmp_path) -> None:
    export = tmp_path / "team.txt"
    export.write_text(
        "Pikachu @ Light Ball\nAbility: Static\n- Thunderbolt\n"
    )  # multi-line = export
    fake = _PackingClient()
    monkeypatch.setattr(arena_tui, "ArenaClient", lambda *a, **k: fake)
    monkeypatch.setattr(
        arena_tui, "_resolve_token", lambda client, args, console: ("tok", _FakeIdentity())
    )
    monkeypatch.setattr(arena_tui, "_prompt_choice", lambda console, n: 1)

    rc = arena_tui.cmd_arena_play(["--token", "tok", "--team", str(export)])
    assert rc == 0
    assert fake.drafted and fake.drafted[0].startswith("Pikachu")  # export was sent to /team/draft
    assert fake.began_team == "PACKED|gen9ou|..."  # begin received the PACKED form


def test_default_agent_name_survives_server_name_cap(monkeypatch) -> None:
    """PR #279/#285 review: the default agent name must fit the arena's 24-char
    server cap (MAX_NAME_LEN) so the CLI-side and server-side names match, and it
    must hash the FULL hostname so hosts sharing a prefix don't collide."""
    from adx_showdown.protocol import MAX_NAME_LEN, sanitize_name

    monkeypatch.setattr("socket.gethostname", lambda: "my-very-long-shared-prefix-host-1")
    name = arena_tui._default_agent_name()

    # Fits the cap -> the server stores exactly what the CLI saved (no truncation).
    assert len(name) <= MAX_NAME_LEN
    assert sanitize_name(name) == name
    assert name.startswith("tp-")

    # Stable across runs for the same host.
    assert arena_tui._default_agent_name() == name

    # Two hosts that share the first 8 chars (and so used to truncate to the same
    # server name) now get distinct names via the full-hostname hash.
    monkeypatch.setattr("socket.gethostname", lambda: "my-very-long-shared-prefix-host-2")
    other = arena_tui._default_agent_name()
    assert other != name
    assert len(other) <= MAX_NAME_LEN


def test_default_agent_name_wide_hash_avoids_known_collision(monkeypatch) -> None:
    """PR #285 review 3435385951: the earlier 32-bit hex suffix collided (the
    reviewer's example: host-155141 and host-168010 both hashed to 59aee908).
    The widened 60-bit hash must keep those two distinct."""
    monkeypatch.setattr("socket.gethostname", lambda: "host-155141")
    a = arena_tui._default_agent_name()
    monkeypatch.setattr("socket.gethostname", lambda: "host-168010")
    b = arena_tui._default_agent_name()
    assert a != b


def test_effective_agent_name_falls_back_to_legacy_creds(monkeypatch, tmp_path) -> None:
    """PR #285/#287 review: on the DEFAULT agent with no current-name creds,
    reuse a prior default name's creds — but ONLY for the implicit saved-token
    path and ONLY when the prior token is non-expired. An explicit --agent /
    --token / ADX_ARENA_TOKEN is never overridden (3435385944 + 3435479226)."""
    import types

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ADX_ARENA_TOKEN", raising=False)
    monkeypatch.setattr("socket.gethostname", lambda: "some-host")
    # Deterministic expiry; non-expired by default, flipped per case.
    monkeypatch.setattr(arena_tui, "token_expired", lambda tok, **k: False)
    cfg = tmp_path / ".agentdex"
    cfg.mkdir()

    new_default = arena_tui._default_agent_name()
    legacy = arena_tui._legacy_default_agent_names()[0]
    assert legacy != new_default
    args = types.SimpleNamespace(agent=new_default, token=None)

    # No creds anywhere -> stay on the current default.
    assert arena_tui._effective_agent_name(args) == new_default

    # Legacy token+key present AND non-expired -> fall back.
    (cfg / f"{legacy}.token").write_text("legacy-token")
    (cfg / f"{legacy}.key").write_text("legacy-key")
    assert arena_tui._effective_agent_name(args) == legacy

    # An explicit --token defines the current-name identity -> NO fallback (else
    # it would be paired with the legacy key it was not signed with).
    assert (
        arena_tui._effective_agent_name(types.SimpleNamespace(agent=new_default, token="tok"))
        == new_default
    )
    # Same for ADX_ARENA_TOKEN in the environment.
    monkeypatch.setenv("ADX_ARENA_TOKEN", "env-tok")
    assert arena_tui._effective_agent_name(args) == new_default
    monkeypatch.delenv("ADX_ARENA_TOKEN", raising=False)

    # An EXPIRED legacy token is unusable -> NO fallback (enroll fresh instead of
    # re-enrolling the permanently registered old name).
    monkeypatch.setattr(arena_tui, "token_expired", lambda tok, **k: True)
    assert arena_tui._effective_agent_name(args) == new_default
    monkeypatch.setattr(arena_tui, "token_expired", lambda tok, **k: False)

    # An explicit (non-default) --agent is never overridden.
    assert (
        arena_tui._effective_agent_name(types.SimpleNamespace(agent="MyExplicitBot", token=None))
        == "MyExplicitBot"
    )

    # Once the current default also has creds, prefer it over the legacy name.
    (cfg / f"{new_default}.token").write_text("new-token")
    assert arena_tui._effective_agent_name(args) == new_default


def test_legacy_default_agent_names_includes_original_bare_default(monkeypatch) -> None:
    """PR #287 review 3435479234: the very first CLI default was the literal
    `terminal-player` (no hostname/hash suffix); it must be a fallback candidate
    so users who enrolled in that release keep their credentials."""
    monkeypatch.setattr("socket.gethostname", lambda: "some-host")
    names = arena_tui._legacy_default_agent_names()
    assert "terminal-player" in names
    assert any(n.startswith("terminal-player-") for n in names)  # plus the suffixed forms


def test_default_arena_base_is_a_live_https_host(monkeypatch) -> None:
    """`adx arena play` with no --url must reach a LIVE arena. agentdex.builders
    is not wired yet (parked DNS, no TLS -> the default would time out), so the
    default is the live, skill.md-canonical host agentdex.ai-builders.space.
    Override precedence: explicit arg > ADX_ARENA_URL > ARENA_BASE > default."""
    from agentdex_cli.arena_client import DEFAULT_BASE, resolve_base

    monkeypatch.delenv("ADX_ARENA_URL", raising=False)
    monkeypatch.delenv("ARENA_BASE", raising=False)
    assert DEFAULT_BASE == "https://agentdex.ai-builders.space"
    assert resolve_base() == DEFAULT_BASE

    monkeypatch.setenv("ARENA_BASE", "https://env-arena-base")
    assert resolve_base() == "https://env-arena-base"
    monkeypatch.setenv("ADX_ARENA_URL", "https://adx-arena-url")
    assert resolve_base() == "https://adx-arena-url"  # ADX_ARENA_URL wins over ARENA_BASE
    assert resolve_base("https://explicit") == "https://explicit"  # explicit arg wins over all
