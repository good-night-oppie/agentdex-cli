---
title: "EventLog append throughput - ADR-0012 must-measure #2"
status: active
owner: "@EdwardTang"
created: 2026-06-23
updated: 2026-06-23
type: reference
scope: scripts
layer: cross-cutting
cross_cutting: true
---

# EventLog append throughput - 2026-06-23

ADR-0012 must-measure #2 asks whether the durable arena write path can sustain
roughly 100 concurrent turns/sec. This run measures the current
single-fcntl-lock NDJSON `EventLog` baseline before replacing it with
SQLite-WAL or Postgres-direct.

## Tool

`scripts/eventlog_append_bench.py` writes hash-chained rows through
`agentdex_engine.modules.arena.events.EventLog` and verifies the final chain
row count after every level.

Default coverage:

- `append`: one canonical row per operation; this is the per-turn hot path.
- `append_many:3`: grouped atomic writes similar to end-of-battle receipt
  groups; this rewrites the JSONL file under the lock.
- executor: process workers, so fcntl contention is measured across real
  processes instead of only in-process threads.
- payload: 512 bytes, approximating a small turn event with metadata.

## Fresh-log run

Date: 2026-06-23.

Command:

```bash
python3 scripts/eventlog_append_bench.py --levels 1,2,4,8,16,32,64,100 --rows-per-level 1000 --modes append,append_many:3 --payload-bytes 512
```

| mode | workers | rows | seconds | rows/sec | op p50 ms | op p95 ms | chain rows | errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `append` | 1 | 1000 | 0.1024 | 9767.5 | 0.078 | 0.121 | 1000 | 0 |
| `append` | 2 | 1000 | 0.4597 | 2175.1 | 0.857 | 1.786 | 1000 | 0 |
| `append` | 4 | 1000 | 0.4270 | 2341.8 | 1.425 | 2.696 | 1000 | 0 |
| `append` | 8 | 1000 | 0.5021 | 1991.5 | 3.659 | 6.831 | 1000 | 0 |
| `append` | 16 | 1000 | 0.5598 | 1786.4 | 8.048 | 12.269 | 1000 | 0 |
| `append` | 32 | 1000 | 0.6374 | 1569.0 | 17.675 | 23.789 | 1000 | 0 |
| `append` | 64 | 1000 | 0.6928 | 1443.5 | 34.692 | 45.692 | 1000 | 0 |
| `append` | 100 | 1000 | 0.7623 | 1311.9 | 56.878 | 70.680 | 1000 | 0 |
| `append_many:3` | 1 | 1000 | 1.6374 | 610.7 | 4.903 | 7.175 | 1000 | 0 |
| `append_many:3` | 2 | 1000 | 2.1485 | 465.5 | 12.884 | 16.332 | 1000 | 0 |
| `append_many:3` | 4 | 1000 | 2.2635 | 441.8 | 26.577 | 37.780 | 1000 | 0 |
| `append_many:3` | 8 | 1000 | 2.2841 | 437.8 | 57.879 | 74.561 | 1000 | 0 |
| `append_many:3` | 16 | 1000 | 2.2073 | 453.0 | 104.072 | 130.082 | 1000 | 0 |
| `append_many:3` | 32 | 1000 | 2.4356 | 410.6 | 202.180 | 287.575 | 1000 | 0 |
| `append_many:3` | 64 | 1000 | 2.5462 | 392.7 | 366.613 | 517.450 | 1000 | 0 |
| `append_many:3` | 100 | 1000 | 3.1423 | 318.2 | 678.900 | 780.946 | 1000 | 0 |

## Aged-log check

Command:

```bash
python3 scripts/eventlog_append_bench.py --levels 100 --rows-per-level 1000 --modes append,append_many:3 --payload-bytes 512 --preload-rows 10000
```

| mode | workers | preload rows | new rows | seconds | rows/sec | op p50 ms | op p95 ms | chain rows | errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `append` | 100 | 10000 | 1000 | 8.2843 | 120.7 | 780.158 | 901.716 | 11000 | 0 |
| `append_many:3` | 100 | 10000 | 1000 | 22.6921 | 44.1 | 5664.935 | 6493.463 | 11000 | 0 |

## Finding

The current NDJSON `append` path clears the roughly 100 turns/sec target in the
100-worker process-contention test. On a fresh log it has large headroom
(1311.9 rows/sec at N=100). With 10k existing rows it still clears the target
(120.7 rows/sec at N=100), but the margin is thin because competing workers
reload the watermark after external writes.

The grouped `append_many` receipt path is not suitable as a high-rate per-turn
path on a long-lived JSONL file: it rewrites the file under the lock and falls
to 44.1 rows/sec after a 10k-row preload. That does not block the current
per-turn append design, but it means grouped writes should stay off the hot path
or move to an append-only/SQLite-WAL implementation before grouped writes become
turn-rate traffic.
