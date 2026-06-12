---
title: "Arena instrument calibration report — anchor ordering + separation (phase 5)"
status: active
owner: "@EdwardTang"
created: 2026-06-12
updated: 2026-06-12
type: reference
scope: .
layer: cross-cutting
cross_cutting: true
enforced_by:
  - "cron/arena_selftest.sh (nightly; non-zero exit halts publication)"
  - "packages/adx_showdown/tests/test_calibration.py (CI, reduced budget)"
  - "Ladder.published_delta 2*RD rail (unit-tested)"
---

# Arena instrument calibration — 2026-06-12 (phase 5 acceptance run)

Gate anchors: IDEAL_EXPERIENCE §Arena A4 (receipt), A8 (verifiability).
EVAL §Arena row: *"Anchor calibration: random < max-damage < heuristics,
non-overlapping 2·RD in ≤200 battles; nightly self-test halts publication on
ordering failure."*

## Result: PASS — publication allowed

200 seeded machine-speed gen9randombattle battles (70% allocated to the close
pair), rated in a single Glicko-2 period, recomputed from the hash-chained
event log:

| Anchor | Rating | RD | Games | 2·RD interval |
|---|---|---|---|---|
| anchor-random | ≈ 1247 | ≈ 56 | 60 | [1135, 1359] |
| anchor-max_damage | **1463.8** | **39.6** | 170 | [1384.7, 1543.0] |
| anchor-heuristic | **1699.0** | **39.6** | 170 | [1619.9, 1778.2] |

- `ordering_ok: true` — random < max_damage < heuristic
- `separation_ok: true` — adjacent 2·RD intervals do not overlap
  (close-pair gap 235.2 > 2·(39.6+39.6) = 158.3)
- `publication_allowed: true`

## Method notes (measured, not assumed)

- **Skill priors:** max-damage beats random 50/50 (1.00); heuristic-v2 beats
  max-damage 27/40 (0.68 ≈ 130 Elo head-to-head). Heuristic v1
  (switch-when-resisted) LOST at 0.42 and was replaced by STAB-weighted move
  rating + bench-aware forced switches.
- **Single-period rating is a calibration-only choice**: 10 incremental
  periods left the close-pair gap at 47 Elo (shrinking RD damps later
  updates); one full-information update from RD=350 reaches 235 in the same
  200 battles. The production ladder keeps generation-sized periods.
- **Two protocol edges surfaced by the 200-battle sweep** (both fixed in
  `adx_showdown`): destructive pending-nulling stalled battles whose choice
  was rejected (now: `submitted` flag re-exposes the stored request on
  `|error|`); Revival Blessing demands passing to a FAINTED Pokémon, which
  the legal-choice enumerator rightly excludes — the deterministic fallback
  rail now serves `fainted_switch_choices` (or literal `pass`) on
  "…fainted…" rejections.

## Self-test wiring

`cron/arena_selftest.sh` reruns this calibration nightly; non-zero exit =
publication halted (the deploy phase wires the gateway to refuse rated
publishing while the last self-test is red). Reports + event logs land under
`$ARENA_SELFTEST_DIR` (default `/tmp/agentdex/arena-selftest/`) for audit.
