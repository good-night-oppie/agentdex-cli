"""``adx run`` — the agentdex allocation loop (v3 MVP #2).

The whole thesis in one command:

    know which model does a job better  →  get the job done  →  learn a seed

Flow per invocation:
    1. classify the task into a *signature* (per the interview policy's job_types)
    2. consult the seed ledger — which model sits on the constrained-Pareto
       frontier for this signature under the user's objective order?
    3. allocate: exploit the known best, or explore an alternative (bandit rate)
    4. dispatch to the chosen model(s); fake engine emits three frontier axes
       (quality ↑, cost_dollar ↓, wall_clock_sec ↓)
    5. prune hard constraints → keep non-dominated → order by objective;
       append per-run axis rows to the seed JSONL and export
       ``.agentdex/frontier.json`` via ``FrontierLedger``.

Engines
-------
``--engine fake`` (default) scores each (model, signature) deterministically from
a hash across the three frontier axes, so the loop is fully demonstrable with no
network, no secrets, no spend — mirroring ``adx measure``'s fake-engine
convention. Different models win different signatures under different
objectives, so learning is observable. ``--engine bridges`` (later add-back)
will dispatch through ``adx_bridges`` over the TeamClaude substrate and run the
policy's real ``gate`` command.

stdlib + PyYAML + ``adx_frontier`` only. No model is called in fake mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from adx_frontier import selection
from adx_frontier.candidate import FRONTIER_AXES
from adx_frontier.ledger import FrontierLedger, FrontierRecord, TrustReceipt


# --------------------------------------------------------------------------- #
# policy + signature
# --------------------------------------------------------------------------- #
def load_policy(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"no orchestration policy at {path} — run `adx interview` first")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _policy_list(value: Any) -> list[str]:
    """Accept a YAML sequence or a comma-separated scalar; return list[str]."""
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item) for item in value]


def signature(task: str, job_types: list[str]) -> str:
    """Map a task to the first job_type whose head keyword appears in it.

    Deterministic and dependency-free. The head keyword is the part before any
    '/' (e.g. 'bugfix/python' → 'bugfix'), matched case-insensitively as a
    substring of the task. Falls back to 'default' when nothing matches.
    """
    low = task.lower()
    for jt in job_types:
        head = jt.split("/", 1)[0].strip().lower()
        if head and head in low:
            return jt
    return "default"


def max_cost_from_constraints(constraints: str) -> float | None:
    """Parse ``max $0.50/task`` style cost ceilings from the constraints string.

    Matches ``r'max\\s*\\$\\s*([0-9]+(?:\\.[0-9]+)?)'`` case-insensitively.
    ``'none'`` / no match → ``None``. Other constraint forms are a documented
    add-back.
    """
    if not constraints or constraints.strip().lower() == "none":
        return None
    m = re.search(r"max\s*\$\s*([0-9]+(?:\.[0-9]+)?)", constraints, flags=re.IGNORECASE)
    return float(m.group(1)) if m else None


def _parse_axes(raw_scores: dict[str, Any]) -> dict[str, float] | None:
    """Parse frontier axes; None on missing / bool / non-finite / unconvertible."""
    try:
        scores: dict[str, float] = {}
        for axis in FRONTIER_AXES:
            if axis not in raw_scores:
                return None
            value = raw_scores[axis]
            if isinstance(value, bool):
                return None
            parsed = float(value)
            if not math.isfinite(parsed):
                return None
            scores[axis] = parsed
        return scores
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# ledger — append-only axis rows; Pareto selection delegates to adx_frontier
# --------------------------------------------------------------------------- #
class FrontierSeedLedger:
    """Append-only JSONL seed store that delegates dominance to ``adx_frontier``.

    Each line: ``{"signature", "model", "scores": {3 axes}, "ts"}``. Records
    for one signature share partition ``(ladder_id=f"job:{sig}",
    base_model="adx-pool")`` so ``dominates`` / ``frontier()`` compare across
    models — that is the F1 delegation point.
    """

    def __init__(self, path: Path, *, max_cost: float | None = None) -> None:
        self.path = path
        self.max_cost = max_cost

    def append(self, *, signature: str, model: str, scores: dict[str, float], ts: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {"signature": signature, "model": model, "scores": scores, "ts": ts}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def _to_record(self, row: dict[str, Any], scores: dict[str, float], ts: str) -> FrontierRecord:
        sig = str(row["signature"])
        return FrontierRecord(
            candidate=str(row["model"]),
            ladder_id=f"job:{sig}",
            base_model="adx-pool",
            scores=scores,
            budget_usd=self.max_cost if self.max_cost else 1.0,
            budget_wall_clock_min=10.0,
            receipt=TrustReceipt(
                tier="self_reported",
                kind="adx-run-fake",
                artifacts=(f"seeds:{self.path}",),
            ),
            measured_at_utc=ts,
        )

    def records(self, sig: str) -> list[FrontierRecord]:
        """Parse rows for ``sig`` into ``FrontierRecord``s (skip corrupt lines)."""
        out: list[FrontierRecord] = []
        for row in self._rows():
            if row.get("signature") != sig or "model" not in row:
                continue
            raw_scores = row.get("scores")
            if not isinstance(raw_scores, dict):
                continue
            scores = _parse_axes(raw_scores)
            if scores is None:
                continue
            try:
                out.append(self._to_record(row, scores, str(row.get("ts") or "")))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def mean_records(self, sig: str) -> list[FrontierRecord]:
        """One synthetic record per model: mean of each axis (ts = latest row)."""
        agg: dict[str, list[dict[str, float]]] = {}
        latest_ts: dict[str, str] = {}
        latest_row: dict[str, dict[str, Any]] = {}
        for row in self._rows():
            if row.get("signature") != sig or "model" not in row:
                continue
            raw_scores = row.get("scores")
            if not isinstance(raw_scores, dict):
                continue
            scores = _parse_axes(raw_scores)
            if scores is None:
                continue
            model = str(row["model"])
            agg.setdefault(model, []).append(scores)
            latest_ts[model] = str(row.get("ts") or "")
            latest_row[model] = row
        out: list[FrontierRecord] = []
        for model, score_list in agg.items():
            means = {
                axis: sum(s[axis] for s in score_list) / len(score_list) for axis in FRONTIER_AXES
            }
            try:
                out.append(self._to_record(latest_row[model], means, latest_ts[model]))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def best_model(self, sig: str, objective: list[str], max_cost: float | None) -> str | None:
        """Winner under constrained-Pareto objective order over mean records."""
        survivors = selection.select(self.mean_records(sig), objective, max_cost_dollar=max_cost)
        return survivors[0].candidate if survivors else None

    def export_frontier(self, path: Path | None = None) -> Path:
        """Build a ``FrontierLedger`` from all raw rows and export ``frontier.json``."""
        target = path if path is not None else self.path.parent / "frontier.json"
        ledger = FrontierLedger()
        seen: set[tuple[str, str, tuple[tuple[str, float], ...]]] = set()
        for row in self._rows():
            if "model" not in row or "signature" not in row:
                continue
            raw_scores = row.get("scores")
            if not isinstance(raw_scores, dict):
                continue
            scores = _parse_axes(raw_scores)
            if scores is None:
                continue
            key = (str(row["signature"]), str(row["model"]), tuple(sorted(scores.items())))
            if key in seen:
                continue
            seen.add(key)
            try:
                ledger.add(self._to_record(row, scores, str(row.get("ts") or "")))
            except (KeyError, TypeError, ValueError):
                continue
        return ledger.export(target)


# --------------------------------------------------------------------------- #
# engine — fake now, bridges later
# --------------------------------------------------------------------------- #
def fake_axes(model: str, sig: str, task: str) -> dict[str, float]:
    """Deterministic pseudo-scores for the three frontier axes.

    - ``quality``: sha256(model+sig) base in [0,1), 0.85*base + 0.15*jitter(task),
      4 decimal places (task jitters quality only).
    - ``cost_dollar``: sha256(cost+model+sig) → [0.01, 0.60], 4dp.
    - ``wall_clock_sec``: sha256(wall+model+sig) → [5.0, 120.0], 1dp.

    Deterministic per (model, sig); no network.
    """
    h = hashlib.sha256(f"{model}\x00{sig}".encode()).digest()
    base = int.from_bytes(h[:4], "big") / 0xFFFFFFFF
    jitter = int.from_bytes(hashlib.sha256(task.encode()).digest()[:2], "big") / 0xFFFF
    quality = round(0.85 * base + 0.15 * jitter, 4)

    ch = hashlib.sha256(f"cost\x00{model}\x00{sig}".encode()).digest()
    cfrac = int.from_bytes(ch[:4], "big") / 0xFFFFFFFF
    cost_dollar = round(0.01 + cfrac * (0.60 - 0.01), 4)

    wh = hashlib.sha256(f"wall\x00{model}\x00{sig}".encode()).digest()
    wfrac = int.from_bytes(wh[:4], "big") / 0xFFFFFFFF
    wall_clock_sec = round(5.0 + wfrac * (120.0 - 5.0), 1)

    return {
        "quality": quality,
        "cost_dollar": cost_dollar,
        "wall_clock_sec": wall_clock_sec,
    }


# --------------------------------------------------------------------------- #
# allocation
# --------------------------------------------------------------------------- #
def allocate(
    pool: list[str],
    best: str | None,
    explore_rate: float,
    rng: random.Random,
    fanout: int,
) -> tuple[list[str], str]:
    """Return (models_to_dispatch, mode). Pure — incumbent ``best`` is injected.

    - cold start (``best`` is None or not in pool): fan out across up to
      ``fanout`` of the pool.
    - warm: with prob ``explore_rate``, add one non-incumbent explorer;
      otherwise exploit the known best alone.
    """
    if best is None or best not in pool:
        return pool[: max(1, fanout)], "cold-start-fanout"
    if rng.random() < explore_rate:
        alts = [m for m in pool if m != best]
        if alts:
            return [best, rng.choice(alts)], "explore"
    return [best], "exploit"


def _explore_rate(policy: dict[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(policy.get("explore_rate", 0.2))))
    except (TypeError, ValueError):
        return 0.2


def _run_record(
    model: str,
    sig: str,
    scores: dict[str, float],
    ts: str,
    ledger_path: Path,
    max_cost: float | None,
) -> FrontierRecord:
    return FrontierRecord(
        candidate=model,
        ladder_id=f"job:{sig}",
        base_model="adx-pool",
        scores=scores,
        budget_usd=max_cost if max_cost else 1.0,
        budget_wall_clock_min=10.0,
        receipt=TrustReceipt(
            tier="self_reported",
            kind="adx-run-fake",
            artifacts=(f"seeds:{ledger_path}",),
        ),
        measured_at_utc=ts,
    )


# --------------------------------------------------------------------------- #
# command
# --------------------------------------------------------------------------- #
def cmd_run(args: argparse.Namespace) -> int:
    policy = load_policy(Path(args.policy).expanduser())
    pool = _policy_list(policy.get("pool"))
    if not pool:
        print("policy has an empty pool — run `adx interview` to set one")
        return 2
    job_types = _policy_list(policy.get("job_types"))
    objective = _policy_list(policy.get("objective"))
    max_cost = max_cost_from_constraints(str(policy.get("constraints", "")))
    ledger = FrontierSeedLedger(Path(args.ledger).expanduser(), max_cost=max_cost)
    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    sig = signature(args.task, job_types)
    best = ledger.best_model(sig, objective, max_cost)
    models, mode = allocate(pool, best, _explore_rate(policy), rng, args.fanout)

    if args.engine != "fake":
        print(f"engine '{args.engine}' not wired yet — use --engine fake (bridges is the add-back)")
        return 2

    ts = datetime.now(UTC).replace(microsecond=0).isoformat()
    scored: list[tuple[str, dict[str, float]]] = [(m, fake_axes(m, sig, args.task)) for m in models]
    run_records = [_run_record(m, sig, axes, ts, ledger.path, max_cost) for m, axes in scored]
    survivors = selection.select(run_records, objective, max_cost_dollar=max_cost)
    winner_rec = survivors[0] if survivors else None
    winner = winner_rec.candidate if winner_rec else None

    obj_display = " > ".join(objective) if objective else " > ".join(FRONTIER_AXES)
    print(f"task      : {args.task}")
    print(f"signature : {sig}")
    print(f"allocation: {mode}  ({len(models)} candidate(s))")
    print(f"objective  : {obj_display}")
    for m, axes in scored:
        flag = "  <- winner" if m == winner else ""
        print(
            f"  q={axes['quality']:.4f} $={axes['cost_dollar']:.4f} "
            f"t={axes['wall_clock_sec']:.1f}s  {m}{flag}"
        )
    if winner_rec is None:
        ceiling = max_cost if max_cost is not None else 0.0
        print(f"all candidates exceed max cost ${ceiling} — recording, no winner")
    else:
        wa = winner_rec.scores
        print(
            f"winner    : {winner}  "
            f"(q={wa['quality']:.4f} $={wa['cost_dollar']:.4f} t={wa['wall_clock_sec']:.1f}s)"
        )

    try:
        for m, axes in scored:
            ledger.append(signature=sig, model=m, scores=axes, ts=ts)
        frontier_path = ledger.export_frontier()
    except OSError as exc:
        print(f"could not persist ledger: {type(exc).__name__}")
        if args.json:
            payload: dict[str, Any] = {
                "signature": sig,
                "mode": mode,
                "winner": winner,
                "axes": dict(winner_rec.scores) if winner_rec else None,
                "next_best": None,
                "frontier": None,
            }
            print(json.dumps(payload))
        return 1

    nxt = ledger.best_model(sig, objective, max_cost)
    print(f"learned   : next '{sig}' will prefer -> {nxt}")
    print(f"frontier   : {frontier_path}")
    if args.json:
        payload = {
            "signature": sig,
            "mode": mode,
            "winner": winner,
            "axes": dict(winner_rec.scores) if winner_rec else None,
            "next_best": nxt,
            "frontier": str(frontier_path),
        }
        print(json.dumps(payload))
    return 0


def register_run_parser(subs: argparse._SubParsersAction) -> None:
    p = subs.add_parser(
        "run",
        help="allocate a task across the model pool, gate it, and learn a seed (v3 MVP #2)",
    )
    p.add_argument("task", help="the task to run")
    p.add_argument(
        "--policy",
        default=".agentdex/orchestration.yaml",
        help="orchestration policy from `adx interview`",
    )
    p.add_argument(
        "--ledger",
        default=".agentdex/seeds.jsonl",
        help=(
            "append-only seed ledger (the learned allocation); "
            "frontier.json is written next to the ledger; give each ledger its own directory"
        ),
    )
    p.add_argument(
        "--engine",
        default="fake",
        choices=["fake", "bridges"],
        help="fake = deterministic, no spend; bridges = real (add-back)",
    )
    p.add_argument("--fanout", type=int, default=4, help="max candidates on a cold start")
    p.add_argument("--seed", type=int, default=None, help="RNG seed (deterministic explore)")
    p.add_argument("--json", action="store_true", help="also emit a one-line JSON summary")
    p.set_defaults(func=cmd_run)
