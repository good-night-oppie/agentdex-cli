#!/usr/bin/env bash
# detect_secrets_no_drift.sh — wraps `detect-secrets-hook` so the
# `generated_at` timestamp in `.secrets.baseline` does not pollute every
# CI run with a "baseline modified" exit-3.
#
# DEFERRED.md BASELINE-DRIFT (closed by this script): the upstream
# detect-secrets hook rewrites the baseline on every invocation and
# bumps `generated_at` to the wall-clock time. The exit-3 it raises
# afterwards ("Please git add .secrets.baseline") fires every time,
# masking real findings.
#
# Behavior:
#   1. Snapshot the baseline's content-hash WITHOUT `generated_at`.
#   2. Run `detect-secrets-hook --baseline <path>` (forwards extra args).
#   3. Strip `generated_at` from the (possibly rewritten) baseline.
#   4. Re-hash post-strip; if the only diff vs step 1 was the timestamp,
#      suppress the hook's exit-3. Real new-finding exits (1/2) are
#      preserved.
#
# Invoked from `.pre-commit-config.yaml` as a local `language: system`
# hook so the same script runs locally + in CI without an extra wrapper.

set -u

BASELINE="${BASELINE_PATH:-.secrets.baseline}"

content_hash() {
  # Hash the baseline's content WITHOUT the `generated_at` value so the
  # timestamp does not influence diff detection. The parse/dump is only
  # for hashing — the on-disk file format is preserved by the
  # string-level strip below.
  python3 - "$1" <<'PY'
import hashlib, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
if not p.is_file():
    print("missing")
    sys.exit(0)
data = json.loads(p.read_text())
data.pop("generated_at", None)
print(hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest())
PY
}

strip_generated_at() {
  # String-level removal preserves the upstream `detect-secrets`
  # key ordering + indentation (json.dumps would alphabetize keys and
  # churn every line). The terminal `,\n  "generated_at": "<iso>"\n}`
  # block is matched + replaced with `\n}` — the only safe form
  # because `generated_at` is always emitted LAST by detect-secrets.
  python3 - "$1" <<'PY'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1])
if not p.is_file():
    sys.exit(0)
text = p.read_text()
new = re.sub(
    r',\n\s*"generated_at"\s*:\s*"[^"]*"\s*\n\}\s*$',
    "\n}\n",
    text,
)
if new != text:
    p.write_text(new)
PY
}

pre_hash="$(content_hash "$BASELINE")"

set +e
uv run --no-sync detect-secrets-hook --baseline "$BASELINE" "$@"
rc=$?
set -e

strip_generated_at "$BASELINE"
post_hash="$(content_hash "$BASELINE")"

if [[ "$rc" -eq 3 && "$pre_hash" == "$post_hash" ]]; then
  # Only `generated_at` differed pre vs post; suppress the spurious
  # exit-3 so CI does not flag a baseline that has not really moved.
  rc=0
fi

exit "$rc"
