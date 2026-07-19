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
objectives, so learning is observable. ``--engine bridges`` dispatches live
through the local TeamClaude gateway (Anthropic ``/v1/messages`` on loopback
only — never remote, never credentials). Quality stays neutral 0.5 until the
policy gate is wired; ranking falls through to cost/latency.

bridges dispatches pool names as model ids through the loopback TeamClaude
gateway; it does NOT yet consult openbox.yaml backend bindings — openbox check
only declares reachability. Per-backend base_url routing is tracked in issue #706.

stdlib + PyYAML + ``adx_frontier`` (+ urllib for bridges). No model is called
in fake mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from adx_frontier import selection
from adx_frontier.candidate import FRONTIER_AXES
from adx_frontier.ledger import FrontierLedger, FrontierRecord, TrustReceipt


# --------------------------------------------------------------------------- #
# policy + signature
# --------------------------------------------------------------------------- #
def _yaml_loc(exc: yaml.YAMLError) -> str:
    """Return `` (line N, column M)`` from a YAMLError mark — never str(exc)."""
    mark = getattr(exc, "problem_mark", None)
    if mark is None:
        return ""
    return f" (line {mark.line + 1}, column {mark.column + 1})"


def load_policy(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"no orchestration policy at {path} — run `adx interview` first")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(
            f"invalid YAML in policy at {path}{_yaml_loc(exc)} — fix the file"
        ) from None
    if not isinstance(doc, dict):
        raise ValueError(f"policy at {path} must be a YAML mapping")
    return doc


