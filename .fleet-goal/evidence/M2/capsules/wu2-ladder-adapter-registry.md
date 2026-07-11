---
title: "M2 WU-2 request capsule — LadderAdapter ABC + curated market registry"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "MeasureResult score keys MUST be exactly FRONTIER_AXES; Receipt tier rules (verified⇒ref, self_reported⇒artifacts); pre_run_check MUST reject invalid candidates and unlisted ladders"
    test: "packages/adx_ladders/tests/test_base.py (lands with this WU)"
  - claim: "registry ids MUST cover adx_frontier.KNOWN_LADDERS; class assignments MUST match ADR-0015 D4"
    test: "packages/adx_ladders/tests/test_registry.py (lands with this WU)"
---

# M2 WU-2 — LadderAdapter ABC + curated market registry

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (git worktree, branch
`redesign/evolution-market`). READ FIRST: `.fleet-goal/evidence/M1/DESIGN.md`
("Ladder taxonomy", "Module Structure", "Frontier + ledger data model"),
`docs/adr/0015-evolution-ladder-redesign.md` (D3, D4, D4a, D5, D6), and
`packages/adx_frontier/src/adx_frontier/candidate.py` (WU-1 — consume
`AgentCandidate`, `FRONTIER_AXES`, `KNOWN_LADDERS`; do NOT redefine them).
Copy the pyproject pattern from `packages/adx_frontier/pyproject.toml`.

## Guardrails (hard)

- Touch ONLY `packages/adx_ladders/**` (new package) + the root
  `pyproject.toml` workspace members/sources lists.
- Do NOT `git commit` or `git push` — the coordinator reviews and commits.
- No network calls in code or tests (adapters that talk to real ladders come
  in later WUs); no credentials.

## Deliverable

`packages/adx_ladders/` — new uv-workspace package:

1. `src/adx_ladders/base.py`:
   - `class LadderClass(enum.Enum): LIVE_ADVERSARIAL, STATIC` (two-class
     taxonomy, ADR D4).
   - `@dataclass(frozen=True) Receipt`: `tier: str` ("verified" |
     "self_reported"), `kind: str` (e.g. "arc_scorecard_id",
     "kaggle_submission_id", "pokeagent_rating", "raw_artifacts"),
     `ref: str`, `artifacts: tuple[str, ...] = ()`. Rule (ADR D6): tier
     "verified" REQUIRES a non-empty `ref`; tier "self_reported" REQUIRES a
     non-empty `artifacts` tuple — enforce in `__post_init__`.
   - `@dataclass(frozen=True) MeasureResult`: `scores: dict[str, float]`
     (keys MUST be exactly adx_frontier.candidate.FRONTIER_AXES — enforce),
     `receipt: Receipt`, `ladder_id: str`, `base_model: str`,
     `budget_usd: float`, `budget_wall_clock_min: float`.
   - `class LadderAdapter(abc.ABC)`: class attrs `ladder_id: str`,
     `ladder_class: LadderClass`; abstract
     `measure(candidate: AgentCandidate) -> MeasureResult`; concrete
     `pre_run_check(candidate)` that calls `candidate.validate()` AND asserts
     `self.ladder_id in candidate.ladders` (reject otherwise) — adapters MUST
     run out-of-process per ADR D3 (docstring note; enforcement per-adapter).
2. `src/adx_ladders/registry.py` + `registry.yaml` (package data): the
   curated market — one entry per ladder with fields
   `{id, title, ladder_class, operator, url, leaderboard_url, access,
   run_adapter (v1: tb2|arc-agi-3|pokeagent-gen1ou true, others false),
   notes}` for: kaggle, arc-agi-3, pokeagent-gen1ou (live-adversarial);
   swe-bench-pro, tb2, webarena (static); PLUS a separate top-level
   `substrates:` section with huggingface (NOT a ladder — datasets /
   distribution / model-hosting). Link-out only — no leaderboard mirroring
   fields (ToS pending, ADR D5). `load_registry() -> Registry` with lookup
   by id and `.ladders` / `.substrates` views; registry ids MUST be a
   superset-match of adx_frontier KNOWN_LADDERS (test this consistency).
3. `tests/test_base.py` + `tests/test_registry.py`: cover Receipt tier rules
   (verified-without-ref rejected; self_reported-without-artifacts rejected),
   MeasureResult axes-key enforcement (wrong/missing keys rejected),
   pre_run_check (invalid candidate rejected; ladder not in candidate.ladders
   rejected; valid passes with a stub adapter), registry loads, 6 ladders +
   1 substrate, class assignments match ADR D4 exactly, KNOWN_LADDERS
   consistency.

## Acceptance (run these; paste outputs)

- `uv run pytest packages/adx_ladders/tests/ -q` all green.
- `uv run python -c "from adx_ladders.registry import load_registry; r=load_registry(); print([l.id for l in r.ladders], [s.id for s in r.substrates])"`

## Return contract (four fields ONLY)

1. What was learned
2. What changed (file list)
3. Supporting evidence (test output verbatim)
4. What should happen next
