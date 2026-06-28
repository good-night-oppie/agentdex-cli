"""`adx arena play` — a watchable, human-playable terminal TUI for the agentdex
Pokémon Showdown arena.

Turn-based, so no real-time render loop is needed: each turn we paint the board
(the gateway's pre-rendered ``state`` blob + a foe HP bar + the recent-turn log),
read the human's 1-based choice, POST it, and repaint. Rich's Console honours
``NO_COLOR`` / ``FORCE_COLOR`` and only emits ANSI to a TTY, so piped output stays
clean (Ship-Gate). The live battle is observed via the player's own owner-scoped
poll; the public ``/replay`` is the spectator surface for after the match.

Wire: see ``agentdex_cli.arena_client.ArenaClient`` (enroll + Ed25519 PoP + loop).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import socket
import sys
from typing import Any

import httpx

from agentdex_cli.arena_client import (
    AgentIdentity,
    ArenaClient,
    TokenExpired,
    resolve_base,
    token_expired,
)

# Lazy rich import lives at call time so importing this module (e.g. for the
# arg parser / tests) never hard-requires a TTY toolkit.


def _console(force_no_color: bool = False):
    from rich.console import Console

    # Console auto-detects NO_COLOR + isatty; we only emit the rich frame when
    # attached to a terminal, else fall back to plain text (pipe-safe).
    return Console(no_color=force_no_color or bool(os.environ.get("NO_COLOR")))


def _hp_bar(pct: int | None, width: int = 24) -> str:
    """A semantic HP bar — green > yellow > red — degrading to glyphs under NO_COLOR."""
    if pct is None:
        return "[dim]?? HP[/dim]"
    pct = max(0, min(100, int(pct)))
    filled = round(width * pct / 100)
    color = "green" if pct > 50 else "yellow" if pct > 20 else "red"
    bar = f"[{color}]{'█' * filled}[/{color}][dim]{'─' * (width - filled)}[/dim]"
    return f"{bar} {pct:3d}%"


def _render_turn(console, state: dict[str, Any]) -> None:
    """Paint one turn: header, foe HP, board blob, recent-turn log."""
    from rich.panel import Panel
    from rich.text import Text

    battle_id = state.get("battle_id", "?")
    lane = state.get("lane", "?")
    turn = state.get("turn", "?")
    console.rule(f"[bold cyan]⚔ agentdex arena[/bold cyan]  ·  {lane}  ·  turn {turn}")

    foe = state.get("foe_active")
    if foe:
        console.print(
            Text.from_markup(f"[bold red]foe[/bold red] {foe}   ")
            + Text.from_markup(_hp_bar(state.get("foe_hp_pct")))
        )

    board = state.get("state")
    if board:
        console.print(Panel(Text(str(board)), title="board", border_style="cyan", expand=True))

    recent = state.get("recent_turns") or []
    if recent:
        log = Text("\n".join(str(line) for line in recent[-8:]), style="dim")
        console.print(Panel(log, title="recent", border_style="grey37", expand=True))

    console.print(f"[dim]battle {battle_id}[/dim]")


def _render_receipt(console, receipt: dict[str, Any], base: str) -> None:
    """Paint the end-of-battle receipt: outcome, rating delta, replay link.

    ``base`` is the arena URL the battle was actually played against so the replay
    link is correct even when the user passed a non-default --url."""
    from rich.panel import Panel
    from rich.text import Text

    you_won = receipt.get("you_won")
    winner = receipt.get("winner", "?")
    head = (
        "[bold green]✓ you won[/bold green]"
        if you_won
        else "[bold red]✗ you lost[/bold red]"
        if you_won is False
        else "[bold]battle ended[/bold]"
    )
    lines = [f"{head}   winner: [bold]{winner}[/bold]   turns: {receipt.get('turns', '?')}"]
    rating = receipt.get("rating")
    if isinstance(rating, dict):
        delta = rating.get("published_delta")
        d = f"{delta:+}" if isinstance(delta, int | float) else str(delta)
        lines.append(f"rating: {rating.get('rating', '?')} (rd {rating.get('rd', '?')})   Δ {d}")
    if receipt.get("badge_awarded"):
        lines.append(f"[yellow]🏅 badge: {receipt['badge_awarded']}[/yellow]")
    if receipt.get("quarantined"):
        lines.append(f"[red]⚠ quarantined: {receipt.get('quarantine_reason', '')}[/red]")
    replay = receipt.get("replay")
    if replay:
        lines.append(f"[dim]replay: {base.rstrip('/')}{replay}[/dim]")
    console.print(Panel(Text.from_markup("\n".join(lines)), title="result", border_style="green"))


def _prompt_choice(console, n_choices: int) -> int | None:
    """Read a 1-based move index from the human. Returns None to quit/forfeit."""
    from rich.prompt import Prompt

    if not sys.stdin.isatty():
        raise SystemExit(
            "error: `adx arena play` needs an interactive terminal (stdin is not a TTY)"
        )
    choices = [str(i) for i in range(1, n_choices + 1)] + ["q"]
    ans = Prompt.ask(
        f"[bold]your move[/bold] [1-{n_choices}] ([dim]q to quit[/dim])",
        choices=choices,
        show_choices=False,
        console=console,
    )
    return None if ans == "q" else int(ans)


def _resolve_token(
    client: ArenaClient, args: argparse.Namespace, console
) -> tuple[str, AgentIdentity]:
    """Get (token, identity): prefer an explicit token; else run the enroll flow.

    Enroll is the OOB-code path: request -> the confirmation code is delivered to
    the OWNER out of band (email/file inbox) -> the human pastes it. Curated
    launch typically hands out a batch-minted token instead (--token / env), which
    skips this entirely.
    """
    # Reuse a prior default name's credentials on upgrade (see
    # _effective_agent_name); an explicit --agent is unaffected.
    agent = _effective_agent_name(args)
    key_path = args.key or os.path.expanduser(f"~/.agentdex/{agent}.key")
    tok_path = os.path.expanduser(f"~/.agentdex/{agent}.token")
    token = args.token or os.environ.get("ADX_ARENA_TOKEN")
    # Reuse the token saved by a prior enrollment (same agent) so a returning
    # player does not re-enroll every run — but only if it is still valid.
    if not token and os.path.exists(tok_path):
        saved = open(tok_path).read().strip()
        if saved and not token_expired(saved):
            token = saved

    if token:
        if token_expired(token):
            raise TokenExpired(str(TokenExpired.__doc__))
        # The PoP key must match the token's registered pubkey; load the saved key.
        if not os.path.exists(key_path):
            raise SystemExit(
                f"error: token given but no agent key at {key_path} — the per-battle "
                f"proof-of-possession needs the private key you enrolled with. Pass --key."
            )
        return token, AgentIdentity.load(agent, key_path)

    # No token: enroll.
    if not args.owner:
        raise SystemExit("error: no --token and no --owner; one is required to enroll")
    identity = (
        AgentIdentity.load(agent, key_path)
        if os.path.exists(key_path)
        else AgentIdentity.new(agent)
    )
    identity.save(key_path)
    client.enroll_request(
        owner_email=args.owner,
        agent=identity,
        invite_code=getattr(args, "invite_code", None),
    )
    console.print(
        f"[yellow]enrollment requested[/yellow] — a confirmation code was sent to "
        f"[bold]{args.owner}[/bold] (check email / the owner inbox)."
    )
    from rich.prompt import Prompt

    code = Prompt.ask("paste the confirmation code", console=console)
    token = client.enroll_confirm(code.strip())
    os.makedirs(os.path.dirname(tok_path), exist_ok=True)
    with open(tok_path, "w") as f:
        f.write(token)
    os.chmod(tok_path, 0o600)
    console.print(f"[green]enrolled[/green] — token saved to {tok_path}")
    return token, identity


def _default_agent_name() -> str:
    """A machine-stable, globally-distinct default agent name that survives the
    arena's 24-char server-side name cap (MAX_NAME_LEN) AND resists collisions at
    public-arena scale.

    Arena names are unique across ALL users and capped at 24 chars by
    ``sanitize_name`` (a longer name is silently truncated server-side, so the
    CLI-side and server-side identities would diverge). The short ``tp-`` prefix
    leaves room for a WIDE 60-bit hash of the FULL hostname so distinct hosts
    stay distinct even at scale — the earlier 32-bit suffix could collide (two
    hosts hashing to the same 8 hex). The leftover budget carries a short,
    human-readable host hint. The whole name is <=24 chars (so CLI and server
    names match) and stable across runs (so the saved key/token keep matching).

    Default-name format history (see _legacy_default_agent_names for the
    upgrade fallback): ``terminal-player-<hostname>`` (#271) ->
    ``terminal-player-<8 hex>`` (#285) -> this ``tp-<hint>-<15 hex>`` form."""
    host = socket.gethostname() or "host"
    digest = hashlib.blake2s(host.encode("utf-8"), digest_size=8).hexdigest()[:15]  # 60 bits
    hint = re.sub(r"[^a-z0-9]", "", host.lower())
    room = 24 - len("tp-") - len(digest) - 1  # 1 for the '-' before the hash
    hint = hint[: max(room, 0)]
    return f"tp-{hint}-{digest}" if hint else f"tp-{digest}"


def _legacy_default_agent_names() -> list[str]:
    """Prior forms of the default agent name, so a returning user's existing
    credentials are reused across default-name format changes instead of being
    orphaned by an upgrade (PR #285 review 3435385944). Newest legacy form first."""
    host = socket.gethostname() or "host"
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", host) or "host"
    return [
        # #285: terminal-player-<8 hex of the full hostname>
        f"terminal-player-{hashlib.blake2s(host.encode('utf-8'), digest_size=4).hexdigest()}",
        # pre-#279: terminal-player-<sanitized hostname>, capped at 64 (the CLI
        # saved under the untruncated name even though the server truncated to 24).
        f"terminal-player-{sanitized}"[:64],
        # the original CLI default, the literal `terminal-player` (before any
        # hostname/hash suffix) — credentials at ~/.agentdex/terminal-player.*
        # (PR #287 review 3435479234).
        "terminal-player",
    ]


def _effective_agent_name(args: argparse.Namespace) -> str:
    """The agent name to actually use for credential paths + identity.

    An explicit ``--agent`` is honored verbatim. For the DEFAULT agent, reuse a
    PRIOR default name's credentials on upgrade so the format change does not
    orphan a still-valid enrollment — but ONLY for the implicit saved-token path,
    and ONLY when the prior credentials are usable (PR #287 review 3435479226):

    - An explicit ``--token`` / ``ADX_ARENA_TOKEN`` defines the identity for the
      CURRENT default name; never redirect it to a legacy key it was not signed
      with.
    - A legacy candidate is taken only when it has BOTH a key and a NON-EXPIRED
      saved token. An expired legacy token would otherwise be selected here and
      then dropped by _resolve_token, forcing a re-enroll of the permanently
      registered old name — worse than enrolling the new identity fresh.
    """
    if args.agent != _default_agent_name():
        return args.agent  # user chose it explicitly
    if getattr(args, "token", None) or os.environ.get("ADX_ARENA_TOKEN"):
        return args.agent  # an explicit token defines the current-name identity
    base = os.path.expanduser("~/.agentdex")
    if os.path.exists(os.path.join(base, f"{args.agent}.token")):
        return args.agent  # already enrolled under the current default
    for legacy in _legacy_default_agent_names():
        tok_path = os.path.join(base, f"{legacy}.token")
        key_path = os.path.join(base, f"{legacy}.key")
        if not (os.path.exists(tok_path) and os.path.exists(key_path)):
            continue
        try:
            saved = open(tok_path).read().strip()
        except OSError:
            continue
        if saved and not token_expired(saved):
            return legacy  # reuse only a still-usable prior enrollment
    return args.agent


def _start_ui(console: Any, arena_base: str, battle_id: str) -> Any:
    """Start the local arena2d browser UI for this battle and print its URL.

    Best-effort: returns the running ``ArenaUiServer``, or ``None`` if the arena2d
    assets are missing or the server fails to start (the battle proceeds either way).
    The browser talks ONLY to this local server; the spectator bridge needs no token."""
    from agentdex_cli.arena_ui import ArenaUiServer, find_arena2d_dir

    web_dir = find_arena2d_dir()
    if web_dir is None:
        console.print(
            "[yellow]--ui: web/arena2d not found (run from the repo root or set "
            "ADX_ARENA2D_DIR); continuing without the browser UI.[/yellow]"
        )
        return None
    try:
        server = ArenaUiServer(web_dir, arena_base, battle_id)
        url = server.start()
    except Exception as e:  # noqa: BLE001 — the UI is a bonus, never block the battle
        console.print(f"[yellow]--ui: failed to start ({e}); continuing without it.[/yellow]")
        return None
    console.print(
        f"[bold green]▶ arena2d UI:[/bold green] [underline]{url}[/underline]  "
        "[dim](port-forward if this box is remote; reload the page to pull later turns)[/dim]"
    )
    return server


def _hold_ui(console: Any, ui_server: Any) -> None:
    """Keep the UI server up after the battle so the full animated replay stays viewable."""
    url = getattr(ui_server, "url", "") or ""
    console.print(
        f"[dim]arena2d UI still live{(' at ' + url) if url else ''} — "
        "reload it for the full replay, then press Enter to close.[/dim]"
    )
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass


def cmd_arena_play(argv: list[str]) -> int:
    """`adx arena play` — drive a human-played battle in the terminal."""
    p = argparse.ArgumentParser(
        prog="adx arena play", description="Play a battle in your terminal."
    )
    p.add_argument(
        "--url", help="arena base URL (default: $ADX_ARENA_URL or agentdex.ai-builders.space)"
    )
    p.add_argument("--token", help="consent token (default: $ADX_ARENA_TOKEN; else enroll)")
    p.add_argument("--owner", help="owner email for enrollment (if no token)")
    p.add_argument(
        "--invite-code",
        default=os.environ.get("ADX_ARENA_INVITE_CODE"),
        help="invite code to pass through the OOB enrollment request",
    )
    p.add_argument(
        "--agent",
        default=_default_agent_name(),
        help="agent name (default: terminal-player-<hostname>)",
    )
    p.add_argument(
        "--key", help="path to the agent's Ed25519 key (default: ~/.agentdex/<agent>.key)"
    )
    p.add_argument("--lane", choices=["sandbox", "rated"], default="sandbox")
    p.add_argument("--gym", help="sandbox gym leader to challenge (optional)")
    p.add_argument("--team", help="path to a packed/exported team file (default: starter draft)")
    p.add_argument(
        "-u",
        "--ui",
        action="store_true",
        help="serve the arena2d browser visualizer for this battle (prints a local URL)",
    )
    args = p.parse_args(argv)

    console = _console()
    # Fail BEFORE enrolling / starting a battle if input is not interactive —
    # otherwise we'd begin a live battle and only discover stdin is not a TTY at
    # the first move prompt.
    if not sys.stdin.isatty():
        raise SystemExit(
            "error: `adx arena play` needs an interactive terminal (stdin is not a TTY)"
        )

    raw_team = open(args.team).read().strip() if args.team else None
    ui_server = None  # arena2d browser UI handle (started after battle_begin, if --ui)

    try:
        with ArenaClient(base=resolve_base(args.url)) as client:
            token, identity = _resolve_token(client, args, console)
            # A packed team is a single line; a Showdown EXPORT (multi-line) must be
            # packed via /team/draft before /battle/begin (which expects packed).
            team_packed = raw_team
            if raw_team and "\n" in raw_team:
                draft = client.team_draft(token, raw_team)
                if not draft.get("valid", False):
                    raise SystemExit(f"error: team failed validation: {draft.get('errors')}")
                team_packed = draft["packed"]
            console.print(
                f"[dim]arena: {client.base}  ·  agent: {identity.name}  ·  lane: {args.lane}[/dim]"
            )
            state = client.battle_begin(
                token, identity, team_packed=team_packed, lane=args.lane, gym_leader=args.gym
            )
            # battle_id is fixed for the whole battle; /choose responses need not
            # echo it, so capture it once from begin (a multi-turn battle would
            # otherwise KeyError on state["battle_id"] after the first choice).
            battle_id = state["battle_id"]
            if args.ui:
                ui_server = _start_ui(console, client.base, battle_id)
            while state.get("status") != "ended":
                _render_turn(console, state)
                n = int(state.get("n_choices") or 0)
                if n <= 0:
                    console.print("[red]no legal choices returned; aborting[/red]")
                    return 1
                choice = _prompt_choice(console, n)
                if choice is None:
                    console.print(
                        "[yellow]leaving — the battle stays LIVE server-side (not "
                        "forfeited); resume by polling /state.[/yellow]"
                    )
                    return 0
                state = client.battle_choose(token, battle_id, choice)
            _render_receipt(console, state, client.base)
            if ui_server is not None:
                _hold_ui(console, ui_server)
            return 0
    except KeyboardInterrupt:
        console.print(
            "\n[dim]interrupted — leaving the battle running; resume by polling state.[/dim]"
        )
        return 130
    except TokenExpired as e:
        console.print(f"[red]error:[/red] {e}")
        return 2
    except httpx.HTTPStatusError as e:
        body = ""
        try:
            body = f": {e.response.text[:200]}"
        except Exception:
            pass
        console.print(f"[red]error:[/red] arena returned HTTP {e.response.status_code}{body}")
        return 1
    except httpx.HTTPError as e:
        console.print(f"[red]error:[/red] could not reach arena: {e}")
        return 1
    finally:
        if ui_server is not None:
            ui_server.stop()
