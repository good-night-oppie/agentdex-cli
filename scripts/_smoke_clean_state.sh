#!/usr/bin/env bash
# Smoke: clean_state.py + install_doc_lint_precommit.sh
#
# Adversarial by construction: every gate assertion is proved BOTH ways —
# fail-on-unclean AND pass-on-clean. A gate only ever observed passing is
# indistinguishable from a gate that is not running at all
# (feedback_gate_present_is_not_gate_running).
#
# Runs entirely inside a throwaway git repo under $TMP. It NEVER touches the
# real .git/hooks — that directory is shared by every worktree of this repo, so
# a smoke test that installed into it would mutate sibling sessions' gates.
#
# No network. Exit 0 only when every assertion holds.
set -uo pipefail

ROOT="${CLEAN_STATE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
GATE="$ROOT/scripts/clean_state.py"
INSTALLER="$ROOT/scripts/install_doc_lint_precommit.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAIL=0
fail() { printf '[smoke] FAIL %s\n' "$*" >&2; FAIL=$((FAIL + 1)); }
pass() { printf '[smoke] PASS %s\n' "$*"; }

# Must match BEGIN_MARK in install_doc_lint_precommit.sh. Asserted below, so a
# drift between the two files fails the smoke rather than silently skipping the
# idempotency check.
BEGIN_MARK_SMOKE='# >>> doc-lint+clean-state (managed by install_doc_lint_precommit.sh) >>>'
grep -qF "$BEGIN_MARK_SMOKE" "$INSTALLER" \
  || { printf '[smoke] FAIL marker drift: BEGIN_MARK not found in installer\n' >&2; exit 1; }

# assert_rc <name> <expected_rc> <cmd...>
assert_rc() {
  local name="$1" want="$2"; shift 2
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if [[ "$rc" -eq "$want" ]]; then pass "$name (rc=$rc)"
  else fail "$name — want rc=$want got rc=$rc; output: ${out:0:220}"; fi
}

# ---------------------------------------------------------------- sandbox repo
SANDBOX="$TMP/repo"
mkdir -p "$SANDBOX/scripts"
git -C "$SANDBOX" init -q 2>/dev/null || { echo "[smoke] cannot init git"; exit 2; }
git -C "$SANDBOX" config user.email smoke@example.com
git -C "$SANDBOX" config user.name smoke
cp "$GATE" "$SANDBOX/scripts/clean_state.py"
cp "$INSTALLER" "$SANDBOX/scripts/install_doc_lint_precommit.sh"
# doc_lint stub that always passes — this smoke tests clean_state, not doc_lint.
printf '#!/usr/bin/env python3\nimport sys; sys.exit(0)\n' > "$SANDBOX/scripts/doc_lint.py"
chmod +x "$SANDBOX/scripts/doc_lint.py"
# A real generator: deterministically rewrites GENERATED.md. clean_state's `ci`
# mode runs this and asserts the committed tree already matches its output.
cat > "$SANDBOX/scripts/sync_toc.sh" <<'GEN'
#!/usr/bin/env bash
printf 'GENERATED-CONTENT-V1\n' > "$(git rev-parse --show-toplevel)/GENERATED.md"
GEN
printf 'GENERATED-CONTENT-V1\n' > "$SANDBOX/GENERATED.md"
printf 'seed\n' > "$SANDBOX/README.md"
# A REAL hook declaration, not a stub. check_hook_wired parses this as YAML and
# requires a hook whose id is clean-state AND whose entry runs clean_state.py — a
# substring stub would pass a weaker check and prove nothing.
cat > "$SANDBOX/.pre-commit-config.yaml" <<'CFG'
repos:
  - repo: local
    hooks:
      - id: clean-state
        name: clean-state
        entry: python3 scripts/clean_state.py --mode precommit
        language: system
        always_run: true
        pass_filenames: false
CFG
# hook-wired requires these to EXIST (deletion is the easiest rot), so the sandbox
# must carry them or every ci-mode assertion below fails for the wrong reason.
mkdir -p "$SANDBOX/.github/workflows"
printf 'run: python3 scripts/clean_state.py --mode ci\n' > "$SANDBOX/.github/workflows/clean-state-gate.yml"
printf 'python3 scripts/clean_state.py --mode precommit\n' > "$SANDBOX/scripts/_smoke_clean_state.sh"

