#!/usr/bin/env bash
# Smoke: tiny_pr_gate.py — deterministic LOC + Indivisible-Unit/Scope contract.
# Also proves trusted-base mode selection + static workflow embedding.
# No network. Exit 0 only when every fixture assertion holds.
set -uo pipefail
ROOT="${TINY_PR_GATE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
GATE="$(cd "$(dirname "$0")" && pwd)/tiny_pr_gate.py"
WORKFLOW="$ROOT/.github/workflows/tiny-pr-gate.yml"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAIL=0
fail() { printf '[smoke] FAIL %s\n' "$*" >&2; FAIL=$((FAIL + 1)); }
pass() { printf '[smoke] PASS %s\n' "$*"; }
exception_body() { printf 'Indivisible-Unit: %s\nIndivisible-Scope: %s\n' "$1" "$2"; }

# run name expect_pass body numstat
# expect_pass: 1 = must exit 0 + print PASS; 0 = must exit 1 + print FAIL
run() {
  local name="$1" expect_pass="$2" body="$3" numstat="$4"
  local out rc
  printf '%s' "$body" >"$TMP/body.txt"
  printf '%s' "$numstat" >"$TMP/numstat.txt"
  set +e
  out="$(python3 "$GATE" --body-file "$TMP/body.txt" --numstat-file "$TMP/numstat.txt" 2>&1)"
  rc=$?
  set -e
  if [[ "$expect_pass" -eq 1 ]]; then
    if [[ "$rc" -eq 0 && "$out" == tiny-pr-gate:\ PASS* ]]; then
      pass "$name"
    else
      fail "$name (expected PASS, rc=$rc out=$out)"
    fi
  else
    if [[ "$rc" -eq 1 && "$out" == tiny-pr-gate:\ FAIL* ]]; then
      pass "$name"
    else
      fail "$name (expected FAIL, rc=$rc out=$out)"
    fi
  fi
}

# --- fixtures ---------------------------------------------------------------

PR687_NUMSTAT=$'5\t0\tpackages/agentdex_cli/pyproject.toml\n'
PR687_NUMSTAT+=$'5\t0\tpackages/agentdex_cli/src/agentdex_cli/cli.py\n'
PR687_NUMSTAT+=$'2\t2\tpackages/agentdex_cli/src/agentdex_cli/evolve_cmd.py\n'
PR687_NUMSTAT+=$'492\t0\tpackages/agentdex_cli/src/agentdex_cli/evolve_submit_cmd.py\n'
PR687_NUMSTAT+=$'731\t0\tpackages/agentdex_cli/tests/test_evolve_submit_cmd.py\n'
PR687_NUMSTAT+=$'27\t0\tuv.lock\n'

PR687_SCOPE="packages/agentdex_cli/pyproject.toml packages/agentdex_cli/src/agentdex_cli/cli.py packages/agentdex_cli/src/agentdex_cli/evolve_cmd.py packages/agentdex_cli/src/agentdex_cli/evolve_submit_cmd.py packages/agentdex_cli/tests/test_evolve_submit_cmd.py uv.lock"

PR687_BODY_LOOSE=$'feat(cli): submit measured candidates to frontier\n\n'
PR687_BODY_LOOSE+=$'Local-review: validates durable measurements before the collaborative Bene gate,\n'
PR687_BODY_LOOSE+=$'preserves trust and promotion receipts, and exports frontier state atomically.\n'

# Substantive reason: >=40 chars, >=6 words, standalone "because", non-placeholder.
PR687_UNIT="Cannot split frontier-submit wire and tests because promotion receipts would strand incomplete"
PR687_BODY_OK=$'feat(cli): submit measured candidates to frontier\n\n'
PR687_BODY_OK+="Indivisible-Unit: ${PR687_UNIT}"$'\n'
PR687_BODY_OK+="Indivisible-Scope: ${PR687_SCOPE}"$'\n'

# 1) #687 shape + Local-review body => FAIL
run pr687_loose 0 "$PR687_BODY_LOOSE" "$PR687_NUMSTAT"

# 2) same shape with exact reason + exact scope => PASS
run pr687_ok 1 "$PR687_BODY_OK" "$PR687_NUMSTAT"

# 3a) loose Indivisible-Unit reason => FAIL
run loose_unit 0 $'Indivisible-Unit: indivisible\n'"Indivisible-Scope: ${PR687_SCOPE}"$'\n' "$PR687_NUMSTAT"

# 3b) empty / missing unit with scope present => FAIL
run empty_unit 0 $'Indivisible-Unit: \n'"Indivisible-Scope: ${PR687_SCOPE}"$'\n' "$PR687_NUMSTAT"

