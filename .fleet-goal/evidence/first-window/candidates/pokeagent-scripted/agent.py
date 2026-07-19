#!/usr/bin/env python3
"""Deterministic legal-first policy for the bounded M3 live proof."""

from __future__ import annotations

import json
import sys
from typing import Any


def choose_action(battle: dict[str, Any]) -> str | None:
    moves = battle.get("available_moves") or []
    if moves:
        return str(max(moves, key=lambda move: move.get("base_power", 0))["id"])
    switches = battle.get("available_switches") or []
    if switches:
        return str(switches[0].get("species") or "") or None
    return None


def main() -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict) or message.get("type") != "observation":
            continue
        battle = message.get("battle")
        if not isinstance(battle, dict):
            battle = {}
        print(
            json.dumps({"type": "action", "action": choose_action(battle)}, separators=(",", ":")),
            flush=True,
        )


if __name__ == "__main__":
    main()
