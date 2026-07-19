---
title: "M2 WU-1 request capsule — AgentCandidate manifest + pre-run validation gate"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
---

# M2 WU-1 — AgentCandidate manifest + pre-run validation gate

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (git worktree, branch
`redesign/evolution-market`). READ FIRST: `.fleet-goal/evidence/M1/DESIGN.md`
(sections "AgentCandidate" + "Frontier") and `docs/adr/0015-evolution-ladder-redesign.md`
(D1, D3, enforced_by rows). Repo conventions: uv workspace — copy the pyproject
pattern from `packages/adx_bridges/pyproject.toml`; match the code style of
existing packages.

## Guardrails (hard)

- Touch ONLY `packages/adx_frontier/**` (new package). Never edit `.supergoal/`,
  `.fleet-goal/`, other packages, or repo-root files EXCEPT the root
  `pyproject.toml` uv-workspace members list if new members must be declared.
- Do NOT `git commit` or `git push` — the coordinator reviews and commits.
- No network calls; no credentials; pure local code + tests.

## Deliverable

`packages/adx_frontier/` — new uv-workspace package containing `candidate.py`
(+ `__init__.py`, `pyproject.toml`, `tests/test_candidate.py`).

`candidate.py` implements the AgentCandidate manifest (DESIGN.md schema):

```yaml
name: my-agent
entrypoint: "python -m my_agent"
mutable: ["src/**/*.py", "prompts/*"]
base_model: claude-sonnet-5
budget: {usd: 5.00, wall_clock_min: 60}
ladders: [tb2, arc-agi-3, pokeagent-gen1ou]
```

API: `load_candidate(dir_path) -> AgentCandidate` (parses `candidate.yaml` in
the dir) and `AgentCandidate.validate() -> None | raises CandidateValidationError`.

**Pre-run validation gate (user directive — the frontier must be ungameable
by proxy-winners; REJECT before any run starts):**

1. **weco --sources limits:** expand `mutable` globs against the candidate
   dir; the expansion must be ≤10 files, ≤200KB per file, ≤500KB total.
   Violation → error message containing "narrow your weco-mutable subset"
   plus the actual counts/sizes.
2. **Declared budget:** `budget.usd > 0` AND `budget.wall_clock_min > 0`,
   both present. Missing/zero → reject.
3. **Axes partition completeness:** `base_model` non-empty string; `ladders`
   non-empty list drawn from a module-level `KNOWN_LADDERS` registry constant
   `{"tb2", "arc-agi-3", "pokeagent-gen1ou", "kaggle", "swe-bench-pro", "webarena"}`;
   define module constant `FRONTIER_AXES = ("quality", "cost_dollar", "wall_clock_sec")`
   exported for downstream use. Unknown ladder / empty → reject.
4. `name` and `entrypoint` non-empty.

Plain dataclasses + PyYAML preferred (match repo deps); pydantic only if the
repo already uses it in packages/.

## Acceptance (run these; paste outputs in your reply)

- `uv run pytest packages/adx_frontier/tests/ -q` — all green; tests cover:
  valid manifest accepted; each rejection path (too many files, oversize file,
  oversize total, missing budget, zero budget, unknown ladder, empty ladders,
  missing base_model, missing entrypoint); error message for the weco limit
  contains "narrow your weco-mutable subset".
- `uv run python -c "from adx_frontier.candidate import load_candidate, FRONTIER_AXES; print(FRONTIER_AXES)"`.

## Return contract (four fields ONLY)

1. What was learned
2. What changed (file list)
3. Supporting evidence (test output verbatim)
4. What should happen next