# 3c) missing scope path => FAIL
run missing_scope 0 "$(exception_body "$PR687_UNIT" "packages/agentdex_cli/pyproject.toml uv.lock")" "$PR687_NUMSTAT"

# 3d) extra scope path => FAIL
run extra_scope 0 "$(exception_body "$PR687_UNIT" "${PR687_SCOPE} docs/EXTRA.md")" "$PR687_NUMSTAT"

# 3e) duplicate scope path => FAIL
run dup_scope 0 "$(exception_body "$PR687_UNIT" "${PR687_SCOPE} uv.lock")" "$PR687_NUMSTAT"

# 3f) unsafe changed path => FAIL
run unsafe_path 0 "$(exception_body "$PR687_UNIT" "../etc/passwd a.py")" $'5\t0\ta.py\n50\t0\t../etc/passwd\n'

# 3g) tiny-pr-exempt / bootstrap unit / Local-review as unit => FAIL
for loose in "tiny-pr-exempt" "bootstrap unit" "Local-review"; do
  run "loose_${loose// /_}" 0 "$(exception_body "$loose" "$PR687_SCOPE")" "$PR687_NUMSTAT"
done

# 3h) reason quality — single token "x" with exact scope => FAIL
run reason_x 0 $'Indivisible-Unit: x\n'"Indivisible-Scope: ${PR687_SCOPE}"$'\n' "$PR687_NUMSTAT"

# 3i) short multiword text (has because but too short / too few words) => FAIL
run reason_short_multiword 0 $'Indivisible-Unit: bad because x\n'"Indivisible-Scope: ${PR687_SCOPE}"$'\n' "$PR687_NUMSTAT"

# 3j) long text without standalone because => FAIL
run reason_long_no_because 0 $'Indivisible-Unit: this is a long enough multiword reason missing the causal token entirely\n'"Indivisible-Scope: ${PR687_SCOPE}"$'\n' "$PR687_NUMSTAT"

# 3k) whitespace padding must not inflate a thin reason => FAIL
PADDED="x$(printf '%80s' '')"
run reason_whitespace_pad 0 "$(exception_body "$PADDED" "$PR687_SCOPE")" "$PR687_NUMSTAT"

# 3l) repeated/generic padding cannot manufacture a substantive reason
run reason_repeated_padding 0 "$(exception_body "alpha alpha alpha alpha alpha alpha because alpha alpha alpha alpha" "$PR687_SCOPE")" "$PR687_NUMSTAT"
run reason_generic_padding 0 "$(exception_body "placeholder atomic required because necessary generic reason exception" "$PR687_SCOPE")" "$PR687_NUMSTAT"

# 3m) placeholder / generic reasons => FAIL
for ph in "placeholder" "TODO" "n/a" "generic reason" "cannot split"; do
  run "placeholder_${ph// /_}" 0 "$(exception_body "$ph" "$PR687_SCOPE")" "$PR687_NUMSTAT"
done

# 3n) placeholder glued around because still fails
run placeholder_around_because 0 $'Indivisible-Unit: placeholder because TODO\n'"Indivisible-Scope: ${PR687_SCOPE}"$'\n' "$PR687_NUMSTAT"

# 4) <=50 total LOC => PASS (no exception)
run within_limit 1 "no markers needed" $'10\t5\ta.py\n20\t5\tb.py\n'
run boundary_50 1 "no markers" $'30\t20\ta.py\n'

# 5) additions AND deletions both count (30+21=51 fails without exception)
run adds_and_dels 0 "no markers" $'30\t21\ta.py\n'

# Base advancement after a PR forks must not inflate candidate LOC.
MERGE_REPO="$TMP/merge-base-repo"
git init -q "$MERGE_REPO"
git -C "$MERGE_REPO" config user.email smoke@example.invalid
git -C "$MERGE_REPO" config user.name smoke
printf 'seed\n' >"$MERGE_REPO/seed.txt"
git -C "$MERGE_REPO" add seed.txt && git -C "$MERGE_REPO" commit -qm seed
BASE_BRANCH="$(git -C "$MERGE_REPO" branch --show-current)"
git -C "$MERGE_REPO" branch feature
seq 1 60 >"$MERGE_REPO/base-only.txt"
git -C "$MERGE_REPO" add base-only.txt && git -C "$MERGE_REPO" commit -qm base-advanced
BASE_TIP="$(git -C "$MERGE_REPO" rev-parse HEAD)"
git -C "$MERGE_REPO" checkout -q feature
printf 'candidate\n' >"$MERGE_REPO/candidate.txt"
git -C "$MERGE_REPO" add candidate.txt && git -C "$MERGE_REPO" commit -qm candidate
HEAD_TIP="$(git -C "$MERGE_REPO" rev-parse HEAD)"
MERGE_BASE="$(git -C "$MERGE_REPO" merge-base "$BASE_TIP" "$HEAD_TIP")"
run merge_base_candidate_only 1 "no markers" "$(git -C "$MERGE_REPO" diff --numstat "$MERGE_BASE" "$HEAD_TIP")"
run two_tip_inflates_scope 0 "no markers" "$(git -C "$MERGE_REPO" diff --numstat "$BASE_BRANCH" "$HEAD_TIP")"

