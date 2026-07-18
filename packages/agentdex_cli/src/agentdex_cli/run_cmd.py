"""``adx run`` — the agentdex allocation loop (v3 MVP #2).

The whole thesis in one command:

    know which model does a job better  →  get the job done  →  learn a seed

Flow per invocation:
    1. classify the task into a *signature* (per the interview policy's job_types)
    2. consult the seed ledger — which model has won this signature before?
    3. allocate: exploit the known best, or explore an alternative (bandit rate)
    4. dispatch to the chosen model(s), gate each result to a score
    5. pick the winner, emit a SEED {signature, model, score} to the ledger
       → the next run of that signature routes smarter.

Engines
-------
``--engine fake`` (default) scores each (model, signature) deterministically from
a hash, so the loop is fully demonstrable with no network, no secrets, no spend —
mirroring ``adx measure``'s fake-engine convention. Different models win different
signatures, so learning is observable. ``--engine bridges`` (later add-back) will
dispatch through ``adx_bridges`` over the TeamClaude substrate and run the policy's
real ``gate`` command.

stdlib + PyYAML only. No model is called in fake mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


# --------------------------------------------------------------------------- #
# policy + signature
# --------------------------------------------------------------------------- #
def load_policy(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"no orchestration policy at {path} — run `adx interview` first")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


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


# --------------------------------------------------------------------------- #
# ledger — append-only seeds; the learned allocation lives here
# --------------------------------------------------------------------------- #
@dataclass
class Seed:
    signature: str
    model: str
    score: float
    ts: str

    def to_json(self) -> str:
        return json.dumps(
            {"signature": self.signature, "model": self.model, "score": self.score, "ts": self.ts}
        )


class Ledger:
    """Append-only JSONL seed store. Best-known model = highest mean score."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, seed: Seed) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(seed.to_json() + "\n")

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def mean_scores(self, sig: str) -> dict[str, float]:
        agg: dict[str, list[float]] = {}
        for r in self._rows():
            if r.get("signature") == sig and "model" in r and "score" in r:
                agg.setdefault(r["model"], []).append(float(r["score"]))
        return {m: sum(v) / len(v) for m, v in agg.items()}

    def best_model(self, sig: str) -> str | None:
        scores = self.mean_scores(sig)
        return max(scores, key=scores.__getitem__) if scores else None


# --------------------------------------------------------------------------- #
# engine — fake now, bridges later
# --------------------------------------------------------------------------- #
def fake_score(model: str, sig: str, task: str) -> float:
    """Deterministic pseudo-quality in [0,1) for (model, signature).

    Keyed on model+signature so a model is consistently good/bad at a job-type
    (that is what makes learning meaningful); task is folded in for per-run
    variation so repeated runs are not byte-identical.
    """
    h = hashlib.sha256(f"{model}\x00{sig}".encode()).digest()
    base = int.from_bytes(h[:4], "big") / 0xFFFFFFFF
    jitter = int.from_bytes(hashlib.sha256(task.encode()).digest()[:2], "big") / 0xFFFF
    return round(0.85 * base + 0.15 * jitter, 4)


# --------------------------------------------------------------------------- #
# allocation
# --------------------------------------------------------------------------- #
def allocate(
    pool: list[str], sig: str, ledger: Ledger, explore_rate: float, rng: random.Random, fanout: int
) -> tuple[list[str], str]:
    """Return (models_to_dispatch, mode).

    - cold start (no seeds for sig): fan out across up to `fanout` of the pool.
    - warm: with prob explore_rate, add one non-incumbent explorer; otherwise
      exploit the known best alone.
    """
    best = ledger.best_model(sig)
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


# --------------------------------------------------------------------------- #
# command
# --------------------------------------------------------------------------- #
def cmd_run(args: argparse.Namespace) -> int:
    policy = load_policy(Path(args.policy).expanduser())
    pool = [str(m) for m in (policy.get("pool") or [])]
    if not pool:
        print("policy has an empty pool — run `adx interview` to set one")
        return 2
    job_types = [str(j) for j in (policy.get("job_types") or [])]
    ledger = Ledger(Path(args.ledger).expanduser())
    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    sig = signature(args.task, job_types)
    models, mode = allocate(pool, sig, ledger, _explore_rate(policy), rng, args.fanout)

    if args.engine != "fake":
        print(f"engine '{args.engine}' not wired yet — use --engine fake (bridges is the add-back)")
        return 2

    results = [(m, fake_score(m, sig, args.task)) for m in models]
    results.sort(key=lambda mv: mv[1], reverse=True)
    winner, win_score = results[0]

    ts = datetime.now(UTC).replace(microsecond=0).isoformat()
    for m, sc in results:
        ledger.append(Seed(signature=sig, model=m, score=sc, ts=ts))

    print(f"task      : {args.task}")
    print(f"signature : {sig}")
    print(f"allocation: {mode}  ({len(models)} candidate(s))")
    for m, sc in results:
        flag = "  <- winner" if m == winner else ""
        print(f"  {sc:.4f}  {m}{flag}")
    print(f"winner    : {winner}  (score {win_score:.4f})")
    nxt = ledger.best_model(sig)
    print(f"learned   : next '{sig}' will prefer -> {nxt}")
    if args.json:
        print(
            json.dumps(
                {
                    "signature": sig,
                    "mode": mode,
                    "winner": winner,
                    "score": win_score,
                    "next_best": nxt,
                }
            )
        )
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
        help="append-only seed ledger (the learned allocation)",
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
