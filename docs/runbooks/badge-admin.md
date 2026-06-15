---
title: "Badge admin runbook (signing-key custody + rotation)"
status: active
owner: "@EdwardTang"
created: 2026-06-15
updated: 2026-06-15
type: reference
scope: packages/agentdex_arena
layer: service
cross_cutting: false
enforced_by:
  - claim: "BadgeAuthority fails-closed boot when ARENA_BADGE_SIGNING_KEY_HEX is missing or malformed"
    test: "packages/agentdex_arena/tests/test_badge_auth.py::test_boot_fails_closed_when_env_unset + ::test_boot_fails_closed_on_malformed_key"
  - claim: "POST /badge/mint runs membership gate + per-agent quota before sign_badge (call order locked in CLAUDE.md)"
    test: "packages/agentdex_arena/tests/test_badge_mint_endpoint.py::test_badge_mint_rejects_free_tier_owner + ::test_badge_mint_returns_signed_token_for_paid_owner + ::test_badge_mint_spends_quota_per_call"
  - claim: "Operator-only key-custody surface absent from every agent-facing doc (SKILL.md, ENROLLMENT.md, METHODOLOGY.md)"
    test: "packages/agentdex_arena/tests/test_membership_primitive.py::test_all_agent_facing_surfaces_do_not_mention_badge_admin_surface"
---

# Badge admin runbook (signing-key custody + rotation)

> **NOT for agent clients.** This runbook documents an operator-only surface.
> The `ARENA_BADGE_SIGNING_KEY_HEX` env var, its rotation procedure, and
> emergency revocation MUST NEVER appear in `SKILL.md`, `ENROLLMENT.md`,
> `METHODOLOGY.md`, or any agent-facing documentation. The agent-visible
> badge-mint endpoint (`POST /badge/mint`) IS public-by-design; only the
> key-custody surface stays in operator docs. See ADR-0011 §3 (admin-surface
> invisibility), §11c (badge design), and the design spec at
> `docs/references/2026-06-14-arena-verified-badge-svg-design.md` (D2 key
> custody choice ratified 2026-06-15).

## What this is

`BadgeAuthority` mints Ed25519-signed verified-badge tokens (`POST
/badge/mint`) and exposes the public verifier endpoints (`GET
/badge/<agent>/<token>.svg`, `/verify`). The signing key is a 32-byte
Ed25519 seed delivered via env var `ARENA_BADGE_SIGNING_KEY_HEX`, **separate
from `ARENA_SIGNING_KEY_HEX`** so a badge-key leak does NOT compromise
consent tokens (and vice versa).

Same fail-closed boot posture as `AdminAuthority`: missing or malformed env
raises `BadgeAuthError` and kills the container at startup. No degraded
runtime mode.

## Generating the badge signing key (deploy-time, ONCE)

On your laptop only — `op` (1Password CLI) is allowed at deploy-time to
store the plaintext securely. The runtime container has zero `op`
dependency.

```bash
# 1. Generate a 32-byte Ed25519 seed (64 hex chars, lowercase)
BADGE_KEY=$(python3 -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; print(Ed25519PrivateKey.generate().private_bytes_raw().hex())")

# 2. Store the seed in 1Password (you'll need it for rotation; never paste anywhere else)
op item create --category="API Credential" \
  --title="agentdex arena badge signing key (prod)" \
  --vault="<your-vault>" \
  credential="$BADGE_KEY" \
  notesPlain="ADR-0011 11c badge signing seed (Ed25519, 32B raw hex). Lives ONLY in this op item + Koyeb env ARENA_BADGE_SIGNING_KEY_HEX. Separate from ARENA_SIGNING_KEY_HEX (consent) on purpose — D2 blast-radius isolation. Rotation procedure: runbooks/badge-admin.md."

# 3. Verify the key shape locally before pushing to Koyeb (catches typos early)
python3 -c "from agentdex_arena.badge_auth import BadgeAuthority; BadgeAuthority(signing_key_hex='$BADGE_KEY'); print('badge key valid')"
```

## Setting the README-embed base URL (deploy-time, optional)

The `/badge/mint` response carries `svg_url` + `verify_url` for paid owners to paste into third-party READMEs. Those URLs must be **absolute** — otherwise the README render resolves them against the README host (e.g. `github.com/badge/...`) and the embed breaks. The arena defaults to `https://agentdex.ai-builders.space` when the env is unset; production deploys work out of the box.

```bash
# Default (matches the production hostname; only set this explicitly if you
# want to be explicit about the deploy URL in your operator runbook):
koyeb service update agentdex --env ARENA_PUBLIC_BASE_URL="https://agentdex.ai-builders.space"

# Staging / preview / fork: point at the deploy URL the owner will paste
# from. Any agent minted on this gateway gets URLs under this host.
koyeb service update agentdex --env ARENA_PUBLIC_BASE_URL="https://staging.your-deploy.example"

# Integration test harness that resolves URLs against an injected base:
# explicitly set to empty so /badge/mint emits relative paths.
koyeb service update agentdex --env ARENA_PUBLIC_BASE_URL=""
```

