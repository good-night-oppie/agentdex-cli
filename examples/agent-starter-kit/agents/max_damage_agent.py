"""Minimal heuristic agent: always picks choice 1 (first legal move).

Showdown's `legal_choices` puts moves before switches; choice 1 is "click the first
move on your active mon." Useful as a baseline and as a smoke test for the loop —
beats nothing serious, but proves the protocol end-to-end.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Resolve sibling module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena_client import AgentIdentity, ArenaClient, play_until_end  # noqa: E402


def decide_first_legal(_state: dict) -> int:
    return 1


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
        choices=[None, "balance", "hyper_offense", "stall", "trick_room"],
    )
    args = ap.parse_args()

    if not args.token:
        print("error: pass --token or set ARENA_TOKEN", file=sys.stderr)
        return 2

    agent = AgentIdentity.load(args.agent_name, args.keyfile)
    export = Path(args.team_file).read_text()

    with ArenaClient() as client:
        # 1. validate the team
        draft = client.team_draft(args.token, export)
        if not draft["valid"]:
            print("team invalid:", json.dumps(draft["errors"], indent=2))
            return 1
        packed = draft["packed"]

        # 2. begin
        initial = client.battle_begin(
            args.token, agent, team_packed=packed, lane=args.lane, gym_leader=args.gym_leader
        )
        battle_id = initial["battle_id"]
        print(f"battle_id = {battle_id}", file=sys.stderr)

        # 3. drive to end
        final = play_until_end(
            client, args.token, battle_id, decide_first_legal, initial_state=initial
        )
        print(json.dumps(final, indent=2))
        return 0


if __name__ == "__main__":
    sys.exit(main())
