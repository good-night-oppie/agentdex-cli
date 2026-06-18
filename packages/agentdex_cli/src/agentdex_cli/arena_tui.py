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
import os
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


def _render_receipt(console, receipt: dict[str, Any]) -> None:
    """Paint the end-of-battle receipt: outcome, rating delta, replay link."""
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
        d = f"{delta:+}" if isinstance(delta, (int, float)) else str(delta)
        lines.append(f"rating: {rating.get('rating', '?')} (rd {rating.get('rd', '?')})   Δ {d}")
    if receipt.get("badge_awarded"):
        lines.append(f"[yellow]🏅 badge: {receipt['badge_awarded']}[/yellow]")
    if receipt.get("quarantined"):
        lines.append(f"[red]⚠ quarantined: {receipt.get('quarantine_reason', '')}[/red]")
    replay = receipt.get("replay")
    if replay:
        lines.append(f"[dim]replay: {resolve_base()}{replay}[/dim]")
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
    key_path = args.key or os.path.expanduser(f"~/.agentdex/{args.agent}.key")
    token = args.token or os.environ.get("ADX_ARENA_TOKEN")

    if token:
        if token_expired(token):
            raise TokenExpired(str(TokenExpired.__doc__))
        # The PoP key must match the token's registered pubkey; load the saved key.
        if not os.path.exists(key_path):
            raise SystemExit(
                f"error: token given but no agent key at {key_path} — the per-battle "
                f"proof-of-possession needs the private key you enrolled with. Pass --key."
            )
        return token, AgentIdentity.load(args.agent, key_path)

    # No token: enroll.
    if not args.owner:
        raise SystemExit("error: no --token and no --owner; one is required to enroll")
    identity = (
        AgentIdentity.load(args.agent, key_path)
        if os.path.exists(key_path)
        else AgentIdentity.new(args.agent)
    )
    identity.save(key_path)
    client.enroll_request(owner_email=args.owner, agent=identity)
    console.print(
        f"[yellow]enrollment requested[/yellow] — a confirmation code was sent to "
        f"[bold]{args.owner}[/bold] (check email / the owner inbox)."
    )
    from rich.prompt import Prompt

    code = Prompt.ask("paste the confirmation code", console=console)
    token = client.enroll_confirm(code.strip())
    tok_path = os.path.expanduser(f"~/.agentdex/{args.agent}.token")
    os.makedirs(os.path.dirname(tok_path), exist_ok=True)
    with open(tok_path, "w") as f:
        f.write(token)
    os.chmod(tok_path, 0o600)
    console.print(f"[green]enrolled[/green] — token saved to {tok_path}")
    return token, identity


def cmd_arena_play(argv: list[str]) -> int:
    """`adx arena play` — drive a human-played battle in the terminal."""
    p = argparse.ArgumentParser(
        prog="adx arena play", description="Play a battle in your terminal."
    )
    p.add_argument("--url", help="arena base URL (default: $ADX_ARENA_URL or agentdex.builders)")
    p.add_argument("--token", help="consent token (default: $ADX_ARENA_TOKEN; else enroll)")
    p.add_argument("--owner", help="owner email for enrollment (if no token)")
    p.add_argument(
        "--agent", default="terminal-player", help="agent name (default: terminal-player)"
    )
    p.add_argument(
        "--key", help="path to the agent's Ed25519 key (default: ~/.agentdex/<agent>.key)"
    )
    p.add_argument("--lane", choices=["sandbox", "rated"], default="sandbox")
    p.add_argument("--gym", help="sandbox gym leader to challenge (optional)")
    p.add_argument("--team", help="path to a packed/exported team file (default: starter draft)")
    args = p.parse_args(argv)

    console = _console()
    team_packed = None
    if args.team:
        team_packed = open(args.team).read().strip()

    try:
        with ArenaClient(base=resolve_base(args.url)) as client:
            token, identity = _resolve_token(client, args, console)
            console.print(
                f"[dim]arena: {client.base}  ·  agent: {identity.name}  ·  lane: {args.lane}[/dim]"
            )
            state = client.battle_begin(
                token, identity, team_packed=team_packed, lane=args.lane, gym_leader=args.gym
            )
            while state.get("status") != "ended":
                _render_turn(console, state)
                n = int(state.get("n_choices") or 0)
                if n <= 0:
                    console.print("[red]no legal choices returned; aborting[/red]")
                    return 1
                choice = _prompt_choice(console, n)
                if choice is None:
                    console.print("[yellow]forfeiting…[/yellow]")
                    return 0
                state = client.battle_choose(token, state["battle_id"], choice)
            _render_receipt(console, state)
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
