---
title: "Clean-state enforcement — pre-commit, lint, CI, worktree"
status: active
owner: "@EdwardTang"
created: 2026-07-14
updated: 2026-07-14
type: runbook
scope: docs/runbooks
layer: cross-cutting
cross_cutting: true
---

# Clean-state enforcement

One definition of "clean", enforced at four points. The definition lives in
`scripts/clean_state.py`; everything else calls it.

## The bug this exists to kill

`doc_lint.py` globs the **working tree**. CI runs on a **fresh clone**. Untracked
files are therefore invisible to CI and fully visible to the local gate.

One untracked `.md` under `docs/` — the harness-HA design doc sat there for three
days — trips DOC-LINT-020, so `doc_lint --staged` exits 1 and **every commit by
every session in this repo is blocked**, while CI stays green and nobody can see
why.

That is not a lint failure. It is a **congruence failure**, and the rational
response to a gate you cannot pass is `git commit --no-verify`. Which is exactly
what this repo learned to do. The gate was present; it was not running.

The fix is to keep the local tree congruent with the CI tree: **a file is either
tracked or ignored. "Neither" is not a state.**

## The four enforcement points

| Point | Mode | Enforces |
| --- | --- | --- |
| `.git/hooks/pre-commit` | `--mode precommit` | no unignored untracked files |
| `.pre-commit-config.yaml` | `--mode precommit` | same rule, when `pre-commit run` is used (CI `lint.yml`) |
| `.github/workflows/clean-state-gate.yml` | `--mode ci` | generator output committed; hook still wired; PR adds no junk paths |
| `scripts/new_worktree.sh` | `--mode worktree` | source tree clean + `doc_lint` green + base fresh from `origin` |

### What CI can and cannot do

CI checks out a fresh clone, which by construction has **zero** untracked files.
So CI **cannot** police "no untracked junk" — asserting it there would be theater
that always passes. Untracked files are policed where they exist: the pre-commit
hook.

What CI *does* enforce:

1. **generators** — run every generator, assert the tree did not move. Catches a
   `CLAUDE.md` TOC that was hand-edited or left stale.
2. **hook-wired** — the clean-state hook is still declared and still installed.
   A gate you can quietly delete is not a gate.
3. **junk-paths** — refuses a PR that *adds* `.playwright-mcp/` or
   `*settings.local.json`.

The CI gate runs on **`ubuntu-latest`, not the self-hosted runner**, on purpose:
as of 2026-07-14 `tiny-pr-gate` is a *required* check that produces no runs, so
every PR into `redesign/evolution-market` is permanently BLOCKED. A required check
that cannot execute is worse than no check.

## Setup — you must run this once

```sh
bash scripts/install_doc_lint_precommit.sh
```

**Nothing installs hooks automatically.** A fresh clone has *no* gate at all while
`.pre-commit-config.yaml` cheerfully declares one — declaration is not
installation, and an uninstalled gate is indistinguishable from a passing one.
`clean_state.py --mode worktree` therefore checks `hook-installed` explicitly, and
`new_worktree.sh` runs the installer for you.

Hooks live in `$GIT_COMMON_DIR/hooks`, which **every worktree of this repo
shares** — install once, covered everywhere. (Not `$REPO_ROOT/.git/hooks`: inside
a worktree `.git` is a *file*, so that path is `Not a directory`. The original
installer was unusable in the exact place this repo is developed.)

Idempotent. Rewrites only its **managed block** (between the `# >>>
doc-lint+clean-state >>>` markers) and preserves anything appended outside it —
notably the `kanban-blast-radius` gate, which the previous `cat > hook` installer
silently deleted on `--force`. Writes are `flock`-serialized and published via
atomic `rename(2)`, because that hook file is shared with live sibling sessions
and truncating it in place lets a concurrent `git commit` exec a half-written file.

## Opening a worktree

```sh
bash scripts/new_worktree.sh <branch> [base=main]
```

Always cuts fresh from `origin/<base>` and has **no reuse path** — `checkout main
&& reset --hard` fails silently and is banned
(`feedback_worktree_reset_silent_fail`). It also installs the hooks.

It refuses to run while **this** tree is unclean. Note the honest reason: the new
worktree is cut from `origin/<base>`, so your dirty tree *cannot* leak into it.
The gate protects the tree you are **leaving behind** — it is shared across agent
sessions, and your untracked `docs/*.md` will red-line every sibling's commits for
a reason none of them can see. "I'll come back to it" is how the harness-HA doc sat
untracked for three days.

## When the gate blocks you

```
[clean-state] FAIL mode=precommit — 1 finding(s)
  [untracked] scratch.md
```

Outside `docs/`, two honest resolutions and only two:

- `git add scratch.md` — it is real work.
- add it to `.gitignore` — it is debris.

If it is debris that *any routine command produces*, ignoring it is mandatory, not
optional: a gate a normal command can trip is a gate that gets bypassed.
`node_modules/` and `htmlcov/` were added to `.gitignore` for exactly this reason.

### The `docs/**/*.md` exception — "gitignore it" is a DEAD END

`doc_lint` walks `docs/` with `pathlib.rglob`, which **does not read
`.gitignore`**. So an *ignored* `.md` under `docs/` still trips DOC-LINT-020 and
still red-lines every commit. Gitignoring it sends you in a circle.

For `docs/**/*.md` the only resolutions are:

- **track it AND link it from `AGENTS.md`** (DOC-LINT-020 wants 3-hop
  reachability, and the link graph contains only `AGENTS.md` + `docs/**.md` —
  `CLAUDE.md` is *not* a node), or
- **move or delete it out of `docs/`.**

`clean_state.py` prints this remedy automatically for those paths. It was found by
adversarial review *after* the first version of this runbook confidently
advertised the dead end.

## Override

```sh
CLEAN_STATE_OVERRIDE=1 git commit ...
```

It exists because `git commit --no-verify` already bypasses every local hook —
making this override *harder* than `--no-verify` would buy nothing but resentment.
It announces itself loudly on stderr so it is greppable in a transcript later.

**It is ignored in `--mode ci`.** An escape hatch that greens the authoritative
gate is not a hatch, it is a hole: anyone able to set an env var in a workflow
could ship an unclean tree. Local hooks are advisory by nature (anyone can
`--no-verify`); CI is the enforcement.

## Verifying the gate actually runs

```sh
bash scripts/_smoke_clean_state.sh
```

Every assertion is proved **both ways** — fail-on-unclean *and* pass-on-clean. A
gate only ever observed passing is indistinguishable from one that is disabled
(`feedback_gate_present_is_not_gate_running`). The smoke test also proves the
installed hook **blocks a real `git commit`**, not merely that the file exists.

## Known limit (asserted, not hidden)

`--mode ci` measures the generator **delta** across the run. If a generated file
is *already* dirty before the run, the generator's change is masked. CI is
authoritative precisely because its pre-run diff is empty. The smoke test asserts
this limit so it cannot silently change.