git -C "$SANDBOX" add -A >/dev/null
git -C "$SANDBOX" commit -qm seed >/dev/null

# Install the gate. `worktree` mode asserts hook-installed, and a sandbox with no
# hook would (correctly) fail it — the gate is right, the fixture must be real.
( cd "$SANDBOX" && bash scripts/install_doc_lint_precommit.sh >/dev/null 2>&1 )
grep -q 'clean_state.py' "$SANDBOX/.git/hooks/pre-commit" 2>/dev/null \
  && pass "installer wrote a hook that runs clean_state.py" \
  || fail "installer did not produce a working hook"

run_gate() { ( cd "$SANDBOX" && python3 scripts/clean_state.py "$@" ); }

# ------------------------------------------------- clean_state: the core rule
# CLEAN tree -> pass. This is the "pass-on-clean" half; without it a gate that
# always fails would look just as green in the failing half below.
assert_rc "precommit passes on a clean tree" 0 run_gate --mode precommit

# UNTRACKED file -> fail. THE load-bearing check: this is the exact state that
# made doc_lint red locally + green in CI and taught the repo to use --no-verify.
printf 'junk\n' > "$SANDBOX/stray.png"
assert_rc "precommit FAILS on an unignored untracked file" 1 run_gate --mode precommit

# ...and gitignoring it is an accepted resolution (the other honest state).
printf 'stray.png\n' > "$SANDBOX/.gitignore"
git -C "$SANDBOX" add .gitignore >/dev/null && git -C "$SANDBOX" commit -qm ignore >/dev/null
assert_rc "precommit passes once the file is gitignored" 0 run_gate --mode precommit

# ...and tracking it is the other.
rm -f "$SANDBOX/.gitignore"
git -C "$SANDBOX" rm -q --cached .gitignore >/dev/null 2>&1
git -C "$SANDBOX" add -A >/dev/null && git -C "$SANDBOX" commit -qm track >/dev/null
assert_rc "precommit passes once the file is tracked" 0 run_gate --mode precommit

# STAGED changes must NOT be treated as unclean — a commit is *made* of staged
# changes. A precommit gate that rejected them would block every commit.
printf 'more\n' >> "$SANDBOX/README.md"
git -C "$SANDBOX" add README.md >/dev/null
assert_rc "precommit tolerates staged changes (it is a COMMIT hook)" 0 run_gate --mode precommit

# worktree mode is stricter: a modified/staged tree is NOT safe to branch from.
assert_rc "worktree mode FAILS on a dirty tree" 1 run_gate --mode worktree
git -C "$SANDBOX" commit -qm readme >/dev/null
assert_rc "worktree mode passes on a committed tree" 0 run_gate --mode worktree

# override escape hatch works and is loud
printf 'junk2\n' > "$SANDBOX/stray2.png"
assert_rc "CLEAN_STATE_OVERRIDE=1 lets an unclean tree through" 0 \
  env CLEAN_STATE_OVERRIDE=1 python3 "$SANDBOX/scripts/clean_state.py" --mode precommit
out="$( cd "$SANDBOX" && CLEAN_STATE_OVERRIDE=1 python3 scripts/clean_state.py --mode precommit 2>&1 )"
grep -q 'OVERRIDDEN' <<<"$out" && pass "override announces itself" || fail "override is silent"
rm -f "$SANDBOX/stray2.png"

# junk paths are refused even when the PR would otherwise be legal
assert_rc "junk path (.playwright-mcp) is refused" 1 \
  env -C "$SANDBOX" python3 "$SANDBOX/scripts/clean_state.py" --mode precommit \
    --added-paths .playwright-mcp/page.yml

# ------------------------------------------------------------ ci: generators
# The CI mode's whole job: the COMMITTED tree must already match what the
# generators emit. Proved both ways.
assert_rc "ci mode passes when generated output is committed" 0 run_gate --mode ci

# Commit a STALE generated file (the CI scenario: clean checkout, wrong content).
printf 'GENERATED-CONTENT-STALE\n' > "$SANDBOX/GENERATED.md"
git -C "$SANDBOX" add GENERATED.md >/dev/null
git -C "$SANDBOX" commit -qm "stale generated output" >/dev/null
assert_rc "ci mode FAILS on committed-but-stale generator output" 1 run_gate --mode ci

