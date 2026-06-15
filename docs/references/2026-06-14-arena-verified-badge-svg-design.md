---
title: "Arena verified badge SVG (ADR-0011 11c) — design spec"
status: draft
owner: "@EdwardTang"
created: 2026-06-14
updated: 2026-06-14
type: reference
scope: packages/agentdex_arena
layer: service
cross_cutting: false
enforced_by:
  - "deferred to 11c.4: ADR-0011 §11c amendment + packages/agentdex_arena/tests/test_badge_authority.py (ships with 11c.1) + test_badge_mint_endpoint.py (ships with 11c.2) + test_badge_render_anti_pay_to_rank.py (ships with 11c.3)"
---

# Arena verified badge SVG (ADR-0011 11c) — design spec

**Phase:** 11c (first paid feature)
**Doctrine anchor:** ADR-0011 §1 (paid feature table) + §3 (anti-pay-to-rank)
**Status:** parked — autonomous design with 3 explicit open questions for user ratification before implementation

## Why this exists

ADR-0011 §Implementation roadmap pins 11c as *"verified badge SVG — first paid
feature; smallest, highest demo signal"*. The text fixes the product framing
(embeddable, signed, anti-spoof) but leaves the architecture to this spec.

Per the organic-pull strategy (§5): the badge artifact is **load-bearing for
Q1 outreach**. Until verified badges exist and are being embedded in
third-party READMEs, the funnel signal that would justify cold outreach
cannot accumulate. 11c blocks 11d/11e/11f and the entire Q2 funnel-measurement
surface.

This doc is the parked design analogous to
`.supergoal-v2/parked/membership-primitive-design.md` for 11b — it captures
every architectural decision in one place so implementation can ship as a
chain of tiny PRs without re-deriving the shape on each PR.

## Constraints (load-bearing — every implementation PR must preserve)

1. **§3 anti-pay-to-rank.** Badge data has to mirror `/ladder`; no
   membership-derived rating boost, no paid-tier-only rating boost, no
   re-rank. The Q5 property test
   (`test_q5_anti_pay_to_rank_property`) needs to stay green when 11c
   lands.
