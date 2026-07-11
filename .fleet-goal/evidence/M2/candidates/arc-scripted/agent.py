#!/usr/bin/env python3
"""Greedy manhattan heuristic for LocalArcEngine — no LLM, deterministic, $0."""

from __future__ import annotations

import json
import sys
from typing import Any


def _choose_action(frame: dict[str, Any]) -> str:
    agent = frame.get("agent") or [0, 0]
    goal = frame.get("goal") or [0, 0]
    ar, ac = int(agent[0]), int(agent[1])
    gr, gc = int(goal[0]), int(goal[1])
    # Prefer vertical then horizontal — stable, deterministic.
    if ar < gr:
        return "down"
    if ar > gr:
        return "up"
    if ac < gc:
        return "right"
    if ac > gc:
        return "left"
    return "up"  # already on goal; engine should have set done


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict) or msg.get("type") != "observation":
            continue
        frame = msg.get("frame") or {}
        if not isinstance(frame, dict):
            frame = {}
        action = _choose_action(frame)
        print(
            json.dumps({"type": "action", "action": action}, separators=(",", ":")),
            flush=True,
        )


if __name__ == "__main__":
    main()