# Regenerate + commit -> green again.
( cd "$SANDBOX" && bash scripts/sync_toc.sh )
git -C "$SANDBOX" add GENERATED.md >/dev/null
git -C "$SANDBOX" commit -qm "regenerate" >/dev/null
assert_rc "ci mode passes once the generator output is committed" 0 run_gate --mode ci

# KNOWN LIMIT, asserted so it cannot silently change: the delta is masked when the
# file is ALREADY dirty before the run (generator change - pre-existing change =
# empty). CI is authoritative precisely because its pre-run diff is empty. If this
# assertion ever flips, the local check got STRONGER and this comment is stale.
printf 'GENERATED-CONTENT-HAND-EDITED\n' > "$SANDBOX/GENERATED.md"
assert_rc "ci mode is masked when the generated file is already dirty (documented limit)" 0 \
  run_gate --mode ci
git -C "$SANDBOX" checkout -- GENERATED.md 2>/dev/null

# ----------------------------------------------- installer: gate preservation
# THE regression this guards: `cat > hook` clobbered the file, so --force
# silently DELETED the appended kanban-blast-radius gate. A deleted gate is
# indistinguishable from a passing one.
HOOKS="$SANDBOX/.git/hooks"; mkdir -p "$HOOKS"
cat > "$HOOKS/pre-commit" <<'OLD'
#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
"$REPO_ROOT/scripts/doc_lint.py" --staged
# >>> kanban-blast-radius >>>
echo "[blast-radius] SENTINEL"
# <<< kanban-blast-radius <<<
OLD
chmod +x "$HOOKS/pre-commit"

( cd "$SANDBOX" && bash scripts/install_doc_lint_precommit.sh >/dev/null 2>&1 )
grep -q 'SENTINEL' "$HOOKS/pre-commit" \
  && pass "installer PRESERVED the appended blast-radius gate" \
  || fail "installer ATE the appended blast-radius gate (the --force clobber bug)"
grep -q 'clean_state.py' "$HOOKS/pre-commit" \
  && pass "installer upgraded an already-installed hook to add clean-state" \
  || fail "installer no-op'd on an existing hook — upgrade never lands"

# idempotent: a second run must not duplicate the managed block
( cd "$SANDBOX" && bash scripts/install_doc_lint_precommit.sh >/dev/null 2>&1 )
# Count the BEGIN marker, not the invocation line: the hook calls the gate through
# a variable ("$CLEAN_STATE"), so the literal "clean_state.py --mode precommit"
# never appears in the file. Grepping for it would have counted 0 forever and the
# "is it duplicated?" question would have gone permanently unasked.
n="$(grep -cF "$BEGIN_MARK_SMOKE" "$HOOKS/pre-commit")"
[[ "$n" -eq 1 ]] && pass "installer is idempotent (managed block appears exactly once)" \
  || fail "managed block appears ${n}x on re-install (want exactly 1)"
grep -c 'SENTINEL' "$HOOKS/pre-commit" | grep -q '^1$' \
  && pass "blast-radius gate still present exactly once after re-install" \
  || fail "blast-radius gate duplicated or lost on re-install"

# the installed hook must actually BLOCK a commit with an untracked file
printf 'junk\n' > "$SANDBOX/stray3.png"
printf 'x\n' >> "$SANDBOX/README.md"
git -C "$SANDBOX" add README.md >/dev/null
if ( cd "$SANDBOX" && git commit -qm "should be blocked" >/dev/null 2>&1 ); then
  fail "installed hook did NOT block a commit with an untracked file (gate present, not running)"
else
  pass "installed hook BLOCKS a real commit while an untracked file exists"
fi

# ============================================================================
# Regression assertions — one per defect found by the 2026-07-14 adversarial
# review. Each of these FAILS against the pre-review implementation.
# ============================================================================

