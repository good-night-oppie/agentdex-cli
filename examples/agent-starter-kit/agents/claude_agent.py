"""Claude-driven agent. Reads battle state, asks Claude to pick a move, loops.

Uses the Anthropic Messages API directly (no claude-agent-sdk dep) so this kit stays
small. Swap to anthropic.AsyncClient + tool_use if you want richer ReAct.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena_client import AgentIdentity, ArenaClient, play_until_end  # noqa: E402


SYSTEM = """You are a Pokémon gen9 OU player. The user will give you a battle state.

Respond with EXACTLY a single integer between 1 and n_choices — the 1-based index of
the move you want to make. No explanation, no JSON, no prose. Just the integer.

Tips:
- Moves come before switches in the choice list.
- Read `recent_turns` for what happened on the last turns.
- `foe_active` + `foe_hp_pct` are the only opponent intel you get mid-battle.
"""


def make_decider(model: str = "claude-haiku-4-5-20251001"):
    import anthropic

    client = anthropic.Anthropic()

    def decide(state: dict) -> int:
        msg = client.messages.create(
            model=model,
            max_tokens=8,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(state)}],
        )
        text = "".join(b.text for b in msg.content if hasattr(b, "text")).strip()
        try:
            idx = int(text.split()[0])
        except (ValueError, IndexError):
            print(f"warning: Claude returned non-int {text!r}; defaulting to 1", file=sys.stderr)
            return 1
        n = state.get("n_choices", 1)
        return max(1, min(idx, n))

    return decide


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("ARENA_TOKEN", ""))
    ap.add_argument("--keyfile", required=True)
    ap.add_argument("--agent-name", required=True)
    ap.add_argument("--team-file", required=True)
    ap.add_argument("--lane", default="sandbox", choices=["sandbox", "rated"])
    ap.add_argument(
        "--gym-leader",
        default=None,
        choices=[
            None,
            "gym-balance",
            "gym-hyper-offense",
            "gym-stall",
            "gym-trick-room",
            "anchor-random",
            "anchor-max_damage",
            "anchor-heuristic",
        ],
        help="canonical gym leader / anchor ID accepted by the gateway",
    )
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    args = ap.parse_args()

    if not args.token:
        print("error: pass --token or set ARENA_TOKEN", file=sys.stderr)
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY", file=sys.stderr)
        return 2

    # Build the decider BEFORE opening a battle so a missing `anthropic` dep
    # (i.e. the user did `uv sync` without the `[claude]` extra) fails fast
    # without consuming arena capacity (and rated quota if --lane rated).
    try:
        decide = make_decider(args.model)
    except ModuleNotFoundError as e:
        print(
            f"error: {e.name} is not installed. Install the claude extra:\n"
            f"  uv sync --extra claude\n"
            f"or: uv pip install anthropic",
            file=sys.stderr,
        )
        return 2

    agent = AgentIdentity.load(args.agent_name, args.keyfile)
    export = Path(args.team_file).read_text()

    with ArenaClient() as client:
        draft = client.team_draft(args.token, export)
        if not draft["valid"]:
            print("team invalid:", json.dumps(draft["errors"], indent=2))
            return 1
        initial = client.battle_begin(
            args.token,
            agent,
            team_packed=draft["packed"],
            lane=args.lane,
            gym_leader=args.gym_leader,
        )
        battle_id = initial["battle_id"]
        print(f"battle_id = {battle_id}", file=sys.stderr)
        final = play_until_end(client, args.token, battle_id, decide, initial_state=initial)
        print(json.dumps(final, indent=2))
        return 0


if __name__ == "__main__":
    sys.exit(main())
