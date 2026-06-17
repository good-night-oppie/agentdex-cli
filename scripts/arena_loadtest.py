#!/usr/bin/env python3
"""arena_loadtest.py — measure the per-sidecar concurrency ceiling for ADR-0012.

Drives N concurrent sandbox battles against an arena (default: a dedicated test
instance you spin with a raised ADX_SIDECAR_MAX_BATTLES + heap) using the
reference client `arena_play.Arena`, ramps N, and at each level reports:

  - sidecar RSS (MB)            -> the memory ceiling (ADR-0012 must-measure #1)
  - p50 / p95 choose latency    -> turn-resolution headroom under load
  - 503 "at capacity" rate      -> where admission control kicks in
  - battles completed / errored

This isolates the SIM tier. It does NOT measure the LLM-decision fan-out (the
client picks move #1, no model call) — that is a separate probe against the
platform /chat/completions proxy. See ADR-0012 "must-measure".

Usage:
  # against an existing arena (caps at its own MAX_BATTLES):
  uv run python scripts/arena_loadtest.py --base http://127.0.0.1:8889 --levels 1,2,4

  # spin a dedicated high-cap test arena first (recommended for the ceiling):
  ADX_SIDECAR_MAX_BATTLES=64 ARENA_ADMIN_TOKEN_HASH=$(printf x|sha256sum|cut -d' ' -f1) \
  ARENA_OWNER_INBOX_DIR=/tmp/arena-loadtest-inbox \
    HOST=127.0.0.1 PORT=8890 uv run python -m agentdex_arena &
  uv run python scripts/arena_loadtest.py --base http://127.0.0.1:8890 \
    --inbox /tmp/arena-loadtest-inbox --levels 1,2,4,8,16,32 --sidecar-pid auto
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path

# arena_play lives in packages/agentdex_arena/ (not importable as a module) — add it.
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "packages" / "agentdex_arena"))


def _sidecar_rss_mb(pid: int | None) -> float | None:
    """RSS of the node sidecar process via /proc (MB). None if unknown."""
    if not pid:
        return None
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 1)  # kB -> MB
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None
    return None


def _auto_sidecar_pid() -> int | None:
    """Find the node sidecar.mjs pid (best-effort)."""
    try:
        import subprocess

        out = subprocess.run(
            ["pgrep", "-f", "sidecar.mjs"], capture_output=True, text=True
        ).stdout.split()
        return int(out[0]) if out else None
    except Exception:
        return None


class _Worker(threading.Thread):
    """One sustained battle loop: enroll once, then begin->choose to terminal, repeat."""

    def __init__(self, base: str, idx: int, stop_at: float, turns: int, nonce: str = ""):
        super().__init__(daemon=True)
        self.base, self.idx, self.stop_at, self.turns = base, idx, stop_at, turns
        self.nonce = nonce
        self.latencies: list[float] = []
        self.cap_503 = 0
        self.errors = 0
        self.battles = 0

    def run(self) -> None:
        from arena_play import Arena  # noqa: PLC0415

        try:
            tag = f"{self.nonce}{self.idx}"
            a = Arena(owner=f"loadtest-{tag}@example.com", name=f"LoadBot{tag}")
            a.enroll()
        except Exception:
            self.errors += 1
            return
        while time.monotonic() < self.stop_at:
            try:
                st = a.begin(lane="sandbox")
            except Exception as e:
                if "503" in str(e) or "capacity" in str(e).lower():
                    self.cap_503 += 1
                    time.sleep(0.5)
                else:
                    self.errors += 1
                continue
            n = 0
            while st.get("status") == "your_move" and n < self.turns:
                t0 = time.monotonic()
                try:
                    st = a.choose(1)
                except Exception:
                    self.errors += 1
                    break
                self.latencies.append((time.monotonic() - t0) * 1000)  # ms
                n += 1
            self.battles += 1


def run_level(base: str, n: int, window_s: float, turns: int, pid: int | None) -> dict:
    stop_at = time.monotonic() + window_s
    # unique owner/name per (run, level) so re-enroll never collides with a
    # previously-registered name (registered names persist) and each worker's
    # battles never inherit a prior worker's "active battle" 503 race.
    nonce = f"{int(time.time())}l{n}-"
    workers = [_Worker(base, i, stop_at, turns, nonce=nonce) for i in range(n)]
    for w in workers:
        w.start()
    # sample RSS across the window
    rss_samples: list[float] = []
    while time.monotonic() < stop_at:
        r = _sidecar_rss_mb(pid)
        if r is not None:
            rss_samples.append(r)
        time.sleep(1.0)
    for w in workers:
        w.join(timeout=30)
    lat = [x for w in workers for x in w.latencies]
    lat.sort()
    return {
        "concurrency": n,
        "rss_mb_peak": max(rss_samples) if rss_samples else None,
        "rss_mb_mean": round(statistics.mean(rss_samples), 1) if rss_samples else None,
        "choose_p50_ms": round(statistics.median(lat), 1) if lat else None,
        "choose_p95_ms": round(lat[int(len(lat) * 0.95)], 1) if len(lat) >= 20 else None,
        "choices": len(lat),
        "battles": sum(w.battles for w in workers),
        "cap_503": sum(w.cap_503 for w in workers),
        "errors": sum(w.errors for w in workers),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:8889")
    ap.add_argument("--inbox", default=None, help="ARENA_OWNER_INBOX_DIR the target arena writes to")
    ap.add_argument("--levels", default="1,2,4,8", help="comma-sep concurrency ramp")
    ap.add_argument("--window", type=float, default=20.0, help="seconds to sustain each level")
    ap.add_argument("--turns", type=int, default=12, help="max choices per battle")
    ap.add_argument("--sidecar-pid", default="auto", help="node sidecar pid, or 'auto'")
    args = ap.parse_args()

    os.environ["ARENA_BASE"] = args.base
    if args.inbox:
        os.environ["ARENA_OWNER_INBOX_DIR"] = args.inbox
    pid = _auto_sidecar_pid() if args.sidecar_pid == "auto" else int(args.sidecar_pid)
    levels = [int(x) for x in args.levels.split(",")]

    print(f"# arena load-test  base={args.base}  sidecar_pid={pid}  window={args.window}s")
    print(f"{'N':>4} {'rss_peak':>9} {'rss_mean':>9} {'p50_ms':>8} {'p95_ms':>8} "
          f"{'battles':>8} {'choices':>8} {'503':>5} {'err':>5}")
    results = []
    for n in levels:
        r = run_level(args.base, n, args.window, args.turns, pid)
        results.append(r)
        print(f"{r['concurrency']:>4} {str(r['rss_mb_peak']):>9} {str(r['rss_mb_mean']):>9} "
              f"{str(r['choose_p50_ms']):>8} {str(r['choose_p95_ms']):>8} "
              f"{r['battles']:>8} {r['choices']:>8} {r['cap_503']:>5} {r['errors']:>5}")
    print("DONE_JSON " + json.dumps({"base": args.base, "sidecar_pid": pid, "levels": results}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