The constructor `rstrip("/")`s the value so a trailing slash will not produce double-slashed README URLs.

## Setting the env var on Koyeb (deploy-time, ONCE)

The container reads `ARENA_BADGE_SIGNING_KEY_HEX` at boot. If missing or
malformed, `BadgeAuthority.__init__` raises and the container exits
immediately — operator notices via Koyeb's health-check failure.

```bash
# Push the seed to Koyeb as a secret env var. The current Koyeb CLI
# (per https://www.koyeb.com/docs/build-and-deploy/environment-variables)
# interpolates a secret into an env var via `{{ secret.<NAME> }}`. The
# older `@<NAME>` shorthand is silently treated as a literal value by
# current builds — the container would read `ARENA_BADGE_SIGNING_KEY_HEX=
# @arena-badge-signing-key-hex`, fail the 64-lowercase-hex validator,
# and stay fail-closed even after the secret exists.
koyeb secret create arena-badge-signing-key-hex --value "$BADGE_KEY"
koyeb service update agentdex --env ARENA_BADGE_SIGNING_KEY_HEX="{{ secret.arena-badge-signing-key-hex }}"

# Container redeploys; on success: `koyeb service logs agentdex` shows the
# usual gateway startup, NO BadgeAuthError. On failure: the logs surface
# "ARENA_BADGE_SIGNING_KEY_HEX not set" or "must be a 64-char lowercase
# ed25519 hex seed" — fix the secret value (or the interpolation shape)
# and re-roll.
```

## Verifying the key is live

The `/badge/<agent>/<token>/verify` endpoint surfaces the deployed
`BadgeAuthority.public_key_hex` directly. Compare against the derivation
from your local plaintext to confirm the right seed is in production:

```bash
# Locally: compute the expected public key from the plaintext seed
PUB_EXPECTED=$(python3 -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; print(Ed25519PrivateKey.from_private_bytes(bytes.fromhex('$BADGE_KEY')).public_key().public_bytes_raw().hex())")

# Mint a probe badge_token via the admin's own owner (requires membership).
# Hit /verify and read the badge_public_key_hex back.
PUB_DEPLOYED=$(curl -s "https://agentdex.ai-builders.space/badge/<your-agent>/<token>/verify" | python3 -c "import sys, json; print(json.load(sys.stdin)['badge_public_key_hex'])")

# Diff: equal → live; mismatch → wrong seed deployed, rotate immediately.
[ "$PUB_EXPECTED" = "$PUB_DEPLOYED" ] && echo OK || echo "ROTATE: keys diverge"
```

## Rotating the badge signing key (planned operation)

Same envelope as the admin-token rotation, with one extra invariant: **all
existing badge_tokens issued under the old key become unverifiable
immediately** after the new key deploys. Owners must remint via `POST
/badge/mint` to get a token signed by the new key.

```bash
# 1. Generate NEW seed + store in 1Password under a new title
NEW_BADGE_KEY=$(python3 -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; print(Ed25519PrivateKey.generate().private_bytes_raw().hex())")
op item create --category="API Credential" \
  --title="agentdex arena badge signing key (prod, rotated $(date -u +%Y-%m-%d))" \
  --vault="<your-vault>" \
  credential="$NEW_BADGE_KEY" \
  notesPlain="Replaces previous badge signing seed; existing badges expire on rotation. Old seed item archived (do not delete — needed for incident forensics)."

# 2. Update Koyeb secret
koyeb secret update arena-badge-signing-key-hex --value "$NEW_BADGE_KEY"

# 3. Container redeploys with the new seed. Verify via /verify (above) BEFORE
#    notifying owners — a botched rotation that left the old seed live would
#    silently let attackers continue to mint under the leaked key.

# 4. Notify owners: "All badge URLs minted before <timestamp> are invalid; re-call
#    POST /badge/mint to get a fresh badge_token. Existing membership unchanged."
```

## Emergency revocation (signing key compromise)

If the plaintext seed is suspected leaked (e.g., 1Password breach, log file
caught the value during a misconfiguration, malicious commit reverted),
treat it as a fire drill:

```bash
# 1. Generate a fresh seed (see rotation procedure above) — DO NOT reuse any
#    previous seed; the old one is permanently burned.
# 2. Deploy the new seed via koyeb secret update.
# 3. Verify the new public key on /verify before declaring the rotation complete.
# 4. Notify owners that EVERY badge URL issued before <timestamp> is invalid.
# 5. Open an incident-log entry citing the time the leak was detected and the
#    `kid` of the burned key (currently always "badge-v1" — V2 multi-kid
#    rotation lands when the V2 SDD-versioned schema does).
```

The badge-render endpoints have NO key-rollover grace window — by design:
the spec D2 mandates blast-radius isolation and a leaked badge key is a
trust-domain compromise that callers must learn about. A grace window
would silently let a compromised key keep signing rendered badges.

## Q2 funnel log shape

`GET /badge/<agent>/<token>.svg` emits one `badge_fetch` log record per
request. The record uses the standard-library `logging.LogRecord` extra
fields — NOT free-form string interpolation — so a structured log
backend (Datadog / Loki / Koyeb's built-in JSON ingester) gets typed
attributes the V2 aggregation endpoint can read without re-parsing.

Fields on every `badge_fetch` record:

| Field | Type | Source |
|-------|------|--------|
| `event` | string `"badge_fetch"` | the literal event key |
| `agent_name` | string | the validated path param |
| `referer_host` | string | `urlparse(Referer).hostname.lower()` — empty when the header is missing or malformed |
| `badge_token_kid` | string `"badge-v1"` (today) | the `kid` field from the signed payload — distinguishes future rotations |

The `LogRecord.message` is the literal string `"badge_fetch"` — values
NEVER appear in the formatted text, so a space in `agent_name`
(`sanitize_name` allows them) cannot make a grep-parse ambiguous (the
pre-fix shape was `badge_fetch agent=My Bot referer_host=...`).

## Health checks

```bash
# 1. Confirm the badge endpoints exist (route hit, not auth-pass)
curl -s -o /dev/null -w "%{http_code}\n" \
  "https://agentdex.ai-builders.space/badge/no-such-agent/garbage.svg"
# Expected: 404 (route fired + opaque error path, matches D7 anti-enumeration)
# If 405 — route not deployed; if 503 — BadgeAuthority not configured
# (ARENA_BADGE_SIGNING_KEY_HEX missing or malformed); if 500 — bug, surface
# the gateway error log with the matching `arena error (ref=…)` id.

curl -s -o /dev/null -w "%{http_code}\n" \
  "https://agentdex.ai-builders.space/badge/no-such-agent/garbage/verify"
# Expected: 404 (same opaque error path as the SVG route).
```

## Operational invariants (ADR-0011 §3, §11c)

These hold across every deploy / rotation cycle — break any of them and
the V1 binding is broken:

- **Badge signing key is SEPARATE from consent signing key.** The two envs
  (`ARENA_BADGE_SIGNING_KEY_HEX`, `ARENA_SIGNING_KEY_HEX`) MUST hold
  different 32-byte seeds. Cross-key reuse defeats blast-radius isolation.
- **Plaintext seed NEVER lives on the server.** Only the Koyeb env carries
  it; nothing else (no logs, no files, no events, no commit). The runtime
  container has no `op` dependency.
- **Badge mint is membership-gated.** `POST /badge/mint` runs the
  CLAUDE.md call order `verify(scope=badge_mint)` → `verify_membership` →
  `spend_quota` → `sign_badge`. A free-tier owner whose token carries
  `badge_mint` scope still gets a 403 "membership required" at step 2.
- **Badge render is anti-pay-to-rank.** Both the SVG and verify endpoints
  pull rating data from `gateway.ladder_public()` — the same source as
  `/ladder`. No membership-derived rating boost, no paid-tier rating
  branch. A regression that altered the badge rating based on tier would
  diverge from `/ladder` and fail the Q5 property test.
- **The badge_token TTL is 30 days, not renewable in-place.** A revoked
  member loses the ability to mint new badges immediately; their existing
  badge_tokens render for up to 30 more days. Industry-standard cert
  expiry semantic; matches the monthly membership cycle (D3 ratified).
- **The signing seed never rolls forward without operator action.** Key
  rotation requires a deliberate `koyeb secret update`; there is no time-
  based rollover. This is on-purpose so a stable `public_key_hex` can be
  pinned by third-party verifiers between intentional rotations.

## Common gotchas

- **Uppercase hex** in the env value → boot failure. The validator wants
  64 lowercase hex chars (`[0-9a-f]{64}`); paste from `python -c …` not
  from a tool that uppercases.
- **Trailing whitespace** in the secret value → also fails the regex.
  Strip before pasting.
- **Confusing the badge seed with the consent seed.** Both are 64 hex
  chars; they are NOT interchangeable. The op item titles +
  `notesPlain` field MUST distinguish them clearly.

## References

- ADR-0011 §3 (anti-pay-to-rank invariant + admin-surface invisibility)
- ADR-0011 §11c (verified-badge SVG paid feature, design ratification)
- Design spec: `docs/references/2026-06-14-arena-verified-badge-svg-design.md`
  D2 key custody (separate env, D2 ratified 2026-06-15) / D3 30-day TTL /
  D7 anti-enumeration
- Related runbook: `docs/runbooks/membership-admin.md` (the `/admin/grant-
  membership` surface that gates `POST /badge/mint`)
