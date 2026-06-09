# Weekly harness audit — 2026-06-09

_Generated 2026-06-09T05:14:09Z by cron/weekly_harness_audit.sh._

This file is auto-generated. Sections below are READ-ONLY signals — no
primary artifact is modified by the audit. Review + act manually as
[tiny PRs](~/.claude/projects/-home-admin-gh-agentdex-cli/memory/feedback_tiny_pr_discipline.md).

## 1. Commit shape (Ideal moment 1)

```
210f98e  files=1  PR-C part 2: .github/workflows/lint.yml CI gate (H1 closing)
dc61ed6  files=2  PR-C: pyproject [dependency-groups] dev + scripts/install_hooks.sh (H1 part 1)
0273cfb  files=2  PR-B: tighten ProvenanceOracle CLAIM_LINE_RE to reject prose initials (C3)
65b2996  files=1  PR-A: regenerate .secrets.baseline with current tree coverage (C1)
4612c45  files=1  D3: populate agents/review/AGENTS.md auto-merge + escalation stubs (PR #12)
d8b3a65  files=1  D1: cliproxy probe lru_cache maxsize 8 → 1 (PR #11)
1634b87  files=8  D2: gitignore + untrack expeditions/test-smoke-exp-001/ (PR #10)
5396b90  files=1  SF3: drop _estimate_cost 1e-6 floor (G11 bitter-lesson, PR #9)
5f0d89c  files=1  SF2: plumb usage tokens + model id into judge generation span (PR #8)
abba6ba  files=1  SF1: surface Langfuse tracer failure as WARN once per process (PR #7)
da4e581  files=3  cron/dream_consolidate.sh + sweeps/<date>-dream-consolidate.md (PR #6)
18e2b0b  files=2  .harness/: track CORPUS_QUERY_KEYWORDS + README (PR #5)
72bcdc9  files=2  cron/weekly_harness_audit.sh + sweeps/<date>.md: weekly doctrine audit
366813c  files=1  cron/expedition_smoke.sh: daily smoke wrapper (mirror eddie-agi-kb pattern)
07e5f55  files=1  CLAUDE.md: rescind async-as-source-of-truth claim (MF1 followup)
eddf0bb  files=2  scripts/sync_toc.sh: port from eddie-agi-kb + regen CLAUDE.md TOC
bd16c47  files=21 ⚠ TINY_PR_VIOLATION  codereview-fix-2: harness-praxis 14-group doctrine alignment (MF1-MF6)
fc1d12e  files=14 ⚠ TINY_PR_VIOLATION  live-expedition-data: live-003 full + live-001 partial + smoke regen
22d6285  files=17 ⚠ TINY_PR_VIOLATION  codereview-fix-1: ProvenanceOracle per-bullet + real cost + judge span + stderr safety
18456a0  files=9  live-3bridge: fix codex 64KB stream limit + claude bridge --dangerously-skip-permissions; first live 3-bridge expedition
3e8fda2  files=5  live-pool: CLIProxyAPI probe fix + Claude Code subscription judge wrapper
051645f  files=24 ⚠ TINY_PR_VIOLATION  musk-cut: delete adx assist, --open-ui, auto-langfuse-ensure, gemini ladder, codex-web stock manifest, FairnessDelta 7-field expansion
2f491d4  files=45 ⚠ TINY_PR_VIOLATION  M-Fairness+Pool: 3-tier fairness gate + LLM model pool + Hermes-assistant UX
4c61cff  files=2  audit-fix-1: ADR-0009 path in CLAUDE.md + README points at real filename
2aee0a6  files=8  M-Polish: CLAUDE.md doctrine + README quickstart + error-case CLI + full regression sweep (phase 8)
ed4a913  files=37 ⚠ TINY_PR_VIOLATION  M3+M4+M5: bridges + Oracle + Pareto + Expedition end-to-end (phases 5-7)
0e5f6c1  files=5  M2 final: KAOS subtree (squashed+culled) + uv.lock + build/debug AGENTS.md (S1/S2) + .gitignore /build/ anchor fix
3d5540f  files=236 ⚠ TINY_PR_VIOLATION  vendor: cull KAOS docs/demos/blog (~150MB); upstream still has them
5039a12  files=377 ⚠ TINY_PR_VIOLATION  Squashed 'packages/kaos/' content from commit a441fc9
6260ee0  files=70 ⚠ TINY_PR_VIOLATION  M2 interim: uv workspace skeleton + engine extract + agentdex_observe glue + gateway helper + R3 spike test + co-opetition reframe (ADR-0009)
1eca32a  files=9  M1: NVIDIA earnings infographic frozen task bundle (Q3 FY2026)
2ec4e27  files=5  praxis: fix M1-M3+S3+S4 (IDEAL_EXP/EVAL/golden stub/ops env vars/agentlint yaml)
c187be8  files=1  praxis: fix M1-M3+S3+S4 (IDEAL_EXP/EVAL/golden stub/ops env vars/agentlint yaml)
bb8d146  files=10  M0: ADR-0009 + Three Cards schemas (Pokédex pivot, KAOS substrate)
da1b4a4  files=41 ⚠ TINY_PR_VIOLATION  init: agentdex-cli (PHASE-3.0 scaffold baseline, pre-restructure)
```

