#!/usr/bin/env python3
"""LLM-driven Gen1 OU policy for the adx PokeAgent battle window.

Per move: read one observation line on stdin, ask a cheap Claude model (via the
loopback TeamClaude gateway — no credentials, no remote base URL) to pick a legal
move id or switch species, print one action line on stdout. Every failure path
(timeout, HTTP error, unparseable reply, empty legal set) ABSTAINS with
action=None so the harness falls back to a legal move and the battle never breaks.
Falls back to max-base-power when the model is unreachable, so the run still
produces a rated result instead of forfeiting.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

GATEWAY = os.environ.get("ADX_BRIDGES_BASE_URL", "http://127.0.0.1:3456").rstrip("/")
MODEL = os.environ.get("ADX_POKEAGENT_LLM_MODEL", "claude-gpt-5.6-sol")
MAX_TOKENS = int(os.environ.get("ADX_POKEAGENT_LLM_MAX_TOKENS", "24"))
TIMEOUT = float(os.environ.get("ADX_POKEAGENT_LLM_TIMEOUT", "20"))
LOG = open(os.environ.get("ADX_POKEAGENT_LLM_LOG", "/dev/null"), "a", encoding="utf-8")


def _log(msg: str) -> None:
    try:
        LOG.write(msg + "\n")
        LOG.flush()
    except Exception:
        pass


def _legal(battle: dict) -> tuple[list[str], list[str]]:
    moves = [str(m.get("id", "")) for m in (battle.get("available_moves") or []) if m.get("id")]
    switches = [
        str(s.get("species", ""))
        for s in (battle.get("available_switches") or [])
        if s.get("species")
    ]
    return moves, switches


def _fallback(battle: dict) -> str | None:
    moves = battle.get("available_moves") or []
    if moves:
        return str(max(moves, key=lambda m: m.get("base_power", 0)).get("id") or "") or None
    switches = battle.get("available_switches") or []
    return (str(switches[0].get("species") or "") or None) if switches else None


def _ask_llm(battle: dict, moves: list[str], switches: list[str]) -> str | None:
    opp = battle.get("opponent") or {}
    prompt = (
        "You are playing Gen 1 OU Pokemon on Showdown. Pick the single best action.\n"
        f"Your active: {battle.get('active_species')} "
        f"(HP {battle.get('active_hp_fraction')}, types {battle.get('active_types')}).\n"
        f"Opponent: {opp.get('species')} (HP {opp.get('hp_fraction')}, types {opp.get('types')}, "
        f"status {opp.get('status')}).\n"
        f"force_switch={battle.get('force_switch')}.\n"
        f"Legal moves: {moves}\n"
        f"Legal switches (species): {switches}\n"
        "Reply with ONLY the exact move id or switch species string, nothing else."
    )
    body = json.dumps(
        {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        f"{GATEWAY}/v1/messages",
        data=body,
        method="POST",
        headers={"content-type": "application/json", "anthropic-version": "2023-06-01"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8", "replace"))
    text = ""
    for block in payload.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            text += block.get("text", "")
    pick = text.strip().split()[0].strip(".,'\"") if text.strip() else ""
    _log(f"picked={pick!r} legal_moves={moves} legal_switches={switches}")
    norm = "".join(ch for ch in pick.casefold() if ch.isalnum())
    for cand in moves + switches:
        if "".join(ch for ch in cand.casefold() if ch.isalnum()) == norm:
            return cand
    return None  # unrecognized -> abstain (harness legalizes)


def _choose(battle: dict) -> str | None:
    moves, switches = _legal(battle)
    if not moves and not switches:
        return None
    try:
        pick = _ask_llm(battle, moves, switches)
        if pick is not None:
            return pick
    except Exception as exc:  # noqa: BLE001 — never raise, always fall back
        _log(f"llm error {type(exc).__name__}")
    return _fallback(battle)


def main() -> None:
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict) or msg.get("type") != "observation":
            continue
        battle = msg.get("battle")
        if not isinstance(battle, dict):
            battle = {}
        print(
            json.dumps({"type": "action", "action": _choose(battle)}, separators=(",", ":")),
            flush=True,
        )


if __name__ == "__main__":
    main()