# R1 — installer must work inside a git WORKTREE, where `.git` is a FILE and
# "$REPO_ROOT/.git/hooks" is literally `Not a directory`. The original installer
# was unusable in the exact place this repo is developed.
git -C "$SANDBOX" worktree add -q "$TMP/wt" -b wt-probe >/dev/null 2>&1
if [[ -d "$TMP/wt" ]]; then
  if ( cd "$TMP/wt" && bash scripts/install_doc_lint_precommit.sh >/dev/null 2>&1 ); then
    pass "installer runs inside a git worktree (.git is a file)"
  else
    fail "installer FAILS inside a worktree — \$REPO_ROOT/.git/hooks is 'Not a directory'"
  fi
  # hooks are shared via \$GIT_COMMON_DIR: installing anywhere covers every worktree
  ( cd "$TMP/wt" && python3 scripts/clean_state.py --mode worktree >/dev/null 2>&1 ) \
    && pass "worktree sees the shared hook as installed" \
    || fail "hook-installed false-negative inside a worktree"
fi

# R2 — the docs/**/*.md remedy must NOT say "gitignore it". doc_lint uses rglob,
# which ignores .gitignore, so an ignored .md STILL trips DOC-LINT-020 and still
# blocks every commit. Advertising that remedy sends the dev in a circle.
mkdir -p "$SANDBOX/docs"
printf 'x\n' > "$SANDBOX/docs/orphan.md"
out="$( cd "$SANDBOX" && python3 scripts/clean_state.py --mode precommit 2>&1 )"
if grep -q 'docs/orphan.md' <<<"$out" && ! grep -A2 'docs/orphan.md' <<<"$out" | grep -qi 'add to .gitignore'; then
  pass "docs/*.md remedy does NOT advertise the gitignore dead-end"
else
  fail "docs/*.md still told to 'gitignore it' — doc_lint rglob ignores .gitignore, so it stays red"
fi
grep -q 'rglob' <<<"$out" && pass "remedy explains WHY gitignore fails there" || true
rm -rf "$SANDBOX/docs"

# R3 — CLEAN_STATE_OVERRIDE must NOT green the CI gate. An escape hatch that
# greens the authoritative gate is a hole, not a hatch.
printf 'STALE\n' > "$SANDBOX/GENERATED.md"
git -C "$SANDBOX" add GENERATED.md >/dev/null; git -C "$SANDBOX" commit -qm stale2 >/dev/null
rc=0; ( cd "$SANDBOX" && CLEAN_STATE_OVERRIDE=1 python3 scripts/clean_state.py --mode ci >/dev/null 2>&1 ) || rc=$?
[[ "$rc" -eq 1 ]] && pass "CLEAN_STATE_OVERRIDE is IGNORED in --mode ci" \
  || fail "CLEAN_STATE_OVERRIDE greened the CI gate (rc=$rc) — that is a hole"
( cd "$SANDBOX" && bash scripts/sync_toc.sh ); git -C "$SANDBOX" add -A >/dev/null
git -C "$SANDBOX" commit -qm regen2 >/dev/null

# R4 — junk paths must be caught AT COMMIT TIME, not only in CI against a PR diff.
# Previously JUNK_PATTERNS only ran when --added-paths was passed, i.e. never at
# the one moment junk actually appears in a tree.
mkdir -p "$SANDBOX/.playwright-mcp"; printf 'challstr\n' > "$SANDBOX/.playwright-mcp/page.yml"
assert_rc "junk path caught in precommit with NO --added-paths" 1 run_gate --mode precommit
rm -rf "$SANDBOX/.playwright-mcp"

# R5 — hook-wired must not be satisfied by its own PROSE. Deleting the hook while
# leaving a comment that mentions it must FAIL. A gate validated by its own
# documentation is not a gate.
cp "$SANDBOX/.pre-commit-config.yaml" "$TMP/cfg.bak"
printf '# the clean-state hook (id: clean-state) used to live here\nrepos: []\n' \
  > "$SANDBOX/.pre-commit-config.yaml"
assert_rc "hook-wired FAILS when only a COMMENT mentions clean-state" 1 run_gate --mode ci
cp "$TMP/cfg.bak" "$SANDBOX/.pre-commit-config.yaml"

# R6 — --uninstall actually removes the hook (it used to grep for a literal the
# template no longer contains, so it was a permanent no-op that reported success).
( cd "$SANDBOX" && bash scripts/install_doc_lint_precommit.sh >/dev/null 2>&1 )
( cd "$SANDBOX" && bash scripts/install_doc_lint_precommit.sh --uninstall >/dev/null 2>&1 )
[[ -f "$SANDBOX/.git/hooks/pre-commit" ]] \
  && fail "--uninstall is a no-op — hook still present" \
  || pass "--uninstall actually removes the hook"