## 2. Doctrine-vs-filesystem cross-check (Ideal moment 6)

| Doctrine claim | File path | Exists? |
|---|---|---|
| AGENTS.md senses: run_tests | `tools/agent_senses/run_tests.sh` | ✅ |
| AGENTS.md senses: tail_logs | `tools/agent_senses/tail_logs.sh` | ✅ |
| AGENTS.md senses: peek_metrics | `tools/agent_senses/peek_metrics.sh` | ✅ |
| AGENTS.md hard rails: pre-commit | `.pre-commit-config.yaml` | ✅ |
| AGENTS.md hard rails: secrets baseline | `.secrets.baseline` | ✅ |
| EVAL.md GT: golden pareto | `tests/golden/nvidia_pareto_expected.yaml` | ✅ |
| EVAL.md GT: bridge smoke fixtures dir | `tests/fixtures/bridges` | ✅ |
| EVAL.md GT: oracle calibration dir | `packages/agentdex_engine/tests/oracle_calibration_fixtures` | ✅ |
| CLAUDE.md TOC generator | `scripts/sync_toc.sh` | ✅ |
| Daily smoke cron | `cron/expedition_smoke.sh` | ✅ |

## 3. System shape (agent_senses peek_metrics)

```

=== tests (collect-only) ===
packages/agentdex_engine/tests/test_pareto.py::test_single_eligible_baseline_wins_by_default

77 tests collected in 0.22s

=== SLOC by package ===
adx_bridges              1395
agentdex_cli             1280
agentdex_engine          3405
agentdex_observe         896
agentdex_plugin          145
helios_client            106

=== recent commits (latest 5 w/ size delta) ===
210f98e 2026-06-09 PR-C part 2: .github/workflows/lint.yml CI gate (H1 closing)
 1 file changed, 39 insertions(+)

dc61ed6 2026-06-09 PR-C: pyproject [dependency-groups] dev + scripts/install_hooks.sh (H1 part 1)
 2 files changed, 48 insertions(+)

0273cfb 2026-06-09 PR-B: tighten ProvenanceOracle CLAIM_LINE_RE to reject prose initials (C3)
 2 files changed, 48 insertions(+), 6 deletions(-)

65b2996 2026-06-09 PR-A: regenerate .secrets.baseline with current tree coverage (C1)
 1 file changed, 220 insertions(+), 36 deletions(-)

4612c45 2026-06-09 D3: populate agents/review/AGENTS.md auto-merge + escalation stubs (PR #12)
 1 file changed, 48 insertions(+), 5 deletions(-)

=== latest expedition verdict ===
expedition: test-smoke-exp-001
winner: null
verdict_kind: no_clear_winner
rankings:
  claude:
    pass_rate: 1
    cost_dollar: 3
    speed_wall_clock_sec: 3
  codex:
    pass_rate: 2
    cost_dollar: 2

=== doctrine anchor line counts (G14/G13/G2 health) ===
IDEAL_EXPERIENCE.md        66 lines
EVAL.md                    49 lines
AUTONOMY_THRESHOLD.md      29 lines
AGENTS.md                  54 lines
```

## 4. Test signal (run_tests)

```
..sss.sss....................s.......................................... [ 93%]
.....                                                                    [100%]
70 passed, 7 skipped in 1.34s
```

## 5. Action queue

The audit is a read-only signal. To act on a finding above:

1. **MISSING entries in §2** → ship a tiny PR per file (max 1 LOC concern
   per commit, per [tiny-PR-discipline](~/.claude/projects/-home-admin-gh-agentdex-cli/memory/feedback_tiny_pr_discipline.md)).
2. **TINY_PR_VIOLATION flags in §1** → already shipped; not actionable
   retroactively, but next sweep should show 0 violations.
3. **System-shape regressions in §3-4** → cross-check against
   `tests/golden/nvidia_pareto_expected.yaml` before reverting.

Per IDEAL_EXPERIENCE.md v2 Ideal moment 2: this audit IS the mechanism
that keeps Ideal moments 1, 3, 4 live. Skipping a week means doctrine
drift accumulates undetected.
