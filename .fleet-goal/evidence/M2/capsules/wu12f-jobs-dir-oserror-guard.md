---
title: "M2 WU-12F fix capsule — the new --jobs-dir flag must not crash with a raw traceback on a bad path (OSError guard → exit 2)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "adx measure --jobs-dir with an uncreatable path (existing file, file-as-parent-component, or unwritable location) MUST exit 2 with a clean actionable stderr message, never a raw Python traceback"
    test: "packages/agentdex_cli/tests/test_measure_cmd.py (regression lands with this fix)"
---

# M2 WU-12F — guard --jobs-dir mkdir (regression from WU-12)

You are an implementation worker for the agentdex redesign. Work in
`/home/admin/gh/agentdex-cli-redesign` (branch `redesign/evolution-market`).
READ FIRST: `packages/agentdex_cli/src/agentdex_cli/measure_cmd.py`
(`cmd_measure` — the `_build_adapter` call is wrapped only in
`except RuntimeError` + `except FileNotFoundError`, ~230-236; `--jobs-dir`
is passed to `HarborCliClient(jobs_dir=...)` via `_build_adapter`),
`packages/adx_ladders/src/adx_ladders/engines/harbor_cli.py`
(`__init__` ~68-74: `self._jobs_dir = Path(jobs_dir); self._jobs_dir.mkdir(parents=True, exist_ok=True)`).

## The defect (regression check confirmed, reproduced end-to-end)

WU-12 shipped the new user-facing `--jobs-dir` flag. `HarborCliClient.__init__`
does `Path(jobs_dir).mkdir(parents=True, exist_ok=True)`, which raises OSError
subclasses on ordinary bad input: `FileExistsError` (leaf is an existing
regular file — `exist_ok=True` only suppresses when the leaf is a dir),
`NotADirectoryError` (a parent component is a file), `PermissionError`
(unwritable). `cmd_measure` catches only `RuntimeError` and `FileNotFoundError`
— none of these are subclasses — so the CLI prints a raw traceback and exits
1/nonzero instead of the contracted clean `_EXIT_GATE` (2). Before WU-12 the
CLI always passed `jobs_dir=None` (mkdtemp), so this branch was unreachable.
This breaks the "clean error, never a traceback" contract the module
docstrings state and the harbor tests assert.

Reproduced: `adx measure --agent <tb2-candidate> --ladder tb2 --engine
harbor-cli --harbor-tasks hello-world --jobs-dir <an-existing-regular-file>`
→ `FileExistsError` traceback, nonzero non-2 exit.

## Guardrails (hard)

- Touch ONLY: `packages/agentdex_cli/src/agentdex_cli/measure_cmd.py`,
  `packages/agentdex_cli/tests/test_measure_cmd.py`. NOTHING else.
- Do NOT `git commit` / `git push`. NO paid-LLM / NO real harbor runs.
- Do NOT change `HarborCliClient` (out of allowed_paths) — guard at the CLI
  boundary where the exit code is owned.

## Fix

In `cmd_measure`, add `except OSError as exc:` to the `_build_adapter`
try-block (alongside the existing RuntimeError / FileNotFoundError handlers),
printing an actionable message and returning `_EXIT_GATE` (2). Order it AFTER
`FileNotFoundError` (which is itself an OSError subclass — keep the missing-
binary message distinct; the harbor client raises `FileNotFoundError` with the
install hint, so that catch must stay FIRST). Suggested message:
`f"--jobs-dir {args.jobs_dir!r} is not a usable directory: {exc}"` — but only
when `args.jobs_dir` is set; a bare OSError from elsewhere should still get a
clean generic message + exit 2, never a traceback.

## Tests

- `--jobs-dir <existing regular file>` + `--engine harbor-cli`
  `--harbor-tasks x` (stub harbor on PATH) → exit 2, actionable message on
  stderr, assert `"Traceback" not in captured.err`.
- `--jobs-dir <nested-under-a-file>` (NotADirectoryError) → exit 2, no
  traceback.
- A valid `--jobs-dir` still works (regression: existing durable-artifacts
  test stays green).
- Existing suites stay green.

## Acceptance (run + paste)

- `uv run pytest packages/adx_ladders/tests/ packages/adx_frontier/tests/ packages/agentdex_cli/tests/ -q`
  (only the pre-existing `test_kaos_lineage_entry_persisted` failure allowed)

## Return contract (four fields ONLY)

1. What was learned
2. What changed (file list)
3. Supporting evidence (test output verbatim)
4. What should happen next