( cd "$SANDBOX" && bash scripts/install_doc_lint_precommit.sh >/dev/null 2>&1 )

# R7 — porcelain parsing must survive paths with spaces (core.quotepath C-quotes
# them; naive line-splitting names a file that does not exist on disk).
printf 'x\n' > "$SANDBOX/a file with spaces.txt"
out="$( cd "$SANDBOX" && python3 scripts/clean_state.py --mode precommit 2>&1 )"
grep -q 'a file with spaces.txt' <<<"$out" \
  && pass "untracked path with spaces is reported verbatim (-z parsing)" \
  || fail "path with spaces was mangled by porcelain parsing"
rm -f "$SANDBOX/a file with spaces.txt"

# ============================================================================
# Round-2 regressions — defects the adversarial review found in the ALREADY
# COMMITTED gate (b04ce60b). Each fails against that commit.
# ============================================================================

# R8 — exit-code contract. A malformed .pre-commit-config.yaml raised yaml.YAMLError
# straight through the narrow `except (RuntimeError, OSError)` as an uncaught
# traceback with exit 1 — which is the UNCLEAN code, indistinguishable from a real
# finding. The module docstring promises "never a traceback; exit 2".
cp "$SANDBOX/.pre-commit-config.yaml" "$TMP/cfg.bak2"
printf 'repos: [ unclosed\n' > "$SANDBOX/.pre-commit-config.yaml"
out="$( cd "$SANDBOX" && python3 scripts/clean_state.py --mode ci 2>&1 )"; rc=$?
if [[ "$rc" -eq 2 ]] && ! grep -q 'Traceback' <<<"$out"; then
  pass "malformed YAML -> exit 2, no traceback (contract honored)"
else
  fail "malformed YAML -> rc=$rc $(grep -q Traceback <<<"$out" && echo '+ TRACEBACK') — contract says 2, never a traceback"
fi
cp "$TMP/cfg.bak2" "$SANDBOX/.pre-commit-config.yaml"

# R9 — DELETION is the easiest rot. The anti-rot check guarded each file with
# `if path.exists():`, so deleting the installer (or the CI workflow) made the
# check pass cheerfully. "Absent" was treated as "fine".
mv "$SANDBOX/scripts/install_doc_lint_precommit.sh" "$TMP/installer.bak"
assert_rc "hook-wired FAILS when the installer is DELETED" 1 run_gate --mode ci
mv "$TMP/installer.bak" "$SANDBOX/scripts/install_doc_lint_precommit.sh"
mv "$SANDBOX/.github/workflows/clean-state-gate.yml" "$TMP/wf.bak"
assert_rc "hook-wired FAILS when the CI workflow is DELETED" 1 run_gate --mode ci
mv "$TMP/wf.bak" "$SANDBOX/.github/workflows/clean-state-gate.yml"

# R10 — junk-paths was a STRUCTURAL NO-OP for the case it exists for: both patterns
# are gitignored, so they never appear as untracked. The failure that matters is
# junk that is ALREADY TRACKED — in history, visible to CI, and nobody would know.
mkdir -p "$SANDBOX/.playwright-mcp"; printf 'challstr\n' > "$SANDBOX/.playwright-mcp/page.yml"
git -C "$SANDBOX" add -f .playwright-mcp/page.yml >/dev/null 2>&1
git -C "$SANDBOX" commit -qm "junk lands in history" >/dev/null 2>&1
printf '.playwright-mcp/\n' >> "$SANDBOX/.gitignore"   # ignored AND tracked: the blind spot
git -C "$SANDBOX" add .gitignore >/dev/null; git -C "$SANDBOX" commit -qm ign >/dev/null
assert_rc "junk-path caught when ALREADY TRACKED (gitignored, so invisible to porcelain)" 1 \
  run_gate --mode precommit
git -C "$SANDBOX" rm -q --cached .playwright-mcp/page.yml >/dev/null
git -C "$SANDBOX" commit -qm "untrack junk" >/dev/null
rm -rf "$SANDBOX/.playwright-mcp"
assert_rc "clean once the junk is untracked" 0 run_gate --mode precommit

printf '\n[smoke] %s\n' "$( ((FAIL == 0)) && echo 'ALL ASSERTIONS PASS' || echo "$FAIL ASSERTION(S) FAILED" )"
exit $((FAIL > 0))
