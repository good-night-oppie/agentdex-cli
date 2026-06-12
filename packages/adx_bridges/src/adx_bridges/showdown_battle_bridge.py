"""House battler — LLM-decided Showdown battles with a FIC turn loop (phase 6).

IDEAL §Arena A7 economics, harness-engineering FIC doctrine:
- FLAT per-turn context by construction: each decision prompt = bounded state
  render + rewrite-not-append scratchpad + last-3 turn lines. Nothing
  accumulates; turn-30 context == turn-3 context (CI-asserted ±10%).
- State renders are hard-capped at MAX_STATE_CHARS (8,000 chars ≈ ≤2,500
  tokens, tiktoken-verified in CI against a fixture corpus).
- Decisions route through the platform LLM proxy (AI_BUILDER_TOKEN,
  flash-tier) via an injected Decider — never private keys by default.
  A fail-closed BudgetGuard refuses decisions once the battle budget is
  spent (circuit-breaker posture).
- The gateway owns the clock (go/no-go): per-decision timeout falls back to
  the deterministic first-legal rail; MAX_CONSECUTIVE_TIMEOUTS forfeits the
  battle (the stalling side LOSES — tested with a deliberately-stalling
  decider).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from adx_showdown.protocol import ParsedRequest, legal_choices
from adx_showdown.sidecar import Sidecar
from adx_showdown.sim import BattleContext, BattleResult, Policy, run_battle

log = logging.getLogger(__name__)

MAX_STATE_CHARS = 8_000  # ≈ ≤2,500 tokens (CI-verified with tiktoken)
MAX_SCRATCHPAD_CHARS = 1_200
MAX_CONSECUTIVE_TIMEOUTS = 3
DEFAULT_DECIDE_TIMEOUT_S = 120.0  # go/no-go turn budget
PROXY_URL_ENV = "ADX_BUILDER_PROXY_URL"
DEFAULT_PROXY_URL = "https://space.ai-builders.com/backend/v1"
DEFAULT_PROXY_MODEL = "deepseek-v4-flash"

Decider = Callable[[str], Awaitable[tuple[str, dict]]]
"""prompt -> (raw_decision_text, usage_dict). Injected; CI uses fakes."""


class BattleForfeited(RuntimeError):
    """The house battler forfeited (stall rail) — the opponent wins."""


class BudgetExhausted(RuntimeError):
    """Fail-closed: decision budget spent; no further LLM calls (A7)."""


@dataclass
class BudgetGuard:
    """Counts decision usage; refuses when the cap is hit. Fail-closed."""

    max_decisions: int = 200
    used: int = 0

    def spend(self) -> None:
        if self.used >= self.max_decisions:
            raise BudgetExhausted(f"decision budget exhausted ({self.max_decisions})")
        self.used += 1


def render_state(
    req: ParsedRequest,
    ctx: BattleContext,
    *,
    scratchpad: str,
    recent_turns: list[str],
) -> str:
    """Bounded battle-state prompt. Strings inside `req` were sanitized at the
    protocol parse boundary (A6); this renderer only ever shrinks content."""
    choices = legal_choices(req)
    lines = [
        f"# Turn {ctx.turns} — you are {ctx.side}",
        f"Your active: {ctx.my_species or '?'} | Opponent active: {ctx.opponent_species or '?'}",
        "",
        "## Your options (reply with the NUMBER of your choice)",
    ]
    for i, choice in enumerate(choices, start=1):
        detail = ""
        if choice.startswith("move"):
            slot = int(choice.split()[1])
            for moves in req.active_moves[:1]:
                for mv in moves:
                    if mv.slot == slot:
                        detail = f" — {mv.move or mv.id} (pp {mv.pp}/{mv.maxpp})"
        elif choice.startswith("switch"):
            idx = int(choice.split()[1])
            for slot_info in req.bench:
                if slot_info.index == idx:
                    detail = f" — {slot_info.species} ({slot_info.condition})"
        lines.append(f"{i}. {choice}{detail}")
    lines += [
        "",
        "## Bench",
        *(f"- {s.species} {s.condition}{' [active]' if s.active else ''}" for s in req.bench),
        "",
        "## Scratchpad (your own notes from previous turns)",
        scratchpad or "(empty)",
        "",
        "## Recent turns",
        *(recent_turns[-3:] or ["(battle start)"]),
        "",
        'Reply as JSON: {"choice": <number>, "scratchpad": "<REWRITE your notes, max 1000 chars>"}',
    ]
    text = "\n".join(lines)
    return text[:MAX_STATE_CHARS]


def parse_decision(raw: str, n_choices: int) -> tuple[int | None, str | None]:
    """Extract (1-based choice index, new scratchpad) from decider output.
    Tolerant: bare numbers work; malformed output -> (None, None) -> fallback."""
    raw = raw.strip()
    try:
        start = raw.index("{")
        data = json.loads(raw[start : raw.rindex("}") + 1])
        idx = int(data.get("choice", 0))
        pad = str(data.get("scratchpad", ""))[:MAX_SCRATCHPAD_CHARS]
        return (idx if 1 <= idx <= n_choices else None), pad
    except (ValueError, json.JSONDecodeError, TypeError):
        for token in raw.replace(",", " ").split():
            if token.isdigit() and 1 <= int(token) <= n_choices:
                return int(token), None
        return None, None


def platform_proxy_decider(
    *,
    model: str = DEFAULT_PROXY_MODEL,
    timeout_s: float = 100.0,
) -> Decider:
    """Production decider: OpenAI-compatible platform proxy, AI_BUILDER_TOKEN
    auth (injected into deployed containers; never a private key)."""
    import httpx

    base = os.environ.get(PROXY_URL_ENV, DEFAULT_PROXY_URL).rstrip("/")
    token = os.environ.get("AI_BUILDER_TOKEN", "")

    async def _decide(prompt: str) -> tuple[str, dict]:
        if not token:
            raise BudgetExhausted("AI_BUILDER_TOKEN missing — refusing (fail-closed)")
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a Pokemon Showdown battler. Read the state, "
                                "pick the best option NUMBER, rewrite your scratchpad."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 400,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return text, dict(data.get("usage") or {})

    return _decide


@dataclass
class LlmBattlePolicy:
    """FIC turn loop: bounded render -> decide (timeout-railed) -> act.

    State lives HERE (scratchpad, recent turns, trajectory), not in any
    accumulating prompt — context stays flat across arbitrarily long battles.
    """

    decider: Decider
    trajectory_path: Path | None = None
    decide_timeout_s: float = DEFAULT_DECIDE_TIMEOUT_S
    budget: BudgetGuard = field(default_factory=BudgetGuard)
    scratchpad: str = ""
    recent_turns: list[str] = field(default_factory=list)
    consecutive_timeouts: int = 0
    prompt_chars_by_turn: dict[int, int] = field(default_factory=dict)
    total_usage: dict[str, int] = field(default_factory=dict)

    def _record(self, entry: dict) -> None:
        if self.trajectory_path is not None:
            self.trajectory_path.parent.mkdir(parents=True, exist_ok=True)
            with self.trajectory_path.open("a") as fh:
                fh.write(json.dumps(entry, sort_keys=True) + "\n")

    async def __call__(self, req: ParsedRequest, ctx: BattleContext) -> str | None:
        choices = legal_choices(req)
        if not choices:
            return None
        prompt = render_state(req, ctx, scratchpad=self.scratchpad, recent_turns=self.recent_turns)
        self.prompt_chars_by_turn[ctx.turns] = len(prompt)
        self.budget.spend()
        t0 = time.monotonic()
        try:
            raw, usage = await asyncio.wait_for(self.decider(prompt), timeout=self.decide_timeout_s)
            self.consecutive_timeouts = 0
        except TimeoutError:
            self.consecutive_timeouts += 1
            self._record(
                {
                    "turn": ctx.turns,
                    "timeout": True,
                    "consecutive": self.consecutive_timeouts,
                }
            )
            if self.consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                raise BattleForfeited(
                    f"{self.consecutive_timeouts} consecutive decision timeouts"
                ) from None
            return choices[0]  # deterministic fallback rail; battle continues
        idx, new_pad = parse_decision(raw, len(choices))
        if new_pad is not None:
            self.scratchpad = new_pad  # REWRITE, never append (FIC)
        choice = choices[idx - 1] if idx is not None else choices[0]
        self.recent_turns = (self.recent_turns + [f"turn {ctx.turns}: chose {choice}"])[-3:]
        for k, v in usage.items():
            if isinstance(v, int):
                self.total_usage[k] = self.total_usage.get(k, 0) + v
        self._record(
            {
                "turn": ctx.turns,
                "prompt_chars": len(prompt),
                "choice": choice,
                "decide_ms": round((time.monotonic() - t0) * 1000, 1),
                "usage": usage,
            }
        )
        return choice


async def play_house_battle(
    *,
    battle_id: str,
    format_id: str,
    seed: list[int],
    policy: LlmBattlePolicy,
    opponent: Policy,
    my_name: str = "house",
    opponent_name: str = "anchor",
    my_team: str | None = None,
    opponent_team: str | None = None,
    max_battles: int | None = None,
) -> BattleResult:
    """One house battle. A stall-rail forfeit returns a LOSS result (the
    opponent is the winner) instead of raising — the clock is the gateway's."""
    async with Sidecar(max_battles=max_battles) as sidecar:
        try:
            return await run_battle(
                sidecar,
                battle_id=battle_id,
                format_id=format_id,
                p1_name=my_name,
                p2_name=opponent_name,
                p1_policy=policy,
                p2_policy=opponent,
                seed=seed,
                p1_team=my_team,
                p2_team=opponent_team,
            )
        except BattleForfeited as e:
            log.warning("%s: forfeited — %s", battle_id, e)
            await sidecar.request("stop", battle=battle_id)
            return BattleResult(
                battle_id=battle_id,
                winner=opponent_name,  # stalling side loses (A7 clock rail)
                turns=max(policy.prompt_chars_by_turn, default=0),
                input_log=[],
                choice_errors=0,
            )
