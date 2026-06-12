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

## Phase-7 addendum (2026-06-12) — evolution loop falsification + rollback drill

House-lane evolution loop live (`adx_showdown/evolution.py`): 5-store git
workspace (teams.json = 5th store), Distiller consumes structured signature
bullets only, Refiner must write `change_manifest.json` BEFORE its window,
Verdict is pure Python over NEXT-window CRN pairs — no self-certification.

**Rollback chaos-drill transcript (CI-reproduced, seeded):**

```
1. healthy gen-1 window: rating=1968±110 (k=20 vs random anchor)
2. INJECTED NERF committed for gen 2 (teams.json -> early-route mons; sha 0e94c3a1)
3. gen-2 CRN falsification: 20 pairs, p=0.00000 -> verdict=HARMFUL
4. rolled_back=True; teams.json restored byte-identically to best_ever (sha 4a086726 == healthy)
```

**Next-window discipline (benign 3-generation run, k=5):** gen 1 NEUTRAL
(no prior manifest, 0 pairs); gens 2–3 falsify the previous cycle's
memory-store edit with 5 CRN pairs each → honestly INCONCLUSIVE (team
unchanged, all pairs concordant, p=1.0); every report carries rating±RD and
`power=INCONCLUSIVE` at k=5 (A4 — small windows never publish deltas).

**Measured falsification gotcha:** in a max-damage MIRROR the entrant loses
most seeds — control loses identically, pairs go concordant, and a real nerf
hides (p=0.5). Falsification opponents must be ones the baseline reliably
beats; the CRN lane pins this choice per archetype.
