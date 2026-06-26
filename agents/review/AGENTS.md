---
title: agents/review — agentdex-cli
status: active
owner: etang
created: 2026-06-08
updated: 2026-06-25
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
enforced_by:
  - .github/workflows/pr-cascade-breaker-gate.yml
  - .github/workflows/review-comment-signoff-gate.yml
  - scripts/pr_cascade_breaker_gate.py
  - scripts/enforce_review_bounds.sh
---

# agents/review — agentdex-cli

## Merge philosophy (G2 ep5+7 — async, not sync-block)
- Lint + test gates are MANDATORY but run async — agent can open PR before human looks.
- Canary deploy / preview env runs on every PR; agent watches its own canary metrics.
- Human review is HIGH-LEVERAGE checkpoints (research, plan) not every commit.

## Auto-merge criteria

All criteria below must hold AND the agent's `AUTONOMY_THRESHOLD.md`
gate must be AUTONOMOUS (default SUPERVISED — every PR human-gated
until the 14-day flip gates pass). Until threshold flips, auto-merge
is DISABLED regardless of these criteria.

Scoped by the root [CI-POLICY](../../AGENTS.md#ci-policy): "CI green" /
"hooks pass clean" below mean **your change's own** lint+test job and
**your diff** — a full-tree `pre-commit run --all-files` red on
third-party / sibling-synced files you did not touch (e.g. the
hook-excluded `vendor/aaop/**`) is NOT a blocker; fix such shared red as
its own tiny PR instead of gating yours on it.

- Your change's CI checks green — `uv run --no-sync pytest` over the **changed
  surface** exits 0: the package(s) your diff touches **plus the full reverse
  transitive closure of downstream workspace packages** — every package that
  declares them as a dependency directly OR transitively (e.g. editing
  `agentdex_engine` runs `agentdex_arena`, `agentdex_cli`, `agentdex_plugin`,
  `adx_showdown`, AND `adx_bridges` — which reaches the engine transitively
  through `adx_showdown`, so a direct-dependents-only scope would leave its
  tests unrun). An API/behavior break in a shared package must not pass the gate
  by leaving a direct OR transitive dependent's tests unrun. Still not a full
  blind `packages/` sweep: a pre-existing failure in a package neither touched
  nor downstream of your diff is a separate tiny PR, per the CI-POLICY note above.
- No HIGH-severity `agentlint scan` findings (per `agentlint.yaml`)
- `.pre-commit-config.yaml` hooks pass clean **on your diff** — ruff (lint+format),
  mypy (strict on `packages/agentdex_engine/src/agentdex_engine/cards/`),
  detect-secrets vs `.secrets.baseline`
- Coverage delta ≥ 0 (`coverage run -m pytest` vs main baseline)
- Golden Pareto verdict shape still matches
  `tests/golden/nvidia_pareto_expected.yaml` (smoke test invariant)
- Tiny-PR discipline holds: diff touches ≤ 10 files OR commit body
  carries `Note: bundled because <reason>` (per
  `feedback_tiny_pr_discipline` memory + Ideal Moment 1 in
  `IDEAL_EXPERIENCE.md` v2)
- Doctrine anchors green per latest
  `sweeps/<date>-weekly-harness-audit.md` cross-check (10/10 anchors)

## Escalation path

The agent STOPS + pings human when ANY of these triggers fires. The
default `AUTONOMY_THRESHOLD.md` state is SUPERVISED — every PR ALREADY
escalates by default. The triggers below also apply post-flip.

- A planning question genuinely requires user judgment: scope expansion
  beyond the original task, an architectural fork between two equally
  valid approaches, or an irreversible/destructive op (per CLAUDE.md
  "Autonomous-agent defaults" + `feedback_fix_all_before_moving_forward`
  memory). DO NOT escalate "do I batch or split?" — both answers are
  obvious; just work the queue top-to-bottom.
- HIGH-severity `agentlint scan` finding lands on main (per
  `AUTONOMY_THRESHOLD.md` rollback trigger).
- Eval golden set score drops > 5% in a single PR.
- Pre-commit `detect-secrets` flags a NEW result not present in
  `.secrets.baseline` — likely real leak; do not auto-rebase the
  baseline.
- An issue requires credentials, external account access (Anthropic
  console billing, GH org admin), or capabilities the agent lacks.
- The agent has edited the same file > 5 times in one session AND
  tests still fail — doom-loop guard per `agents/debug/AGENTS.md`
  G4 LangChain ep4 trigger.

Ping channel: append a one-line entry to
`~/.cursor/projects/home-admin/heartbeat/monitor-gaps.md` (the same
gap log the cron wrappers funnel into); the persistent orchestrator
(`harness-N` per `feedback_persistent_orchestrator` memory) sweeps
that file on its 1h gap-log cadence.

---

## PR Cascade Breaker — reviewer protocol (mandatory)

Every reviewer (`chatgpt-codex-connector[bot]`, `cursor-agent`, `agy`, Claude/EdwardTang) operating on this repo's PRs MUST walk the `pr-cascade-breaker` finite state machine before posting a single comment. Canonical skill: `~/.claude/skills/pr-cascade-breaker/SKILL.md` (synthesised 2026-06-25 from 6 historical cascade post-mortems across `good-night-oppie/{eddie-agi-kb, agentdex-cli, bene}`). In-repo gate: `scripts/enforce_review_bounds.sh`. CI workflow: `.github/workflows/pr-cascade-breaker-gate.yml` (intercepts review payloads before they reach the GitHub API).

### 11 hard rules — refusal to follow drops your finding at the format gate

1. **Sync-PR bypass** — PR title matching `^(chore\(sync\)|merge|Sync GA|build\(vendor\))` → APPROVE, no behaviour review. (Cascades C3/C4: `agentdex-cli#508/#499`.)
2. **Queue-drain scope-lock** — PR body has `Drains-Cascade: #N` or title matches `complete the .* review queue` → review ONLY the drained-thread file set; no new findings on adjacent code. (C1: `bene#83`.)
3. **Batch limit ≤5** — >5 findings on one pass MUST be bundled into `docs/reviews/PR_<NUM>_DIGEST.md` + ONE PR-level comment. Inline calls beyond #5 are dropped by the gate. (C6: `eddie-agi-kb#404`.)
4. **No noise-mask** — Do NOT bundle a verifiable P1 with unverifiable P3 nits in one review. Split by priority so a skim cannot dismiss both. (C5: `eddie-agi-kb#328`.)
5. **Structural format** — Every finding MUST be a YAML `reviewer_finding` block (see schema in skill SKILL.md §"Reviewer-Finding format"): `kind` / `priority` / `blocking_verdict` / `exploitability` / `file` / `evidence_quote` (grep-verified) / `fix_suggestion` / `withdraw_condition`. Add `citation: SEARCH.json idx:<hash>` for kind∈{architecture, logic, security}; `exploit_demo` for exploitability=HIGH. Malformed = dropped.
6. **No tightening without citation** — Demanding a stricter guard / new `raise` / rejected input shape without a `SEARCH.json` citation proving the tightened rule matches canonical wire form → finding auto-downgraded to `DEFER_TO_FOLLOWUP`. (C1: `from_adx_dict` over-reach reverted in 1 hour.)
7. **Iteration cap K=3** — After 3 review iterations (commit count), the reviewer is mechanically muted. Eddie (orchestrator) takes over.
8. **Thread lifecycle** — Threads MUST resolve via `Resolves-Thread: <id>` / `Withdraws-Thread: <id>` commit trailer (granular) or `Drains-Cascade: #N` PR-body line (macro). No manual "Fixed + merged in #X. Resolving." paste. The gate auto-resolves siblings on merge.
9. **Split-panel disagreement** — If you disagree with another reviewer, the tie-breaker is the Exploitability Gate. If exploit=SAFE → APPROVE author's implementation. Do NOT relay the scariest verdict.
10. **Done = deployed+live** — Hash-locked probe = `converged` AND only P2/P3 open → APPROVE and drop nits to followup PRs. (Eddie standing directive.)
11. **Known-red exclusions** — Ignore vendor pre-commit failures (`adx-cli` standing directive) and runner-manifest gaps (Python 3.12 / Debian 12). These are infra, not diff. Do NOT block on them.

**Default to HALT on ambiguity. APPROVE requires positive evidence, not absence of objection.**

### Activation

- The fleet review router (`scripts/fleet_review_router.py`) injects an abbreviated version of these rules into every A2A review request — codex-bot/og/eddie-agi-kb/harness all receive the same protocol.
- Claude Code agents auto-load the full skill on activation keywords (`/review`, `Review this PR`, `PTAL`, `Resolves-Thread:`, `Drains-Cascade:`).
- The non-LLM CI gate (`.github/workflows/pr-cascade-breaker-gate.yml`) intercepts review payloads and drops malformed findings before they reach GitHub — no LLM can argue its way past it.

### Recursive applicability

This section itself is policy. A reviewer who adds a row to the decision matrix without a real-cascade citation (verifiable via `gh pr view`) will be rejected by this gate, applied to their PR.
