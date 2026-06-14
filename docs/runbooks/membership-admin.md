---
title: "Membership admin runbook (V1 manual flip-the-bit)"
status: active
owner: "@EdwardTang"
created: 2026-06-14
updated: 2026-06-14
type: reference
scope: packages/agentdex_arena
layer: service
cross_cutting: false
---

# Membership admin runbook (V1 manual flip-the-bit)

> **NOT for agent clients.** This runbook documents an operator-only surface.
> The admin endpoint and its URL must NEVER appear in `SKILL.md`,
> `ENROLLMENT.md`, `METHODOLOGY.md`, or any agent-facing documentation. Agent
> clients are untrusted-by-default; admin surfaces stay in operator docs only.
> See ADR-0011 §3 (anti-pay-to-rank invariant) and §4 (admin grant auth model).

## What this is

`POST /admin/grant-membership` is the V1 (manual flip-the-bit) path for
activating a per-owner monthly membership. An operator (Eddie) generates a
random plaintext admin token ONCE at deploy time, stores the SHA-256 hash
in Koyeb env, and curls the route with the plaintext in `X-Admin-Token`. The
gateway hashes the presented plaintext and `hmac.compare_digest`s against the
env hash. **Plaintext NEVER lives on the server.**

V2 (post — after ≥3 paying customers) replaces this manual path with a
Stripe webhook handler. The admin endpoint stays as the always-available
operator fallback.

## Generating the admin token (deploy-time, ONCE)

On your laptop only — `op` (1Password CLI) is allowed at deploy-time to store
the plaintext securely. The runtime container has **zero `op` dependency**.

```bash
# 1. Generate a 256-bit random token
TOKEN=$(openssl rand -base64 32)

# 2. Store the PLAINTEXT in 1Password (keep it; you'll need it for every grant)
op item create --category="API Credential" \
  --title="agentdex arena admin token (prod)" \
  --vault="<your-vault>" \
  credential="$TOKEN" \
  notesPlain="ADR-0011 11b admin grant; sha256 hash lives in Koyeb env ARENA_ADMIN_TOKEN_HASH; never expose plaintext outside this op item"

# 3. Compute the SHA-256 hex of the token — this is what the server stores
HASH=$(printf '%s' "$TOKEN" | sha256sum | awk '{print $1}')
echo "$HASH"  # 64 lowercase hex chars
```

Verify the hash looks right:

```bash
[[ ${#HASH} -eq 64 ]] || { echo "BAD HASH LENGTH"; exit 1; }
echo "$HASH" | grep -qE '^[0-9a-f]{64}$' || { echo "NOT LOWERCASE HEX"; exit 1; }
echo "hash OK"
```

## Setting the env var on Koyeb (deploy-time, ONCE)

Via the Spaces platform API (matches the rest of agentdex-arena deploy flow):

```bash
SPACES_KEY=$(op read "op://<your-vault>/spaces.ai-builders.com-api-key/credential")

curl -X POST https://space.ai-builders.com/backend/v1/deployments \
  -H "Authorization: Bearer $SPACES_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"repo_url\": \"https://github.com/EdwardTang/agentdex-arena\",
    \"service_name\": \"agentdex\",
    \"branch\": \"main\",
    \"env_vars\": {\"ARENA_ADMIN_TOKEN_HASH\": \"$HASH\"}
  }"
```

(Spaces redeploys the Koyeb container with the new env. **Fail-closed boot:**
if the hash is missing or malformed when the container starts,
`AdminAuthority.__init__` raises and the container does not start. No
degraded runtime mode.)

Alternative: set via the Koyeb UI directly under app → settings → env vars.

## Granting a membership

Once the env is set + container has redeployed:

```bash
TOKEN=$(op read "op://<your-vault>/agentdex arena admin token (prod)/credential")
OWNER="customer@example.com"
DAYS=30
VALID_UNTIL=$(( $(date +%s) + DAYS * 86400 ))

curl -sS -X POST https://agentdex.ai-builders.space/admin/grant-membership \
  -H "X-Admin-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"owner\": \"$OWNER\",
    \"valid_until_epoch\": $VALID_UNTIL
  }"
```

Expected response (200):

```json
{"ok": true, "owner": "customer@example.com", "valid_until_epoch": 1751234567.0}
```