def _policy_list(value: Any) -> list[str]:
    """Accept a YAML sequence or a comma-separated scalar; return list[str].

    Non-iterable scalars (bool/int/float/dict) raise ``ValueError`` so callers
    can map them to a clean rc-2 without a TypeError traceback.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    raise ValueError("policy field must be a list or comma-separated string")


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
    """Parse frontier axes; None on missing / bool / non-finite / out-of-range."""
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
            if axis == "quality" and not (0.0 <= parsed <= 1.0):
                return None
            if axis in ("cost_dollar", "wall_clock_sec") and parsed < 0.0:
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

    def append(
        self,
        *,
        signature: str,
        model: str,
        scores: dict[str, float],
        ts: str,
        receipt_kind: str = "adx-run-fake",
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row: dict[str, Any] = {
            "signature": signature,
            "model": model,
            "scores": scores,
            "ts": ts,
            "receipt_kind": receipt_kind,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

    @property
    def attempts_path(self) -> Path:
        """Sidecar holding per-signature cold-start attempt counts."""
        return self.path.parent / "attempts.json"

    def bump_attempt(self, sig: str) -> int:
        """Return this signature's prior cold-start count, then persist +1.

        Rotation MUST advance on attempts, not on appended rows: a round where
        every candidate fails dispatch or is pruned by the budget writes zero
        rows, so a row-derived offset would replay the same dead prefix forever
        — the counter would be advanced by exactly the thing whose failure it
        exists to route around. Kept per-signature because a global counter
        aliases mod len(pool) when two signatures interleave, starving each of
        a disjoint slice.
        """
        counts: dict[str, Any] = {}
        if self.attempts_path.exists():
            try:
                loaded = json.loads(self.attempts_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    counts = loaded
            except (json.JSONDecodeError, OSError):
                counts = {}  # corrupt sidecar is advisory only — never fatal
        raw = counts.get(sig)
        prior = raw if isinstance(raw, int) and raw >= 0 else 0
        counts[sig] = prior + 1
        try:
            self.attempts_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.attempts_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(counts), encoding="utf-8")
            os.replace(tmp, self.attempts_path)
        except OSError:
            pass  # rotation is an optimisation; never block a run on it
        return prior

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
        kind = str(row.get("receipt_kind") or "adx-run-fake")
        return FrontierRecord(
            candidate=str(row["model"]),
            ladder_id=f"job:{sig}",
            base_model="adx-pool",
            scores=scores,
            budget_usd=self.max_cost if self.max_cost else 1.0,
            budget_wall_clock_min=10.0,
            receipt=TrustReceipt(
                tier="self_reported",
                kind=kind,
                artifacts=(f"seeds:{self.path}",),
            ),
            measured_at_utc=ts,
        )

    def _measured_rows(self, sig: str) -> tuple[list[dict[str, Any]], bool]:
        """Rows for ``sig``, provenance-partitioned. Returns (rows, mixed).

        SIMULATED AND MEASURED MUST NEVER AVERAGE. ``--engine fake`` derives
        quality from a hash uniform on [0,1] while the live path pins 0.5, so
        pooling them lets roughly half of all synthetic rows structurally
        outrank EVERY real measurement under a quality-first objective — and
        ``fake`` is the default engine, so a first run poisons the ledger that
        drives real allocation. Measured rows win outright when any exist; the
        caller is told when a mix was present so it can say so.
        """
        rows = [r for r in self._rows() if r.get("signature") == sig and "model" in r]
        measured = [r for r in rows if not str(r.get("receipt_kind", "")).endswith("-fake")]
        if measured and len(measured) != len(rows):
            return measured, True
        return (measured or rows), False

    def records(self, sig: str) -> list[FrontierRecord]:
        """Parse rows for ``sig`` into ``FrontierRecord``s (skip corrupt lines)."""
        out: list[FrontierRecord] = []
        for row in self._measured_rows(sig)[0]:
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
        for row in self._measured_rows(sig)[0]:
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

    def degenerate_primary_axis(self, sig: str, objective: list[str]) -> str | None:
        """Name the primary axis when every candidate ties on it, else None.

        A constant primary axis is NOT a tiebreak situation — it silently
        changes what is being optimised. With ``quality`` pinned (as the live
        bridges path does until the policy gate is wired), the decision falls
        through to cost and wall-clock, which are BOTH monotone in output
        tokens: the candidate that produces the least output then strictly
        dominates the one that did the work, making a refusal or a truncated
        reply the global optimum. Callers surface this rather than ranking
        quietly.
        """
        recs = self.mean_records(sig)
        if len(recs) < 2:
            return None
        axis = selection.objective_axes(objective)[0]
        values = {r.scores.get(axis) for r in recs}
        return axis if len(values) == 1 else None

    def best_model(self, sig: str, objective: list[str], max_cost: float | None) -> str | None:
        """Winner under constrained-Pareto objective order over mean records."""
        survivors = selection.select(self.mean_records(sig), objective, max_cost_dollar=max_cost)
        return survivors[0].candidate if survivors else None

    def export_frontier(self, path: Path | None = None) -> Path:
        """Build a ``FrontierLedger`` from all raw rows and export ``frontier.json``.

        When ``self.max_cost`` is set, a row is excluded if its own
        ``cost_dollar`` exceeds the ceiling OR if its (signature, model) MEAN
        cost does. Both filters are needed: the allocator judges eligibility on
        mean-per-model records (``best_model`` -> ``mean_records``), so
        filtering raw rows alone still let a model whose mean is over budget be
        advertised on the strength of one cheap run — exactly the "frontier
        advertises what the allocator rejects" case, reproducible on the
        bridges path where per-run cost varies.
        """
        target = path if path is not None else self.path.parent / "frontier.json"
        ledger = FrontierLedger()
        over_budget_models: set[tuple[str, str]] = set()
        if self.max_cost is not None:
            sums: dict[tuple[str, str], list[float]] = {}
            for row in self._rows():
                if "model" not in row or "signature" not in row:
                    continue
                raw = row.get("scores")
                if not isinstance(raw, dict):
                    continue
                parsed = _parse_axes(raw)
                if parsed is None:
                    continue
                sums.setdefault((str(row["signature"]), str(row["model"])), []).append(
                    parsed["cost_dollar"]
                )
            over_budget_models = {
                k for k, costs in sums.items() if sum(costs) / len(costs) > self.max_cost
            }
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
            if self.max_cost is not None and scores["cost_dollar"] > self.max_cost:
                continue
            if (str(row["signature"]), str(row["model"])) in over_budget_models:
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
# engine — fake + bridges (loopback TeamClaude gateway)
# --------------------------------------------------------------------------- #

# Per-1M USD (input, output) for the interview default pool. Unknown models
# fall through to adx_bridges.rate_table when importable, else 0.0 → unmetered.
_RATE_TABLE: dict[str, tuple[float, float]] = {
    "claude-opus": (15.0, 75.0),
    "claude-sonnet": (3.0, 15.0),
    "codex-gpt-5.6": (2.50, 10.00),
    "deepseek": (0.27, 1.10),
    "sakana-fugu": (1.0, 5.0),
}

_DEFAULT_BRIDGES_BASE = "http://127.0.0.1:3456"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


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


def _bridges_base_url() -> str:
    return os.environ.get("ADX_BRIDGES_BASE_URL", _DEFAULT_BRIDGES_BASE).rstrip("/")


def require_loopback_base_url(base_url: str) -> None:
    """Refuse any non-loopback host — bridges must never talk to a remote."""
    host = (urlparse(base_url).hostname or "").lower()
    if host not in _LOOPBACK_HOSTS:
        raise ValueError(
            f"bridges engine refuses non-loopback host {host!r} — "
            "ADX_BRIDGES_BASE_URL must be http://127.0.0.1:… or localhost"
        )


def _cost_dollar_and_kind(model: str, tokens_in: int, tokens_out: int) -> tuple[float, str]:
    """Return (cost_dollar, receipt_kind). Unmetered when rates are fallback-0."""
    if model in _RATE_TABLE:
        in_rate, out_rate = _RATE_TABLE[model]
        if in_rate == 0.0 and out_rate == 0.0:
            return 0.0, "adx-run-bridges-unmetered"
        cost = round((tokens_in * in_rate + tokens_out * out_rate) / 1_000_000.0, 6)
        return max(cost, 0.0), "adx-run-bridges"
    try:
        from adx_bridges.rate_table import estimate_cost_usd

        estimated = estimate_cost_usd(model, tokens_in, tokens_out)
        if estimated is not None:
            return float(estimated), "adx-run-bridges"
    except ImportError:
        pass
    return 0.0, "adx-run-bridges-unmetered"


def estimate_pre_dispatch_cost(model: str, task: str, max_tokens: int) -> float | None:
    """Conservative PRE-dispatch cost estimate for the live bridges budget guard.

    Uses the same ``_RATE_TABLE`` the engine meters with:
    ``est = (est_input/1e6)*rate_in + (max_tokens/1e6)*rate_out`` where
    ``est_input = len(task)//3 + 200``. Returns ``None`` when the model is
    unmetered / unknown so the guard does not invent a ceiling.
    """
    est_input = len(task) // 3 + 200
    if model in _RATE_TABLE:
        rate_in, rate_out = _RATE_TABLE[model]
        if rate_in == 0.0 and rate_out == 0.0:
            return None
        return (est_input / 1_000_000.0) * rate_in + (max_tokens / 1_000_000.0) * rate_out
    try:
        from adx_bridges.rate_table import estimate_cost_usd

        estimated = estimate_cost_usd(model, est_input, max_tokens)
        if estimated is not None and float(estimated) > 0.0:
            return float(estimated)
    except ImportError:
        pass
    return None


def _extract_message_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in payload.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "".join(parts)


def _sanitize_model_filename(model: str) -> str:
    return model.replace("/", "-").replace(" ", "-")


def _post_messages(
    base_url: str,
    *,
    model: str,
    task: str,
    max_tokens: int,
    timeout: float,
) -> dict[str, Any]:
    """POST Anthropic-wire ``/v1/messages``; no credentials. Raises on failure."""
    url = f"{base_url.rstrip('/')}/v1/messages"
    body = json.dumps(
        {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": task}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


# --------------------------------------------------------------------------- #
# allocation
# --------------------------------------------------------------------------- #
def allocate(
    pool: list[str],
    best: str | None,
    explore_rate: float,
    rng: random.Random,
    fanout: int,
    rotation: int = 0,
) -> tuple[list[str], str]:
    """Return (models_to_dispatch, mode). Pure — incumbent ``best`` is injected.

    - cold start (``best`` is None or not in pool): fan out across up to
      ``fanout`` of the pool, starting at ``rotation % len(pool)`` so repeated
      cold-starts cover later pool entries instead of the same prefix forever.
    - warm: with prob ``explore_rate``, add one non-incumbent explorer;
      otherwise exploit the known best alone.
    """
    if best is None or best not in pool:
        if not pool:
            return [], "cold-start-fanout"
        n = min(max(1, fanout), len(pool))
        offset = rotation % len(pool)
        return [pool[(offset + i) % len(pool)] for i in range(n)], "cold-start-fanout"
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
    *,
    receipt_kind: str = "adx-run-fake",
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
            kind=receipt_kind,
            artifacts=(f"seeds:{ledger_path}",),
        ),
        measured_at_utc=ts,
    )


def _dispatch_bridges(
    models: list[str],
    *,
    task: str,
    max_tokens: int,
    timeout: float,
    base_url: str,
) -> list[dict[str, Any]]:
    """Live-dispatch each model; skip failures with a one-line type-only note."""
    results: list[dict[str, Any]] = []
    for model in models:
        try:
            t0 = time.perf_counter()
            payload = _post_messages(
                base_url,
                model=model,
                task=task,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            elapsed = round(time.perf_counter() - t0, 1)
            usage = payload.get("usage") if isinstance(payload, dict) else None
            if not isinstance(usage, dict):
                usage = {}
            tokens_in = int(usage.get("input_tokens") or 0)
            tokens_out = int(usage.get("output_tokens") or 0)
            cost, kind = _cost_dollar_and_kind(model, tokens_in, tokens_out)
            text = _extract_message_text(payload) if isinstance(payload, dict) else ""
            results.append(
                {
                    "model": model,
                    "scores": {
                        "quality": 0.5,
                        "cost_dollar": cost,
                        "wall_clock_sec": elapsed,
                    },
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "text": text,
                    "receipt_kind": kind,
                }
            )
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            # Type name only — never echo response/request bodies.
            print(f"  FAILED {model}: {type(exc).__name__}")
    return results


# --------------------------------------------------------------------------- #
# command
# --------------------------------------------------------------------------- #
def cmd_run(args: argparse.Namespace) -> int:
    try:
        policy = load_policy(Path(args.policy).expanduser())
        pool = _policy_list(policy.get("pool"))
        job_types = _policy_list(policy.get("job_types"))
        objective = _policy_list(policy.get("objective"))
        # Validate objective tokens early (case-insensitive map; reject unknown).
        selection.objective_axes(objective)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        return 2
    if not pool:
        print("policy has an empty pool — run `adx interview` to set one")
        return 2
    max_cost = max_cost_from_constraints(str(policy.get("constraints", "")))
    ledger = FrontierSeedLedger(Path(args.ledger).expanduser(), max_cost=max_cost)
    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    sig = signature(args.task, job_types)

    engine = getattr(args, "engine", "fake")
    max_tokens = int(getattr(args, "max_tokens", 2000))

    # Budget-prune the POOL before allocation, not the dispatch slice after it.
    # Pruning the slice lets an unaffordable prefix consume the whole fanout and
    # report no_feasible_candidate while an affordable pool member is never
    # considered — a false claim that nothing fits the budget.
    if engine == "bridges" and max_cost is not None:
        affordable: list[str] = []
        for model in pool:
            est = estimate_pre_dispatch_cost(model, args.task, max_tokens)
            if est is not None and est > max_cost:
                print(
                    f"skipped {model}: est cost ${est:.6f} > ceiling ${max_cost} — not dispatched"
                )
            else:
                affordable.append(model)
        if not affordable:
            print("no_feasible_candidate")
            return 3
        pool = affordable

    best = ledger.best_model(sig, objective, max_cost)
    models, mode = allocate(
        pool,
        best,
        _explore_rate(policy),
        rng,
        args.fanout,
        # Step by `fanout` so consecutive cold-starts tile the pool instead of
        # sliding by one and re-dispatching models that just failed.
        rotation=(
            ledger.bump_attempt(sig) * max(1, args.fanout)
            if (best is None or best not in pool)
            else 0
        ),
    )
    dispatch_timeout = float(getattr(args, "dispatch_timeout", 180.0))
    save_outputs = getattr(args, "save_outputs", None)

    ts = datetime.now(UTC).replace(microsecond=0).isoformat()
    candidates: list[dict[str, Any]] = []
    scored: list[tuple[str, dict[str, float]]] = []
    receipt_by_model: dict[str, str] = {}

    if engine == "bridges":
        base_url = _bridges_base_url()
        try:
            require_loopback_base_url(base_url)
        except ValueError as exc:
            print(str(exc))
            return 2
        # PRE-dispatch budget guard: skip candidates whose rate-table expected
        # cost for --max-tokens output + a modest input estimate exceeds max_cost
        # so `max $/task` is a real hard budget for live runs (no spend).
        if max_cost is not None:
            kept: list[str] = []
            for model in models:
                est = estimate_pre_dispatch_cost(model, args.task, max_tokens)
                if est is not None and est > max_cost:
                    print(
                        f"skipped {model}: est cost ${est:.6f} > ceiling ${max_cost} "
                        "— not dispatched"
                    )
                else:
                    kept.append(model)
            models = kept
            if not models:
                print("no_feasible_candidate")
                return 3
        dispatched = _dispatch_bridges(
            models,
            task=args.task,
            max_tokens=max_tokens,
            timeout=dispatch_timeout,
            base_url=base_url,
        )
        if not dispatched:
            print("all bridge candidates failed — nothing appended")
            return 1
        print("quality     : neutral 0.5 (gate not wired for bridges yet — rank by cost/latency)")
        save_dir = Path(save_outputs).expanduser() if save_outputs else None
        if save_dir is not None:
            save_dir.mkdir(parents=True, exist_ok=True)
        for item in dispatched:
            model = str(item["model"])
            axes = item["scores"]
            scored.append((model, axes))
            receipt_by_model[model] = str(item["receipt_kind"])
            out_file: str | None = None
            if save_dir is not None:
                out_path = save_dir / f"{_sanitize_model_filename(model)}.md"
                out_path.write_text(str(item.get("text") or ""), encoding="utf-8")
                out_file = str(out_path)
                print(f"saved     : {out_path}")
            candidates.append(
                {
                    "model": model,
                    "quality": axes["quality"],
                    "cost_dollar": axes["cost_dollar"],
                    "wall_clock_sec": axes["wall_clock_sec"],
                    "tokens_in": item["tokens_in"],
                    "tokens_out": item["tokens_out"],
                    "output_file": out_file,
                }
            )
    elif engine == "fake":
        for m in models:
            axes = fake_axes(m, sig, args.task)
            scored.append((m, axes))
            receipt_by_model[m] = "adx-run-fake"
            candidates.append(
                {
                    "model": m,
                    "quality": axes["quality"],
                    "cost_dollar": axes["cost_dollar"],
                    "wall_clock_sec": axes["wall_clock_sec"],
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "output_file": None,
                }
            )
    else:
        print(f"engine '{engine}' not wired yet — use --engine fake or --engine bridges")
        return 2

    run_records = [
        _run_record(
            m,
            sig,
            axes,
            ts,
            ledger.path,
            max_cost,
            receipt_kind=receipt_by_model.get(m, "adx-run-fake"),
        )
        for m, axes in scored
    ]
    survivors = selection.select(run_records, objective, max_cost_dollar=max_cost)
    winner_rec = survivors[0] if survivors else None
    winner = winner_rec.candidate if winner_rec else None

    obj_display = " > ".join(objective) if objective else " > ".join(FRONTIER_AXES)
    print(f"task      : {args.task}")
    print(f"signature : {sig}")
    print(f"allocation: {mode}  ({len(models)} candidate(s))")
    print(f"objective  : {obj_display}")
    tok_by_model = {c["model"]: c for c in candidates}
    for m, axes in scored:
        flag = "  <- winner" if m == winner else ""
        tok = tok_by_model.get(m) or {}
        tok_part = ""
        if engine == "bridges":
            tok_part = f" tok={tok.get('tokens_in', 0)}/{tok.get('tokens_out', 0)}"
        print(
            f"  q={axes['quality']:.4f} $={axes['cost_dollar']:.4f} "
            f"t={axes['wall_clock_sec']:.1f}s{tok_part}  {m}{flag}"
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
            ledger.append(
                signature=sig,
                model=m,
                scores=axes,
                ts=ts,
                receipt_kind=receipt_by_model.get(m, "adx-run-fake"),
            )
        frontier_path = ledger.export_frontier()
    except OSError as exc:
        print(f"could not persist ledger: {type(exc).__name__}")
        if args.json:
            payload: dict[str, Any] = {
                "engine": engine,
                "signature": sig,
                "mode": mode,
                "winner": winner,
                "axes": dict(winner_rec.scores) if winner_rec else None,
                "next_best": None,
                "frontier": None,
                "candidates": candidates,
            }
            print(json.dumps(payload))
        return 1

    nxt = ledger.best_model(sig, objective, max_cost)
    degenerate = ledger.degenerate_primary_axis(sig, objective)
    if engine == "fake":
        print("provenance: SIMULATED — deterministic hash, no model was called")
    if degenerate is not None:
        print(
            f"WARNING   : every candidate ties on '{degenerate}' — the objective's "
            "primary axis carries no signal, so this ranking fell through to "
            "cost/latency, which both favour the SHORTEST reply. Treat "
            f"'{nxt}' as unvalidated (see issue #708)."
        )
    print(f"learned   : next '{sig}' will prefer -> {nxt}")
    print(f"frontier   : {frontier_path}")
    if args.json:
        payload = {
            "engine": engine,
            "provenance": "simulated" if engine == "fake" else "measured",
            "signature": sig,
            "mode": mode,
            "winner": winner,
            "axes": dict(winner_rec.scores) if winner_rec else None,
            "next_best": nxt,
            "degenerate_primary_axis": degenerate,
            "frontier": str(frontier_path),
            "candidates": candidates,
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
        help=(
            "fake = deterministic, no spend; bridges = live loopback TeamClaude gateway "
            "(dispatches pool names as model ids; does NOT yet consult openbox.yaml "
            "backend bindings — openbox check only declares reachability; per-backend "
            "base_url routing is tracked in issue #706)"
        ),
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=2000,
        dest="max_tokens",
        help="per-model output token cap for bridges dispatch (cost ceiling)",
    )
    p.add_argument(
        "--dispatch-timeout",
        type=float,
        default=180.0,
        dest="dispatch_timeout",
        help="per-model HTTP timeout seconds for bridges dispatch",
    )
    p.add_argument(
        "--save-outputs",
        default=None,
        dest="save_outputs",
        help="directory to write each model's answer as <model>.md (bridges)",
    )
    p.add_argument("--fanout", type=int, default=4, help="max candidates on a cold start")
    p.add_argument("--seed", type=int, default=None, help="RNG seed (deterministic explore)")
    p.add_argument("--json", action="store_true", help="also emit a one-line JSON summary")
    p.set_defaults(func=cmd_run)
