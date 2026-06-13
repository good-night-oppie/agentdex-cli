#!/usr/bin/env python
"""Re-simulation audit job: sweeps the event log for rated battles and audits them.

Audits:
- 100% of disputed battles (battles with 'dispute' event)
- 10% random sample of other rated battles (using deterministic blake2b hashing)

Quarantines any battle where the re-simulated winner does not match the reported winner.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

from adx_showdown.protocol import sanitize_name
from adx_showdown.sidecar import Sidecar
from adx_showdown.sim import replay_input_log
from agentdex_engine.modules.arena import EventLog
from agentdex_engine.oracle.battle import _audit_sampled

log = logging.getLogger("agentdex_arena.audit")


async def run_audit(events_path: Path, artifacts_dir: Path, audit_rate: float) -> int:
    if not events_path.is_file():
        log.error("Event log not found: %s", events_path)
        return 1

    elog = EventLog(events_path)

    # Scan events to find battle_end, dispute, and quarantine events
    completed_battles = {}  # battle_id -> {"winner": winner, "hash": input_log_blake2b16}
    disputed_ids = set()
    quarantined_ids = set()

    for event in elog.iter_events():
        etype = event.get("type")
        payload = event.get("payload", {})
        bid = payload.get("battle_id")
        if not bid:
            continue
        if etype == "battle_end":
            if payload.get("lane") == "sandbox" or bid.startswith("sandbox-"):
                continue
            completed_battles[bid] = {
                "winner": payload.get("winner"),
                "hash": payload.get("input_log_blake2b16"),
            }
        elif etype == "dispute":
            disputed_ids.add(bid)
        elif etype == "quarantine":
            quarantined_ids.add(bid)

    # Find battles to audit
    to_audit = []
    for bid, info in completed_battles.items():
        if bid in quarantined_ids:
            continue
        is_disputed = bid in disputed_ids
        is_sampled = _audit_sampled(bid, audit_rate)
        if is_disputed or is_sampled:
            to_audit.append((bid, info, "dispute" if is_disputed else "sampled"))

    if not to_audit:
        log.info("No battles require auditing.")
        return 0

    log.info("Found %d battles to audit.", len(to_audit))

    async with Sidecar() as sidecar:
        mismatches = 0
        for bid, info, reason in to_audit:
            reported_winner = info.get("winner")
            recorded_hash = info.get("hash")
            log.info("Auditing battle %s (%s)...", bid, reason)
            log_file = artifacts_dir / f"{bid}.inputlog.json"
            if not log_file.is_file():
                raise FileNotFoundError(f"Input log file not found for battle {bid}: {log_file}")

            try:
                input_log = json.loads(log_file.read_text(encoding="utf-8"))
            except Exception as e:
                raise ValueError(f"Failed to parse input log for {bid}: {e}") from e

            if recorded_hash:
                actual_hash = hashlib.blake2b(
                    "\n".join(input_log).encode(), digest_size=16
                ).hexdigest()
                if actual_hash != recorded_hash:
                    log.warning(
                        "Input log hash mismatch for battle %s: actual=%r, recorded=%r. Quarantining.",
                        bid,
                        actual_hash,
                        recorded_hash,
                    )
                    elog.append(
                        "quarantine",
                        {
                            "battle_id": bid,
                            "reason": f"audit hash mismatch ({reason}): actual {actual_hash!r} != recorded {recorded_hash!r}",
                            "timestamp": time.time(),
                        },
                    )
                    mismatches += 1
                    continue

            try:
                res = await replay_input_log(sidecar, battle_id=f"{bid}-audit", input_log=input_log)
                resim_winner = sanitize_name(res.winner)
                reported = sanitize_name(reported_winner or "")
                if resim_winner != reported:
                    log.warning(
                        "Winner mismatch for battle %s: resim=%r, reported=%r. Quarantining.",
                        bid,
                        resim_winner,
                        reported,
                    )
                    # Append quarantine event to the log
                    elog.append(
                        "quarantine",
                        {
                            "battle_id": bid,
                            "reason": f"audit mismatch ({reason}): resim winner {resim_winner!r} != reported {reported!r}",
                            "timestamp": time.time(),
                        },
                    )
                    mismatches += 1
                else:
                    log.info("Battle %s audit passed.", bid)
            except Exception as e:
                log.error("Re-simulation failed for battle %s: %r", bid, e)

    log.info("Audit job completed. %d mismatches found and quarantined.", mismatches)
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Re-simulation audit job")
    parser.add_argument(
        "--events-path",
        type=Path,
        default=Path("/tmp/arena-runtime/events.jsonl"),
        help="Path to events.jsonl",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("/tmp/arena-runtime/artifacts"),
        help="Path to artifacts directory",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=0.10,
        help="Random sampling rate (default: 0.10)",
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(run_audit(args.events_path, args.artifacts_dir, args.rate)))


if __name__ == "__main__":
    main()