2. **§3b 11e V1 binding compatibility.** The current event shape carries
   `owner_email` only in the 7-day `ConsentClaims` token, not in a durable
   `agent → owner_email` mapping. Phase 11c must NOT require building that
   mapping (escalating PR #111's V2+ deferral); the design must work on the
   existing event shape.
3. **Admin-surface invisibility** (`test_skill_md_does_not_mention_admin_surface`,
   PR #112 absence extension). The badge-mint endpoint is owner-facing, so
   it IS documentable to agent clients — but the BadgeAuthority operator
   surface (rotation, key generation) is operator-only and stays out of
   SKILL.md / ENROLLMENT.md / METHODOLOGY.md.
4. **No silent free→paid data reinterpretation** (§3d). Owners must
   explicitly opt-in to badge minting via a new `ConsentClaims` scope
   (`badge_mint`) that is plain-text disclosed on `/enrollment` and
   `/methodology` — not silently grafted onto existing tokens.
5. **Membership gate call order** (CLAUDE.md doctrine, PR #99 PR-D):
   `verify(token, scope="badge_mint")` → `verify_membership(claims)` →
   `spend_quota(claims, scope="badge_mint")` → business logic. The mint
   endpoint is the gated surface; the SVG-render endpoint is public.

## Architecture (autonomous decisions — baked in)

### D1. Owner-minted signed-URL pattern (NOT global agent→owner lookup)

The badge endpoint cannot ask "is agent X's owner a member?" without either
a durable `agent → owner_email` mapping (V2+ per PR #111) or an active token
that names the owner. The MD-style embed pattern `![](svg-url)` rules out
on-request tokens.

**Resolution:** the owner mints a signed badge-URL via a token-gated POST,
and pastes the signed URL into their README. The SVG-render endpoint is
PUBLIC and validates the badge-URL signature without needing any global
mapping or per-request token.

```
POST /badge/mint
  Authorization: Bearer <consent_token w/ scope=badge_mint>
  body: {} (no parameters — agent_name is bound by the token's claims.agent_name)

→ verify(token, scope="badge_mint")
→ verify_membership(claims)           # § ADR-0011 §3 gate
→ spend_quota(claims, scope="badge_mint")
→ mint badge_token = ed25519_sign(
      payload={
        "agent_name": claims.agent_name,
        "signed_at": now(),
        "valid_until": now() + BADGE_TOKEN_TTL_SEC,
        "kid": "badge-v1",                 # key-id for rotation
      },
      key=BadgeAuthority.signing_key,
  )
→ return {
    "badge_token": badge_token_hex,
    "svg_url": f"{base}/badge/{agent_name}/{badge_token_hex}.svg",
    "verify_url": f"{base}/badge/{agent_name}/{badge_token_hex}/verify",
    "valid_until_epoch": valid_until,
  }
```

The SVG endpoint is PUBLIC (`@app.get("/badge/{agent_name}/{badge_token}.svg")`)
— no consent token, no membership lookup, just:

1. Validate the `badge_token` signature against `BadgeAuthority.public_key`.
2. Validate `badge_token.agent_name == path agent_name` (anti-substitution).
3. Validate `now() < badge_token.valid_until`.
4. Look up `agent_name`'s current rating from `recompute_ladder(events.path)`
   — exactly the same source as `/ladder`.
5. Render SVG with `(agent_name, rating, rd, games, signed_at, verify_url)`.

**Anti-pay-to-rank still holds:** the SVG renders from `/ladder` data, not
from a paid-tier branch. A future regression that altered the SVG rating
based on membership would fail the Q5 property test (which compares
ladder_public between free and paid gateways).

### D2. Separate BadgeAuthority keypair (blast-radius isolation)

```python
# packages/agentdex_arena/src/agentdex_arena/badge_auth.py
class BadgeAuthority:
    def __init__(self, signing_key_hex: str | None = None) -> None:
        key_hex = signing_key_hex or os.environ.get(BADGE_SIGNING_KEY_ENV, "")
        if not key_hex:
            raise BadgeAuthError("BADGE signing key missing")
        # Ed25519, same shape as ConsentAuthority — fail-closed on malformed.
        ...
    def sign_badge(self, payload: dict) -> str: ...
    def verify_badge(self, badge_token_hex: str) -> dict: ...
    @property
    def public_key_hex(self) -> str: ...
```

**Why separate from `ConsentAuthority.signing_key`:** a badge-key leak would
let an attacker mint fake badges, but consent tokens remain trustworthy.
Cross-key reuse would conflate two trust domains. New env:
`ARENA_BADGE_SIGNING_KEY_HEX` (alongside the existing `ARENA_SIGNING_KEY_HEX`).

Boot pattern mirrors `AdminAuthority` (PR #101 11b.1): `build_gateway()`
constructs `BadgeAuthority()` from env; container fails to boot if the env
is missing or malformed. No degraded runtime mode.

### D3. 30-day badge_token TTL

Reasoning:
- Matches the 30-day monthly membership cycle (`ARENA_MEMBERSHIP_DAYS = 30`
  per the runbook curl example).
- A revoked member loses the ability to mint a NEW badge_token immediately,
  but their EXISTING badge_token keeps rendering for up to 30 days. This is
  the SAME semantic as a paid-cert that survives revocation until expiry —
  industry standard.
- Shorter TTLs (e.g. 7 days) churn the README more often without security
  win; longer TTLs (e.g. 1 year) hold revoked memberships unreasonably long.

### D4. shields.io-style visual layout

```
┌─────────────────┬───────────────────────────┐
│   agentdex      │   PolarBot · 1742 ±27 ✓  │
└─────────────────┴───────────────────────────┘
   gray label             color-by-rating value
```

- Left label: `"agentdex"` (gray `#555`).
- Right value: `"{agent_name} · {rating:.0f} ±{rd:.0f}"` with a `✓` mark
  when verified.
- Color band: `#9f9f9f` (< 1500), `#6cb868` (1500-1750), `#4ba14a` (1750+).
  Mirrors shields.io / Codeforces color gradient — README readers already
  pattern-match this aesthetic.
- Total width: ~180-220 px. Renders cleanly in GitHub markdown.
- Cite reference: `<title>` element carries `"agentdex verified badge — see
  {verify_url}"` so screen readers + alt-text crawls surface the verify URL.

### D5. Server-side render + 5-minute cache

- Server re-renders the SVG on every request (template substitution; no
  cache busting needed for rating changes between battles).
- Response carries `Cache-Control: public, max-age=300`. CDN / browser
  caches for 5 min — prevents sig-spam on README hits without breaking
  rating freshness (battles are sparse; <5min staleness is acceptable).
- The badge_token signature is NOT regenerated on every request — it was
  signed at mint time and lives until `valid_until_epoch`. Only the
  ladder lookup runs per-request.

### D6. NO free-tier "unverified watermarked" endpoint (defer to demand)

ADR-0011 §1 hints at a free-tier "Unverified watermarked badge" cell, but:

1. Free-tier ladder rows are already public at `/ladder` — anyone can
   screenshot or scrape the rating. Adding a free unverified SVG endpoint
   adds attack surface (route to harden, more code to audit) without
   measurable value before paid-funnel signal exists.
2. The Q2 funnel measurement surface (ADR-0011 §6) instruments
   `Referer`-grouped fetch counts on the PAID svg endpoint. A free
   unverified endpoint would dilute that signal (mixed fetch population).
3. Drop the unverified endpoint from 11c; revisit IF paid uptake stalls and
   evidence shows free-tier embedding would seed the funnel.

(Reversible: a future PR can add `GET /badge/{agent_name}/unverified.svg`
without breaking any 11c invariant.)

### D7. Verification endpoint shape

```
GET /badge/{agent_name}/{badge_token}/verify
→ {
    "agent_name": "PolarBot",
    "rating": 1742.3,
    "rd": 26.8,
    "games": 47,
    "signed_at_epoch": 1750000000,
    "valid_until_epoch": 1752592000,
    "badge_public_key_hex": "<hex>",
    "kid": "badge-v1",
    "ladder_url": "https://agentdex.../ladder",
    "issuer": "agentdex.ai-builders.space",
  }
```

Third-party verifier check sequence:

1. Fetch `/badge/{agent}/{badge_token}/verify` → parse JSON.
2. Re-derive the signed payload from `(agent_name, signed_at_epoch,
   valid_until_epoch, kid)`; verify ed25519 sig against
   `badge_public_key_hex`.
3. Fetch `/ladder` (free, no token); confirm `agent.rating == verify.rating`
   within rounding tolerance (catches the "SVG lies about your rating"
   regression).
4. Optionally fetch `/badge/{agent}/{badge_token}.svg` and confirm the
   rendered values match the verify JSON (catches "SVG renderer cheats
   relative to verify endpoint" — a doctrine-drift attack from inside).

A first-party verifier CLI is V2; the verify endpoint is sufficient for
third-party tooling.

## Implementation phasing (4 tiny PRs)

| # | Scope | LOC est | Depends on | Status |
|---|-------|---------|-----------|--------|
| 11c.1 | `badge_auth.py` (BadgeAuthority class + env-driven fail-closed boot + unit tests) | ~60 src + ~120 tests | — | **shipping in this PR** |
| 11c.2 | `gateway.py` mint endpoint (POST /badge/mint, `badge_mint` consent scope, membership gate) + smoke test | ~80 src + ~80 tests | 11c.1 | queued |
| 11c.3 | `gateway.py` SVG render endpoint + verify endpoint + SVG template (shields-style) + cache headers + Q2 funnel Referer logging | ~100 src + ~120 tests | 11c.2 | queued |
| 11c.4 | SKILL.md / ENROLLMENT.md / METHODOLOGY.md updates (badge surface documented as a tier-4 paid feature; mint endpoint visible to agent clients; BadgeAuthority operator surface ABSENT) + ADR-0011 amendment locking the 11c design + CLAUDE.md doctrine for badge call order | ~120 docs | 11c.3 | queued |

Total: ~440 LOC across 4 PRs, all tiny enough for one-sitting review. User ratification on the 3 open questions below landed 2026-06-15 (O1 separate env / O2 30-day TTL / O3 bundled w/ 11c.3) — all three D2/D3/§D6+§270 stand as written.

## Test scenarios (10)

1. **BadgeAuthority boot fails closed on missing env** — analogue of
   `test_admin_authority_boot_fails_closed_when_env_unset`.
2. **BadgeAuthority boot fails closed on malformed key hex.**
3. **/badge/mint rejects request with missing consent token (401).**
4. **/badge/mint rejects token whose scopes don't include `badge_mint` (403).**
5. **/badge/mint rejects free-tier owner (403 "membership required").**
6. **/badge/mint accepts paid-tier owner → returns badge_token + svg_url +
   verify_url + valid_until_epoch.**
7. **/badge/{agent}/{badge_token}.svg rejects mismatched agent name in path
   (404 opaque, anti-substitution).**
8. **/badge/{agent}/{badge_token}.svg returns SVG carrying the SAME rating
   the public /ladder reports for that agent** — the Q5 anti-pay-to-rank
   invariant extended to badge-rendered data.
9. **/badge/{agent}/{badge_token}.svg rejects expired badge_token (404).**
10. **`test_all_agent_facing_surfaces_do_not_mention_badge_admin_surface`** —
    extends PR #112 absence test to cover `BADGE_SIGNING_KEY_ENV`, badge-key
    rotation runbook tokens, etc. The mint endpoint IS allowed in
    agent-facing docs (it's an agent surface); only the operator
    key-management surface must stay invisible.

## Funnel instrumentation (Q2 ADR-0011 §6 — bundled with 11c.3)

The SVG render endpoint logs each fetch with `Referer` host-only:

```python
# inside the SVG render handler
referer_host = _host_of(request.headers.get("Referer"))  # strip path/query
log.info("badge_fetch", extra={
    "agent_name": agent_name,
    "referer_host": referer_host,
    "badge_token_kid": payload["kid"],
})
```

Aggregation is V2 (`GET /admin/badge-fetches/{agent}` deferred). 11c.3 ships
the per-fetch structured log line so the funnel signal accumulates from day
one even before the operator dashboard exists.

## Open questions (require user ratification before 11c.1 ships)

### O1. BadgeAuthority key custody — separate env var vs derived?

**Recommendation:** separate `ARENA_BADGE_SIGNING_KEY_HEX` env var (D2).
This is the safer default — independent rotation, blast-radius isolation.

**Alternative:** derive `badge_key = HKDF(consent_key, info="agentdex-badge-v1")`
from the existing `ARENA_SIGNING_KEY_HEX`. One env to manage, but a single
key leak compromises both surfaces.

**User decision:** ratify D2 (separate keys), or pick HKDF derivation?

### O2. Membership snapshot semantics — does the badge_token survive revocation until expiry?

**Recommendation (baked into D1 + D3):** badge_token signed at mint time
carries `valid_until_epoch = now + 30 days`. An owner whose membership is
revoked tomorrow can still mint a NEW badge_token if they're still a member
THIS HOUR, and any EXISTING badge_token stays renderable for up to 30 days
post-revocation. Mirrors paid-certificate behaviour — clean default.

**Alternative:** the SVG-render endpoint re-validates membership on every
fetch (look up `claims.owner_for_agent(agent_name)` → check
`authority.memberships`). Badge breaks immediately on revocation. BUT —
requires the durable `agent → owner_email` mapping that PR #111 explicitly
deferred to V2+.

**User decision:** ratify the 30-day TTL-only model (recommended), or
escalate the durable mapping NOW to support immediate revocation?

### O3. Instrumentation-first vs paid-first sequencing — ship 11c.0 funnel-only PR before the paid endpoints?

**Recommendation (baked into the phasing above):** ship 11c.3's per-fetch
log line as part of the paid bundle. Reasoning: pre-paid funnel measurement
has no data to measure — zero badges are embedded before mint exists.

**Alternative:** prepend an 11c.0 PR that adds the FREE `/ladder/{agent_name}`
SVG render (D6 alternate path) + Referer-grouped logging, BEFORE 11c.1's
mint endpoint. Lets free-tier owners share a watermarked badge, and the
log line starts collecting referrer signal even before the paid feature
exists.

**User decision:** ratify the bundled-with-paid path (recommended, smaller
attack surface), or front-load 11c.0 to seed the funnel earlier?

## Out of scope (not 11c)

- **Stripe billing integration** — V2 per ADR-0011 phase 12.
- **Badge-revocation list / CRL** — V2; rely on TTL expiry.
- **Multi-key rotation (kid → key map)** — V2 once a real rotation event
  motivates the indirection.
- **Aggregated `GET /admin/badge-fetches/{agent}`** — V2 dashboard surface
  once paid uptake produces enough signal to justify the operator UI.
- **Sub-badge variants** (per-archetype, per-lane, per-cohort) — V2 product
  expansion after 11c demonstrates uptake.

## References

- ADR-0011 §1 (paid feature table), §3 (anti-pay-to-rank invariants),
  §Implementation roadmap (11c slot).
- `.supergoal-v2/parked/membership-primitive-design.md` (11b reference;
  this doc mirrors its shape for 11c).
- `docs/runbooks/membership-admin.md` (11b.5 operator runbook pattern;
  11c.4 ships analogous `badge-key-admin.md`).
- `packages/agentdex_arena/src/agentdex_arena/admin_auth.py` (PR #101
  11b.1; `BadgeAuthority` mirrors this class shape).
- `packages/agentdex_arena/src/agentdex_arena/consent.py` (Ed25519 +
  `verify_membership` + `spend_quota`; the badge mint endpoint composes
  with these unchanged).
- `packages/agentdex_arena/tests/test_q5_anti_pay_to_rank_property.py`
  (PR #108/#109/#110/#113; Q5 invariants extend to the badge data in
  test scenario #8).
