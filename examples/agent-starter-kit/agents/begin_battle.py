"""Begin a battle and print battle_id + initial state, then exit.

Use this to bind ARENA_BATTLE_ID for the MCP proxy (Mode 2) — unlike
max_damage_agent.py / claude_agent.py, this does NOT play to completion.
The battle stays live so the proxy's decide_move tool drives it from there.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena_client import AgentIdentity, ArenaClient, run_agent_main  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("ARENA_TOKEN", ""))
    ap.add_argument("--keyfile", required=True, help="path to agent ed25519 priv key (raw 32B)")
    ap.add_argument("--agent-name", required=True)
    ap.add_argument("--team-file", required=True, help="Showdown team export .txt")
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
    args = ap.parse_args()

    if not args.token:
        print("error: pass --token or set ARENA_TOKEN", file=sys.stderr)
        return 2

    agent = AgentIdentity.load(args.agent_name, args.keyfile)
    export = Path(args.team_file).read_text()

    with ArenaClient() as client:
        draft = client.team_draft(args.token, export)
        if not draft["valid"]:
            print("team invalid:", json.dumps(draft["errors"], indent=2), file=sys.stderr)
            return 1
        initial = client.battle_begin(
            args.token,
            agent,
            team_packed=draft["packed"],
            lane=args.lane,
            gym_leader=args.gym_leader,
        )
        battle_id = initial["battle_id"]
        # Two lines on stdout for shell capture: battle_id then initial-state JSON.
        # Stderr carries the human-readable hint.
        print(battle_id)
        print(json.dumps(initial))
        print(
            f"battle_id={battle_id}  — bind via: export ARENA_BATTLE_ID={battle_id}",
            file=sys.stderr,
        )
        return 0


if __name__ == "__main__":
    sys.exit(run_agent_main(main))
