"""L1 — the LIVE codex move hook (SECH SPEC / Contract 5; ADR-0014).

This is the ``codex_adapter.DecideFn`` that plugs the REAL openai/codex CLI into the
self-play move seam (#343 wired the seam with ``decide=None`` → greedy; this adds the
live codex behind it). Given a ``BattleHarness`` (whose ``system_prompt`` IS the
evolving policy ``p``) + the JSON ``codex_context`` turn view, it asks codex to choose
a legal move id. bene evolving the harness therefore changes how codex plays — the ACT
step of the self-evolving-codex-harness loop (tasks/codex-harness-evolution/SPEC.md).

Design rails:
- The subprocess + the codex CLI live HERE, NOT in the pure ``codex_adapter`` — that
  module stays import-safe + unit-testable.
- FAIL-SAFE: any failure (codex missing, timeout, bad output, illegal move) returns
  None, so the adapter falls back to a random legal order; codex NEVER crashes a battle.
- The codex invocation is INJECTABLE (``run=``) so unit tests never shell out; a gated
  live smoke exercises the real CLI.
- The real CLI invocation runs read-only + ephemeral. Evolved prompts may choose
  moves; they must not get a write-capable agent session from this per-turn hook.
- Enabled in the runner by ``ADX_CODEX_LIVE=1`` (default = deterministic greedy, so
  tests + offline runs are unchanged).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from typing import Any

# (prompt, json_schema, timeout_sec) -> the structured object codex returned.
CodexRunFn = Callable[[str, "dict[str, Any]", float], "dict[str, Any]"]

_DEFAULT_TIMEOUT_SEC = 60.0


def _timeout_sec() -> float:
    """The per-call codex timeout from ``ADX_CODEX_TIMEOUT_SEC`` (default 60s),
    parsed defensively. A mistyped (non-numeric) override falls back to the default
    instead of raising ``ValueError`` — parsing this at MODULE scope used to crash
    the lazy ``import codex_decide`` in the runner BEFORE ``codex_decide``'s
    fail-safe ``try/except`` could catch it, aborting the battle. The live hook is
    documented to never crash a battle, so the override must fail safe too."""
    try:
        return float(os.environ.get("ADX_CODEX_TIMEOUT_SEC", "60") or "60")
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT_SEC


# The schema codex's last message must conform to (--output-schema). OpenAI strict
# structured output requires EVERY property to be listed in ``required`` (else the
# request 400s with invalid_json_schema), so both keys are required.
_MOVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "move_id": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["move_id", "rationale"],
    "additionalProperties": False,
}


def _build_prompt(harness: Any, ctx: Mapping[str, Any], legal_ids: list[str]) -> str:
    """The per-turn prompt. The harness's ``system_prompt`` is prepended verbatim — it
    IS codex's policy ``p`` (the thing bene evolves) — so a refined harness changes the
    choice. Only legal actions (moves + switch species) are offered, so codex cannot
    pick an illegal one; on a forced switch only the switch targets are legal."""
    policy = str(getattr(harness, "system_prompt", "") or "").strip()
    moves = ctx.get("available_moves") or []
    switches = ctx.get("available_switches") or []
    move_lines = ", ".join(f"{m.get('id')} (power {m.get('base_power', 0)})" for m in moves)
    switch_lines = ", ".join(str(s.get("species") or "") for s in switches)
    species = ctx.get("active_species") or "your active Pokemon"
    hp = float(ctx.get("active_hp_fraction") or 0.0)
    header = policy + "\n\n" if policy else ""
    moves_line = f"Legal moves (id: base power): {move_lines}.\n" if moves else ""
    switch_line = f"Legal switches (species): {switch_lines}.\n" if switches else ""
    return (
        f"{header}You are choosing exactly ONE action in a Pokemon Showdown singles battle.\n"
        f"Active: {species} at {hp:.0%} HP.\n"
        f"{moves_line}{switch_line}"
        f"Pick the single best action id (a move id or a switch species) from: "
        f"{', '.join(legal_ids)}.\n"
        'Reply ONLY with JSON {"move_id": "<one of the legal ids>", "rationale": "<=12 words"}.'
    )


def _parse_last_json(text: str) -> dict[str, Any]:
    """Best-effort: the last balanced ``{...}`` block in ``text``, parsed as JSON."""
    depth, start, last = 0, -1, ""
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                last = text[start : i + 1]
    return json.loads(last) if last else {}


def _codex_exec_args(codex_bin: str, schema_path: str, out_path: str, prompt: str) -> list[str]:
    """The sandboxed non-interactive Codex invocation for one move choice."""
    return [
        codex_bin,
        "exec",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--skip-git-repo-check",
        "--output-schema",
        schema_path,
        "--output-last-message",
        out_path,
        prompt,
    ]


def _run_codex_cli(prompt: str, schema: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Invoke the real codex CLI once for a structured move choice. Honors
    ``ADX_CODEX_BIN`` (default ``codex``) + ``ADX_CODEX_HOME`` (default ``~/gh/codex`` =
    the fork). Uses a read-only, ephemeral sandbox plus ``--output-schema`` for a
    schema-conforming last message."""
    codex_bin = os.environ.get("ADX_CODEX_BIN", "codex")
    codex_home = os.environ.get("ADX_CODEX_HOME", os.path.expanduser("~/gh/codex"))
    with tempfile.TemporaryDirectory() as td:
        schema_path = os.path.join(td, "schema.json")
        out_path = os.path.join(td, "last.txt")
        with open(schema_path, "w") as f:
            json.dump(schema, f)
        proc = subprocess.run(
            _codex_exec_args(codex_bin, schema_path, out_path, prompt),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=codex_home if os.path.isdir(codex_home) else None,
        )
        if os.path.exists(out_path):
            text = open(out_path).read().strip()
            if text:
                return _parse_last_json(text)
        return _parse_last_json(proc.stdout)


def codex_decide(
    harness: Any, ctx: Mapping[str, Any], *, run: CodexRunFn | None = None
) -> str | None:
    """A ``codex_adapter.DecideFn``: ask the live codex CLI for an action id (a move id
    or a switch species) and return codex's PROPOSED id, or None on abstention / ANY
    failure (the adapter then falls back to a random legal order). ``run`` is injectable
    so unit tests never shell out.

    Legality is NOT gated here: ``select_codex_move`` is the single legality gate — it
    counts an illegal proposal via ``on_illegal`` (→ ``raw_dims["illegal_moves"]`` →
    ``move_legibility``) and substitutes a legal order. Pre-filtering an illegal id to
    None here would mask a live illegal choice as an abstention, leaving the legibility
    guard vacuous for the very path it measures (PR #346 review #3440261654)."""
    moves = list(ctx.get("available_moves") or [])
    switches = list(ctx.get("available_switches") or [])
    legal_ids = [str(m.get("id") or "") for m in moves if m.get("id")]
    legal_ids += [str(s.get("species") or "") for s in switches if s.get("species")]
    if not legal_ids:
        return None
    runner = run or _run_codex_cli
    try:
        result = runner(_build_prompt(harness, ctx, legal_ids), _MOVE_SCHEMA, _timeout_sec())
        move_id = str((result or {}).get("move_id", "")).strip()
    except Exception:
        return None  # codex missing / timeout / bad output — never crash a battle
    return move_id or None  # the proposed id (legality is the adapter's gate); blank → abstain


__all__ = ["codex_decide", "CodexRunFn"]