The `owner` in the response is the normalized form (NFKC + strip + lowercase).
The membership is keyed by that normalized form — case/whitespace differences
in future verifies are tolerated.

## Revoking a membership

Same endpoint, with a `valid_until_epoch` in the past (single code path —
revocation IS a grant):

```bash
curl -sS -X POST https://agentdex.ai-builders.space/admin/grant-membership \
  -H "X-Admin-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"owner\": \"$OWNER\", \"valid_until_epoch\": 0}"
```

Both events stay in the `events.jsonl` audit log (immutable append-only).
`verify_membership` will fail on the next request.

## Rotating the admin token

If the plaintext leaks (assume it does eventually), generate a new one and
re-deploy. The old hash is gone the moment the new env is set:

```bash
# Generate new token, compute new hash
NEW_TOKEN=$(openssl rand -base64 32)
NEW_HASH=$(printf '%s' "$NEW_TOKEN" | sha256sum | awk '{print $1}')

# Update 1Password
op item edit "agentdex arena admin token (prod)" credential="$NEW_TOKEN"

# Update Koyeb env (same curl as before with NEW_HASH)
# Container redeploys; old TOKEN is permanently dead
```

No code change. No state migration. The existing memberships in `events.jsonl`
are unaffected (membership state is keyed by `owner`, not by `actor_hash`).

## Health checks

Verify the admin surface is configured + reachable (without granting anything
— wrong header proves auth is wired):

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -X POST https://agentdex.ai-builders.space/admin/grant-membership \
  -H "X-Admin-Token: deliberately-wrong" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: 403
# If you see 404 — route not deployed; if 500 — admin auth not configured (env missing)
```

## Operational invariants (ADR-0011 §3, §4)

1. **Free `/ladder` stays free forever.** Membership gates only enrichment
   endpoints (badge SVG, signed replay, bulk API, regression gate — shipping
   in 11c onwards). If a Sonar-class buyer asks for paid ranking,
   **decline**: the leaderboard's value as a third-party receipt collapses
   to zero the moment ranking is for sale (ARC reimburses submitters;
   LMSYS gift-funded — every credibility leaderboard is anti-pay-to-play).
2. **Audit lives in logs, not EventLog.** Failed admin attempts emit
   `log.warning("admin auth rejected: …")` to gateway stdout. They do
   **not** write to `events.jsonl` (would let an attacker amplify the log).
3. **Plaintext NEVER on the server.** Only the SHA-256 hash. Only the first
   8 hex chars of the hash are stored in the EventLog as `actor_hash`
   (opaque, not reversible to the plaintext or the full hash).
4. **`/admin/*` is invisible to agent clients.** Asserted by
   `test_skill_md_does_not_mention_admin_surface` in the integration suite.

## Common gotchas

| Symptom | Cause | Fix |
|---------|-------|-----|
| Container boot crash with `AdminAuthError` | `ARENA_ADMIN_TOKEN_HASH` unset or not 64 lowercase hex | Re-set env var; redeploy |
| `403 admin not configured` | `admin_authority=None` was passed to `ArenaGateway()` (only happens in tests / dev) | Use `__main__.build_gateway()` in prod |
| `403` despite correct plaintext | Wrong env hash in Koyeb (rotation incomplete) | Verify `printf '%s' "$TOKEN" \| sha256sum` matches the env value |
| `422` on grant | `valid_until_epoch` > `now + 400 days`, NaN/Inf, or non-numeric | Use a sane epoch within 400-day horizon |
| Members "disappear" after restart | Should never happen — events.jsonl replay rehydrates | Check `cat events.jsonl \| grep membership_grant`; file integrity issue if missing |

## References

- ADR-0011 (`docs/adr/0011-gtm-a-membership-primitive-and-paid-feature-positioning.md`) — GTM-A decisions + auth model
- Parked design spec: `.supergoal-v2/parked/membership-primitive-design.md` (28KB, 8 implementation steps, 14 test scenarios)
- Source: `packages/agentdex_arena/src/agentdex_arena/admin_auth.py`, `consent.py` (extensions), `gateway.py` (route + replay)
- Integration tests: `packages/agentdex_arena/tests/test_membership_primitive.py` (10 cases)
- Spaces deploy contract: `~/.claude/projects/-home-admin-gh-agentdex-cli/memory/project_spaces_platform_contract.md`