# binary fail-closed without exception; with exact exception => PASS
BINARY_UNIT="Vendored binary must ship with manifest because splitting leaves unloadable assets"
run binary_no_exc 0 "no markers" $'-\t-\tblob.bin\n5\t0\ta.py\n'
run binary_ok 1 "$(exception_body "$BINARY_UNIT" "blob.bin a.py")" $'-\t-\tblob.bin\n5\t0\ta.py\n'

# unparseable line fail-closed
run unparseable 0 $'Indivisible-Unit: x\nIndivisible-Scope: a.py\n' $'not-a-numstat-line\n'

# --- bootstrap mode selection (matches workflow truth table) ----------------
check_mode() {
  local name="$1" has_gate="$2" has_smoke="$3" expect="$4"
  local out rc
  set +e
  out="$(
    python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('tiny_pr_gate', sys.argv[1])
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
print(mod.resolve_execution_mode(base_has_gate=bool(int(sys.argv[2])), base_has_smoke=bool(int(sys.argv[3]))))
" "$GATE" "$has_gate" "$has_smoke" 2>&1
  )"
  rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    fail "$name (resolver raised rc=$rc out=$out)"
    return
  fi
  if [[ "$out" == "$expect" ]]; then
    pass "$name"
  else
    fail "$name (expected mode=$expect got=$out)"
  fi
}

check_mode mode_base_present 1 1 trusted_base
check_mode mode_base_absent 0 0 fail_closed_partial
check_mode mode_partial_gate_only 1 0 fail_closed_partial
check_mode mode_partial_smoke_only 0 1 fail_closed_partial

# Static workflow smoke: proves trusted-base execution and head is fetched.
if [[ ! -f "$WORKFLOW" ]]; then
  fail "workflow_missing:$WORKFLOW"
else
  for needle in \
    "fail_closed_partial" \
    "trusted_base" \
    "pull_request_target" \
    "git fetch --no-tags origin" \
    "git merge-base" \
    "smoke_root=" \
    "TINY_PR_GATE_ROOT" \
    "base_has_gate" \
    "base_has_smoke" \
    "refusing candidate-head fallback"
  do
    if grep -Fq "$needle" "$WORKFLOW"; then
      pass "workflow_has:${needle}"
    else
      fail "workflow_missing_needle:${needle}"
    fi
  done
  # Ensure smoke + evaluate use resolved paths (not hard-coded base-only).
  if grep -Fq 'steps.resolve.outputs.smoke_sh' "$WORKFLOW" \
    && grep -Fq 'steps.resolve.outputs.gate_py' "$WORKFLOW"; then
    pass "workflow_uses_resolved_paths"
  else
    fail "workflow_does_not_use_resolved_gate_smoke_outputs"
  fi
  if grep -Fq "git diff --numstat \"\$BASE_SHA\" \"\$HEAD_SHA\"" "$WORKFLOW"; then
    fail "workflow_uses_two_tip_diff"
  else
    pass "workflow_uses_merge_base_diff"
  fi
fi

# Execute the full smoke from the exact relocated bootstrap layout once.
if [[ "${TINY_PR_GATE_SKIP_RELOCATION_CHECK:-0}" != "1" ]]; then
  RELOCATED="$TMP/relocated"
  mkdir -p "$RELOCATED/.github/workflows"
  cp "$GATE" "$RELOCATED/tiny_pr_gate.py"
  cp "$0" "$RELOCATED/_smoke_tiny_pr_gate.sh"
  cp "$WORKFLOW" "$RELOCATED/.github/workflows/tiny-pr-gate.yml"
  set +e
  relocated_out="$(TINY_PR_GATE_ROOT="$RELOCATED" TINY_PR_GATE_SKIP_RELOCATION_CHECK=1 bash "$RELOCATED/_smoke_tiny_pr_gate.sh" 2>&1)"
  relocated_rc=$?
  set -e
  if [[ "$relocated_rc" -eq 0 ]]; then pass relocated_bootstrap_layout; else fail "relocated_bootstrap_layout rc=$relocated_rc out=$relocated_out"; fi
fi

if [[ "$FAIL" -ne 0 ]]; then
  printf '[smoke] %s assertion(s) failed\n' "$FAIL" >&2
  exit 1
fi
printf '[smoke] all tiny-pr-gate assertions passed\n'
exit 0
