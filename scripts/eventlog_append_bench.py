#!/usr/bin/env python3
"""Measure EventLog NDJSON append throughput for ADR-0012 must-measure #2.

The current durable arena log is a hash-chained JSONL file protected by one
fcntl lock. This probe measures the existing file-backed implementation before
deciding whether SQLite-WAL or Postgres-direct is necessary for the arena scale
target.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "packages" / "agentdex_engine" / "src"))

from agentdex_engine.modules.arena.events import EventLog  # noqa: E402

DEFAULT_LEVELS = "1,2,4,8,16,32,64,100"
DEFAULT_MODES = "append,append_many:3"


@dataclass(frozen=True)
class ModeSpec:
    name: str
    group_size: int


@dataclass(frozen=True)
class WorkerResult:
    rows: int
    latencies_ms: list[float]
    errors: list[str]


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * pct)))
    return round(ordered[idx], 3)


def _parse_levels(raw: str) -> list[int]:
    levels = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not levels or any(level < 1 for level in levels):
        raise argparse.ArgumentTypeError("levels must be comma-separated positive integers")
    return levels


def _parse_modes(raw: str) -> list[ModeSpec]:
    modes: list[ModeSpec] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        if token == "append":
            modes.append(ModeSpec(name="append", group_size=1))
            continue
        if token.startswith("append_many:"):
            group_size = int(token.split(":", 1)[1])
            if group_size < 2:
                raise argparse.ArgumentTypeError("append_many group size must be >= 2")
            modes.append(ModeSpec(name=f"append_many:{group_size}", group_size=group_size))
            continue
        raise argparse.ArgumentTypeError(f"unknown mode: {token}")
    if not modes:
        raise argparse.ArgumentTypeError("at least one mode is required")
    return modes


def _payload(worker: int, ordinal: int, payload_bytes: int) -> dict[str, Any]:
    return {
        "tenant_id": "bench",
        "battle_id": f"bench-{worker}-{ordinal // 20}",
        "turn": ordinal,
        "choice": "move 1",
        "pad": "x" * payload_bytes,
    }


def _append_worker(
    log_path: str,
    *,
    worker: int,
    rows: int,
    group_size: int,
    payload_bytes: int,
) -> WorkerResult:
    elog = EventLog(log_path)
    latencies_ms: list[float] = []
    errors: list[str] = []
    written = 0
    ordinal = 0
    while ordinal < rows:
        count = min(group_size, rows - ordinal)
        start = time.monotonic()
        try:
            if group_size == 1:
                elog.append("bench_turn", _payload(worker, ordinal, payload_bytes))
                written += 1
            else:
                items = [
                    ("bench_turn", _payload(worker, ordinal + offset, payload_bytes))
                    for offset in range(count)
                ]
                events = elog.append_many(items)
                written += len(events)
        except Exception as exc:  # noqa: BLE001 - benchmark should report all failures.
            errors.append(f"{type(exc).__name__}: {exc}")
        latencies_ms.append((time.monotonic() - start) * 1000)
        ordinal += count
    return WorkerResult(rows=written, latencies_ms=latencies_ms, errors=errors)


def _preload(log_path: Path, rows: int, payload_bytes: int) -> None:
    elog = EventLog(log_path)
    for ordinal in range(rows):
        elog.append("bench_preload", _payload(-1, ordinal, payload_bytes))


def _row_counts(total_rows: int, workers: int) -> list[int]:
    base = total_rows // workers
    remainder = total_rows % workers
    return [base + (1 if idx < remainder else 0) for idx in range(workers)]


def _run_level(
    *,
    root: Path,
    mode: ModeSpec,
    concurrency: int,
    rows: int,
    payload_bytes: int,
    preload_rows: int,
    executor_kind: str,
) -> dict[str, Any]:
    bench_dir = root / f"{mode.name.replace(':', '-')}-n{concurrency}"
    bench_dir.mkdir(parents=True, exist_ok=True)
    log_path = bench_dir / "events.jsonl"
    if preload_rows:
        _preload(log_path, preload_rows, payload_bytes)

    counts = _row_counts(rows, concurrency)
    start = time.monotonic()
    executor_cls: type[concurrent.futures.Executor]
    executor_cls = (
        concurrent.futures.ProcessPoolExecutor
        if executor_kind == "process"
        else concurrent.futures.ThreadPoolExecutor
    )
    max_workers = concurrency
    with executor_cls(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _append_worker,
                str(log_path),
                worker=worker,
                rows=count,
                group_size=mode.group_size,
                payload_bytes=payload_bytes,
            )
            for worker, count in enumerate(counts)
            if count > 0
        ]
        worker_results = [future.result() for future in concurrent.futures.as_completed(futures)]
    elapsed_s = time.monotonic() - start

    latencies = [lat for result in worker_results for lat in result.latencies_ms]
    errors = [error for result in worker_results for error in result.errors]
    written_rows = sum(result.rows for result in worker_results)
    chain_rows = EventLog(log_path).verify_chain()
    file_bytes = log_path.stat().st_size if log_path.exists() else 0
    return {
        "mode": mode.name,
        "executor": executor_kind,
        "concurrency": concurrency,
        "requested_rows": rows,
        "preload_rows": preload_rows,
        "written_rows": written_rows,
        "elapsed_s": round(elapsed_s, 4),
        "rows_per_s": round(written_rows / elapsed_s, 1) if elapsed_s else None,
        "operations": len(latencies),
        "operation_p50_ms": _percentile(latencies, 0.50),
        "operation_p95_ms": _percentile(latencies, 0.95),
        "operation_mean_ms": round(statistics.mean(latencies), 3) if latencies else None,
        "chain_rows": chain_rows,
        "file_mib": round(file_bytes / (1024 * 1024), 3),
        "errors": errors[:10],
        "error_count": len(errors),
    }


def _print_header() -> None:
    print(
        f"{'mode':>14} {'exec':>7} {'N':>4} {'rows':>7} {'sec':>8} {'rows/s':>10} "
        f"{'op_p50':>9} {'op_p95':>9} {'MiB':>7} {'chain':>7} {'err':>5}"
    )


def _print_row(row: dict[str, Any]) -> None:
    print(
        f"{row['mode']:>14} {row['executor']:>7} {row['concurrency']:>4} "
        f"{row['written_rows']:>7} {row['elapsed_s']:>8} {row['rows_per_s']:>10} "
        f"{row['operation_p50_ms']:>9} {row['operation_p95_ms']:>9} "
        f"{row['file_mib']:>7} {row['chain_rows']:>7} {row['error_count']:>5}"
    )


def _print_table(results: list[dict[str, Any]]) -> None:
    _print_header()
    for row in results:
        _print_row(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", type=_parse_levels, default=_parse_levels(DEFAULT_LEVELS))
    parser.add_argument("--modes", type=_parse_modes, default=_parse_modes(DEFAULT_MODES))
    parser.add_argument("--rows-per-level", type=int, default=1000)
    parser.add_argument("--payload-bytes", type=int, default=512)
    parser.add_argument("--preload-rows", type=int, default=0)
    parser.add_argument("--executor", choices=("process", "thread"), default="process")
    parser.add_argument("--keep-dir", type=Path, default=None)
    args = parser.parse_args()

    if args.rows_per_level < 1:
        parser.error("--rows-per-level must be positive")
    if args.payload_bytes < 0:
        parser.error("--payload-bytes must be >= 0")
    if args.preload_rows < 0:
        parser.error("--preload-rows must be >= 0")

    if args.keep_dir is None:
        temp = tempfile.TemporaryDirectory(prefix="eventlog-append-bench-")
        root = Path(temp.name)
    else:
        temp = None
        root = args.keep_dir
        root.mkdir(parents=True, exist_ok=True)

    try:
        results: list[dict[str, Any]] = []
        _print_header()
        for mode in args.modes:
            for concurrency in args.levels:
                rows = max(args.rows_per_level, concurrency)
                result = _run_level(
                    root=root,
                    mode=mode,
                    concurrency=concurrency,
                    rows=rows,
                    payload_bytes=args.payload_bytes,
                    preload_rows=args.preload_rows,
                    executor_kind=args.executor,
                )
                results.append(result)
                _print_row(result)
        print()
        _print_table(results)
        print(
            "DONE_JSON "
            + json.dumps(
                {
                    "config": {
                        "levels": args.levels,
                        "modes": [asdict(mode) for mode in args.modes],
                        "rows_per_level": args.rows_per_level,
                        "payload_bytes": args.payload_bytes,
                        "preload_rows": args.preload_rows,
                        "executor": args.executor,
                    },
                    "results": results,
                },
                sort_keys=True,
            )
        )
    finally:
        if temp is not None:
            temp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
