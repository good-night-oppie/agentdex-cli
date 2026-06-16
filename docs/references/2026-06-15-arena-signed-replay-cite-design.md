---
title: "Arena signed replay + cite_as receipt (ADR-0011 11d) — design spec"
status: validated
owner: "@EdwardTang"
created: 2026-06-15
updated: 2026-06-16
type: reference
scope: packages/agentdex_arena
layer: service
cross_cutting: false
enforced_by:
  - "deferred to 11d.4: ADR-0011 §11d amendment + packages/agentdex_arena/tests/test_receipt_auth.py (ships 11d.1) + test_cite_mint_endpoint.py (ships 11d.2) + test_receipt_render_endpoint.py (ships 11d.3) + extension of test_skill_md_does_not_mention_admin_surface (ships 11d.4)"
---

# Arena signed replay + cite_as receipt (ADR-0011 11d) — design spec

**Phase:** 11d (second paid feature, after 11c verified-badge SVG)
**Doctrine anchor:** ADR-0011 §1 (paid-feature table) + §3 (anti-pay-to-rank) + §3b §5e (scope-conditional spend_quota) + §8 O1 (separate-key blast-radius isolation precedent)
**Status:** RATIFIED 2026-06-16 (session adx-cli-8) — all 3 open questions resolved (see Ratification log). O2 revised against adversarial workflow `wf_873c1d08-480`. 11d.1 unblocked.
**Workflow provenance:** `wf_a0a5743a-8f3` (13 agents, 879k tokens, 9.8 min). 4 lens proposals (Minimalist / Full-cite / Hybrid / Receipts-as-Service) × adversarial scoring → Receipts-as-Service wins 26/30 on minimalism + invariant safety + product fit; runner-up Full-cite (24/30) lost on minimalism (separate cite_as endpoint + scope dimension). Bene-7 cross-team input (2026-06-15 04:32Z): adx-cli self-implements against bene's stable replay-manifest substrate; suggested BadgeAuthority key reuse was adversarially refuted in favor of separate ReceiptAuthority per §8 O1.

## Why this exists

ADR-0011 §Implementation roadmap pins 11d as *"signed replay + cite_as — second paid feature; closes the outsider-verifiable receipt loop"*. The product promise: an owner who wants to **cite** an agentdex battle (in a paper, blog post, README) gets a **signed, long-lived receipt URL** + a **paste-ready BibTeX block** — anyone in the world can verify the receipt cryptographically and cross-check the rating against the public `/ladder` without trusting agentdex.

11c (verified badge SVG) closed the *display* side of the receipt loop — *"this agent has rating X"*. 11d closes the *citation* side — *"in battle B on date D, this agent won, here is the signed proof and the input log digest you can re-derive."*

This doc is the (now RATIFIED) design analogous to
`docs/references/2026-06-14-arena-verified-badge-svg-design.md` for 11c — autonomous decisions baked in, 3 open questions ratified 2026-06-16 (see Ratification log), 4-PR implementation chain analogous to 11c.1–11c.4.

## Constraints (load-bearing — every implementation PR must preserve)

1. **§3a anti-pay-to-rank.** `GET /replay/{battle_id}` stays free + zero `@require_membership` decorators. The new cite endpoints are an ADDITIVE paid surface; the free baseline cannot be regressed. The Q5 property test (`test_q5_anti_pay_to_rank_property`) MUST stay green when 11d lands — extended to assert cite_mint introduces zero rating-bending paths (test scenario 9).
2. **§3b V1 binding compatibility.** The existing event shape carries `tenant_id` only in `battle_end` payloads (gateway.py:888-898) and no durable `agent → owner_email` mapping. Phase 11d MUST NOT require building that mapping (escalating PR #111's V2+ deferral); cite mint gates on `caller.agent_name == participant` (similar to 11e bulk export's V1 narrowing) and works on the existing event shape.
3. **§3b §5e scope-conditional spend_quota.** The new `cite` scope is NON-battle, so it keys on `claims.agent_name` (NOT on `claims.token_id`, NOT on owner). Survives `/enroll/reissue` (same agent_name, fresh token_id), unique per agent (no cross-agent pooling). Matches PR #130 11c.2 binding.
4. **§3c property-test extension.** `test_q5_anti_pay_to_rank_property` extended to assert rating-ceiling equality between a free owner and a paid owner who minted cite_tokens — the cite mint endpoint contributes zero rating-bending paths.
5. **§3d no silent free→paid data reinterpretation.** New `ConsentClaims` scope (`cite`) plaintext-disclosed on `/enrollment` and `/methodology` BEFORE 11d.2 mint endpoint ships. Pre-existing tokens MUST `/enroll/reissue` to acquire the scope — `verify(scope="cite")` raises `ConsentError` on legacy tokens (the §3d-disciplined no-silent-widening behavior).
6. **Admin-surface invisibility, split (CLAUDE.md doctrine + PR #112).** The owner-facing mint endpoint `POST /replay/{battle_id}/cite` IS published on `SKILL.md` as a paid feature (matches `POST /badge/mint` from PR #133). The operator-only `cite-admin.md` runbook + `ARENA_RECEIPT_SIGNING_KEY_HEX` env + `/admin/*` routes stay invisible from agent docs — enforced by extending `test_skill_md_does_not_mention_admin_surface`.
7. **Membership gate call order (CLAUDE.md doctrine).** `verify(token, scope="cite")` → `verify_membership(claims)` → `spend_quota(claims, scope="cite")` → `sign_receipt(...)`. Additive — mirrors `gateway.py:1503-1521` (badge_mint) exactly.
8. **Server-only fork-fuel discipline.** `tenant_id`, `seed`, `teams`, `visitor_choices` MUST stay out of any public cite response — the `gateway.py:910-925` `/replay` public-view filter boundary is preserved verbatim.
9. **Opaque-404 anti-enumeration (D7-style).** Every bad-path on the cite endpoints collapses to opaque 404 — bad signature, expired payload, unknown `battle_id`, `kid` mismatch, `agent_name` mismatch on mint. 503 only on receipt-signing-key-not-configured (degraded boot mode). Quarantine is the deliberate exception — see D3.

## Architecture (autonomous decisions — baked in)

### D1. Single membership-gated mint endpoint; public receipt page is "the auth is the signature"

```
POST /replay/{battle_id}/cite
  Authorization: Bearer <consent_token w/ scope=cite>
  body: {} (no parameters — agent_name is bound by claims, battle_id by path)

→ verify(token, scope="cite")
→ verify_membership(claims)                    # § ADR-0011 §3 paid-feature gate
→ spend_quota(claims, scope="cite")            # 5/day per agent_name (§5e)
→ assert claims.agent_name in {p1, p2} else 404 opaque (V1 binding, D6)
→ assert battle_id NOT in quarantined set else 404 opaque (D6 anti-laundering)
→ payload = {
    "agent_name": claims.agent_name,
    "battle_id": battle_id,
    "lane": "rated" | "sandbox",
    "winner": "<name>" | "",          # "" = tie
    "input_log_blake2b16": "<16B hex>", # determinism anchor
    "signed_at_epoch": now,
    "valid_until_epoch": now + 365 * 86_400,
    "kid": "cite-v1",
    "issuer": ARENA_ISSUER,            # "agentdex.ai-builders.space"
  }
→ cite_token = ed25519_sign(canonical_json(payload), key=ReceiptAuthority.signing_key)
→ events.append("cite_mint", {                  # audit trail; NO rating fields, NO token material
    "tenant_id": claims.token_id,
    "agent_name": claims.agent_name,
    "battle_id": battle_id,
    "valid_until_epoch": valid_until,
    "kid": "cite-v1",
  })
→ return {
    "receipt_url": f"{base}/receipt/{battle_id}/{cite_token}",
    "cite_token": cite_token,
    "valid_until_epoch": valid_until,
    "bibtex_preview": "<rendered @misc block>",  # convenience; canonical render lives at /receipt
  }
```

The receipt endpoint is PUBLIC (`@app.get("/receipt/{battle_id}/{cite_token}")`) — no consent token, no membership lookup, the cite_token signature IS the auth. Mirrors `POST /badge/mint` ↔ `GET /badge/{agent}/{token}.svg` from 11c. Anti-pay-to-rank holds end-to-end: cite content is a pure projection of free `/ladder` + `/replay` surfaces.

### D2. Separate `ReceiptAuthority` keypair + shared `ARENA_ISSUER` constant

```python
# packages/agentdex_arena/src/agentdex_arena/_issuer.py  (NEW)
ARENA_ISSUER = "agentdex.ai-builders.space"

# packages/agentdex_arena/src/agentdex_arena/receipt_auth.py  (NEW)
RECEIPT_SIGNING_KEY_ENV = "ARENA_RECEIPT_SIGNING_KEY_HEX"
RECEIPT_KID_V1 = "cite-v1"

class ReceiptAuthority:
    def __init__(self, signing_key_hex: str | None = None) -> None: ...
    def sign_receipt(self, payload: dict) -> str: ...
    def verify_receipt(self, cite_token_hex: str) -> dict: ...
    @property
    def public_key_hex(self) -> str: ...
```

**Why separate from `BadgeAuthority` and `ConsentAuthority`** (the workflow's Receipts-as-Service lens scored highest on this — 26/30 — and the adversarial pass explicitly refuted the cross-team suggestion to reuse BadgeAuthority's key):

- Receipts live in the wild for 365 days inside academic papers; a badge-key compromise must not silently re-sign citations and vice versa.
- §8 O1 already paid the operational cost of an extra env var; replicating that posture preserves audit consistency and the kid-rotation story symmetry.
- Bene-7 cross-team input (2026-06-15 04:32Z) suggested BadgeAuthority key reuse for the signing layer; the adversarial pass weighed the operator simplicity against the trust-domain-isolation cost and chose isolation.

`_issuer.py` is a small refactor that codifies the shared-operator-surface constant (`ARENA_ISSUER`) without sharing key material. `BadgeAuthority` (PR #129) is amended in 11d.1 to import from `_issuer.py` instead of holding a private `BADGE_ISSUER` constant — converges the issuer string across both paid features.

Boot pattern mirrors `BadgeAuthority` (PR #129): `build_gateway()` constructs `ReceiptAuthority()` from env; container fails to boot if the env is missing or malformed. No degraded runtime mode.

### D3. Single public receipt URL with dual format (HTML + JSON-LD) + quarantine-200-with-banner

```
GET /receipt/{battle_id}/{cite_token}
Accept: text/html  (default)                 → HTML response
Accept: application/ld+json | ?format=json   → JSON-LD response
```

**HTML response** (200, `Cache-Control: public, max-age=300`):

- Human-readable summary block: agent_name, lane, winner, rating + RD as of signed_at, link to `/replay/{battle_id}`.
- `<meta property="og:*">` tags: `og:title`, `og:description` (carrying the lane string — `"rated lane"` / `"sandbox lane"` per adversarial A4 amendment), `og:image`. **Per O3 ratification (2026-06-16): `og:image` is a PER-RECEIPT dynamically-rendered PNG** — carries `agent_name` + `winner` + `lane`, NOT a static agentdex logo (a static placeholder would make every social-unfurl card visually identical and bury the battle facts in the og:description text). Rendered on-demand at first fetch + cached on the same `max-age=300` policy as the page. Reuse the 11c badge render pipeline (SVG template → raster) for the card. The README-embeddable `.svg` share-card is O3-deferred to 11d.5.
- Inline `<script type="application/ld+json">` carrying the FULL JSON-LD claim (**Google Dataset Search + generic rich-results + AI agents harvest this — NOT Google Scholar / Semantic Scholar; see §O2 ratification for the corrected discovery model**).
- Highwire `citation_*` `<meta>` tags (per O2 ratification 2a) — `citation_title`, `citation_author`, `citation_publication_date`, `citation_public_url`. **These are the tags Google Scholar actually reads** (JSON-LD is invisible to Scholar). Mirrors the arXiv / Nature ingestion path. See §O2.
- Copy-paste BibTeX `<pre>` block (D5).

**JSON-LD response** (200, `Content-Type: application/ld+json`) — **revised per O2 ratification (2026-06-16)**:

```json
{
  "@context": [
    "https://schema.org",
    {"adx": "https://agentdex.ai-builders.space/schema/v1#"}
  ],
  "@type": "Dataset",
  "additionalType": "adx:SignedReplayCite",
  "name": "agentdex battle {battle_id} ({lane}) — {agent_name}",
  "description": "Signed cite_as receipt for agentdex battle {battle_id} on the {lane} lane. Participant {agent_name}; winner {winner}; input-log digest {input_log_blake2b16}. Re-derive from GET /replay/{battle_id}.",
  "creator": "<agent_name>",
  "identifier": "<input_log_blake2b16>",
  "dateCreated": "<ISO date of signed_at>",
  "distribution": {"contentUrl": "/replay/{battle_id}"},
  "publisher": "agentdex.ai-builders.space",
  "license": "https://agentdex.ai-builders.space/methodology",
  "creativeWorkStatus": "active" | "disputed"   // 'disputed' if quarantined
}
```

**Why this shape** (was `@type: ['Dataset','CreativeWork']` in the parked draft — REVISED):

- **Single `@type: 'Dataset'`, not the `['Dataset','CreativeWork']` hybrid.** `Dataset` is already a direct subclass of `CreativeWork` in schema.org's hierarchy (`Thing > CreativeWork > Dataset`), so stacking both is the canonical redundant-MTE anti-pattern the schema.org Multi-Typed-Entity wiki explicitly warns against ("avoid spamming MTEs… consumers typically consider your data as lower quality"). Single `Dataset` is also the only form documented as Google Dataset Search rich-result eligible; the array gives up that eligibility for zero upside.
- **`@context` array + inline `adx:` namespace** carries the agentdex-native precision via `additionalType: "adx:SignedReplayCite"` without breaking the canonical single-Dataset shape. This is the live MLCommons Croissant pattern (Hugging Face leaderboard results), the Google Dataset Search docs' own `csvw` pattern, and the Bioschemas / RO-Crate production pattern. The parked draft's "custom @context is silently dropped by crawlers" rejection was **empirically false**: defined terms in a hybrid context expand to absolute IRIs and are preserved per the JSON-LD 1.1 normative algorithm; consumers that only load the first context entry still resolve every schema.org term cleanly (graceful degradation).
- **`name` + `description` are REQUIRED, not optional** (PR #151 review #3417784949). Google's Dataset structured-data docs gate rich-result eligibility on both properties (`developers.google.com/search/docs/appearance/structured-data/dataset#dataset`). Because O2 makes Google Dataset Search the load-bearing discovery channel, a receipt that omits them ships a non-eligible shape — defeating the entire O2 rationale. Both are rendered DETERMINISTICALLY from the signed payload (`battle_id`, `lane`, `agent_name`, `winner`, `input_log_blake2b16`) so two fetches of the same receipt always produce byte-identical metadata. Test scenario 6 asserts their presence + determinism.
- **`creativeWorkStatus`** (was bare `status`) is the schema.org-canonical property for the active/disputed flag. **This is the SINGLE field name for the disputed flag across the whole spec** — the quarantine section + test scenario 8 below use `creativeWorkStatus`, NOT a bare `status` (PR #151 review #3417784951; the parked draft's `status` is fully retired).

**Quarantine semantic (D3 amendment — closes the /replay-vs-/receipt side-channel):**

If the cited battle becomes quarantined AFTER mint:

- The receipt page returns **200 with a visible "this battle is under dispute as of {date}" banner** (HTML) + `"creativeWorkStatus": "disputed"` (JSON-LD). NOT a 404.
- The signature stays cryptographically valid — the published paper's citation does NOT 404 a year later.
- Anti-laundering preserved: the live banner means a reader sees dispute status truthfully without trusting the citing paper.

Opaque 404 still returned on the enumeration vectors: bad signature, expired payload, unknown `battle_id`, `kid` mismatch. 503 only on receipt-signing-key-not-configured.

### D4. TTL = 365 days, cancellation cliff plaintext-disclosed

```
valid_until_epoch = signed_at_epoch + 365 * 86_400
```

**Reasoning:**

- 30-day TTL (the 11c badge default) is hostile to academic publication — peer review + revisions routinely outlast it. A receipt that expires before the paper is published is worse than no receipt.
- Permanent TTL breaks the kid-rotation revocation story (D10).
- 365 days covers the full academic cycle (submission → revision → publication → indexing) and matches the §1 paid-retention envelope.

**Cancellation cliff (Hybrid adversarial amendment):**

Owners may re-mint freely while membership is active; each re-mint produces a fresh `cite_token`. Old cite_tokens remain valid until their own `valid_until_epoch` — paper-citation safety.

When membership is cancelled:

- Already-minted `cite_tokens` remain valid until their existing `valid_until_epoch` (D10 forbids verify-time membership checks).
- Cancelled owner CANNOT re-mint (membership gate at step 2 of the call order).

This cliff is documented at:

- `/enrollment` (§3d-compliant plaintext disclosure — ships in 11d.4, BEFORE 11d.2 mint endpoint goes live).
- `/methodology` §6 Citations subsection.
- `cite-admin.md` operator runbook (key custody + rotation procedure).

### D5. BibTeX rendered live inside the receipt HTML; `@misc` entry type

Entry type: **`@misc`** (matches arXiv / web-archive convention; vanilla biblatex-parser-compatible).

```
@misc{agentdex_battle_{battle_id},
  author       = {{<agent_name>}},
  title        = {{agentdex battle {battle_id} ({lane})}},
  year         = {{<UTC year of signed_at>}},
  howpublished = {\url{<absolute receipt_url>}},
  urldate      = {<ISO date of signed_at>},
  note         = {{winner: <name>; rating <r> ± <rd> as of signed_at}},
}
```

- **No separate `GET /cite_as.bib` endpoint.** The block is rendered server-side from `gateway.ladder_public()` (live) + the signed payload. Folds the BibTeX into the receipt page — eliminates an endpoint + a scope dimension + a quota counter.
- **`@misc` over `@software` or `@data`.** `@software` conflates the agent-as-software with the battle-as-result; `@data` is biblatex-only. `@misc` survives every BibTeX parser unchanged.
- **Live mirror from `/ladder`.** Quarantined battle's BibTeX reflects current state (D3's 200-with-banner posture) — anti-laundering by construction.

### D6. Cite mint restricted to participants; sandbox + rated both citable; quarantine refused at mint AND render

**Mint-time check (gateway.py path):**

```python
if claims.agent_name not in {replay["p1_name"], replay["p2_name"]}:
    raise _opaque_error(404, "battle not found or not citable")   # NOT 403
if battle_id in gateway._quarantined_set():
    raise _opaque_error(404, "battle not found or not citable")
```

- V1 narrowing mirrors §3b 11e binding (`caller.agent_name == participant`). Durable `owner → agents` mapping (register_v2) stays deferred to 11e — NOT escalated by 11d.
- **404 not 403** — anti-enumeration. A third party probing whether a battle exists or who participated MUST NOT be able to tell mint-side rejection apart from "this battle simply does not exist".
- **Sandbox citable too** — pedagogical value + truth-in-advertising. The BibTeX `lane` field + the og:description disambiguate rhetorical weight.
- **Quarantine refused at mint time AND render time.** Mint refuses (so a known-disputed battle cannot get a fresh receipt minted to launder it); render shows a banner for receipts minted BEFORE quarantine.

### D7. Cite payload binds to `input_log_blake2b16`; `cite_mint` event appended to EventLog (audit only)

**Signed payload binds the public determinism anchor:**

```python
payload = {
    "agent_name": claims.agent_name,
    "battle_id": battle_id,
    "lane": lane,
    "winner": winner,
    "input_log_blake2b16": <16-byte hex>,   # the chain-recorded fingerprint
    "signed_at_epoch": now,
    "valid_until_epoch": now + 365 * 86_400,
    "kid": RECEIPT_KID_V1,
    "issuer": ARENA_ISSUER,
}
```

A skeptical reader can independently prove honesty:

1. Fetch `GET /replay/{battle_id}` (free) → re-derive `blake2b16("\n".join(input_log))`.
2. Fetch `GET /receipt/{battle_id}/{cite_token}/verify`-style JSON-LD → read `identifier` (= `input_log_blake2b16`).
3. Compare; equality = the receipt's signed claim and the publicly-replayable input log agree.

**EventLog `cite_mint` event** — append-only audit trail; NO rating fields, NO token material:

```python
events.append("cite_mint", {
    "tenant_id": claims.token_id,
    "agent_name": claims.agent_name,
    "battle_id": battle_id,
    "valid_until_epoch": valid_until,
    "kid": RECEIPT_KID_V1,
})
```

- `recompute_ladder` explicitly skips `cite_mint` events (preserves the §3c property test — the cite endpoint introduces zero rating-bending paths).
- `cite_token` itself NEVER chained — leaking the bearer credential into the audit log would defeat the entire scheme.

### D8. Add `"cite"` to `Scope` literal + `ConsentAuthority.mint` default quotas BEFORE 11d.2 ships

```python
# consent.py
Scope = Literal["enroll", "battle", "evolve", "badge_mint", "cite"]
# ConsentClaims default_factory quotas adds: "cite": 5
```

- Pre-existing un-reissued tokens (constructed before 11d.1) DO NOT carry the `cite` scope — they fall through `verify()`'s scope-not-in-claims.scopes check and get `ConsentError`. **This IS the §3d-disciplined no-silent-widening behavior**, not a bug.
- `/enrollment` + `/methodology` plaintext disclosure of `cite` MUST land BEFORE the mint endpoint goes live. The 4-PR phasing enforces this: PR 11d.4 (docs sync) must merge BEFORE or co-ship with PR 11d.2 (mint endpoint), not trail it.
- Owners reissue tokens via the existing `/enroll/reissue` path to acquire the new scope. Quota is keyed per §3b §5e else-branch (`agent_name`, not `token_id`) — survives reissue, unique per agent.

### D9. Admin-surface invisibility split: mint route IS published, key custody is NOT

`POST /replay/{battle_id}/cite` is the user-facing paid surface and IS documented in `SKILL.md` as a paid feature (matches `POST /badge/mint` precedent from PR #133).

`docs/runbooks/cite-admin.md` + `ARENA_RECEIPT_SIGNING_KEY_HEX` + key-rotation procedure stay operator-only — absent from `SKILL.md`, `ENROLLMENT.md`, `METHODOLOGY.md`.

The existing `test_all_agent_facing_surfaces_do_not_mention_admin_surface` test (and its badge-flavored sibling from PR #133) is extended with cite-flavored forbidden tokens: `cite-admin`, `cite-admin.md`, `ARENA_RECEIPT_SIGNING_KEY_HEX`, `koyeb secret create arena-receipt`. The PR #112 absence pattern carries through unchanged.

### D10. Cite revocation lives in kid rotation, NEVER in a verify-time membership check

**Explicit ADR-0011 §11d clause locked in 11d.4:**

> Cite tokens are revoked by `kid` rotation (`cite-v1` → `cite-v2`), NOT by a membership-status check at receipt-render time. A future engineer MUST NOT add a verify-time membership lookup on `GET /receipt/{...}` as an optimization — that would smuggle in a §3a violation (rating-derived data going paid-tier-private after the fact, breaking the rating-ceiling-equality property test).

Cancelled-membership owners' already-minted cite_tokens stay valid until their own `valid_until_epoch`. The cancellation cliff (D4) is bounded — published receipts survive to their TTL, never silently re-issued or retroactively invalidated.

A `enforced_by:` claim line is added to ADR-0011 §3 frontmatter referencing the test (`test_cite_revocation_via_kid_rotation_not_membership_check`).

## Implementation phasing (4 tiny PRs)

| # | Scope | LOC est | Status |
|---|-------|---------|--------|
| 11d.1 | `_issuer.py` (shared `ARENA_ISSUER` + BadgeAuthority refactor) + `receipt_auth.py` (ReceiptAuthority + fail-closed boot + unit tests) + `consent.py` `Scope` literal extension + default quota `"cite": 5` + scope/quota unit tests | ~120 src + ~150 tests | queued |
| 11d.2 | `gateway.py` `POST /replay/{battle_id}/cite` (call order verify → verify_membership → spend_quota → sign; participant V1 binding; quarantine refused; `cite_mint` EventLog append) + smoke test | ~140 src + ~120 tests | queued (after 11d.1 + 11d.4 docs land) |
| 11d.3 | `gateway.py` `GET /receipt/{battle_id}/{cite_token}` public dual-format (HTML + JSON-LD via Accept header) + OG meta tags w/ **per-receipt dynamic `og:image` PNG (O3)** + **Highwire `citation_*` meta tags (O2 2a)** + **revised single-`Dataset` JSON-LD w/ hybrid `@context` (O2)** + inline BibTeX `<pre>` + quarantine-200-with-banner + opaque-404 on enumeration vectors + 5-min cache | ~190 src + ~170 tests | queued |
| 11d.4 | ADR-0011 §11d amendment + new `enforced_by` claim lines + `/enrollment` plaintext disclosure of `cite` scope + cancellation cliff disclosure + `/methodology` §6 Citations subsection + `SKILL.md` paid surface entry (matches badge_mint precedent) + new `docs/runbooks/cite-admin.md` operator runbook + extension of `test_skill_md_does_not_mention_admin_surface` to assert `cite-admin` absence | ~120 docs | queued (MUST precede or co-ship with 11d.2) |

Total: ~600 src + ~440 tests across 4 PRs, all tiny enough for one-sitting review. (Bumped from the parked draft's ~570/~420 by the O2/O3 ratification adding Highwire `citation_*` meta tags + dynamic `og:image` render + the revised single-`Dataset`/hybrid-`@context` JSON-LD to 11d.3.)

**Shipping order:** 11d.1 ships first (substrate); 11d.4 ships with or before 11d.2 (§3d compliance: scope plaintext-disclosed before tokens carrying it exist); 11d.2 ships next (mint endpoint behind the disclosed scope); 11d.3 ships last (public render surface).

## Test scenarios (16)

1. **`test_receipt_authority_separate_key_isolation`** — ReceiptAuthority loads from `ARENA_RECEIPT_SIGNING_KEY_HEX`; distinct from `ARENA_BADGE_SIGNING_KEY_HEX` and `ARENA_SIGNING_KEY_HEX`; `receipt_public_key_hex` differs from `badge_public_key_hex`; `kid='cite-v1'`; missing env → 503 fail-closed (mirrors PR #129 badge boot posture). **[11d.1]**
2. **`test_cite_scope_added_to_defaults_no_silent_widening`** — Newly-minted ConsentClaims via `ConsentAuthority.mint` carry `cite` in scopes + `quotas['cite']=5`; PRE-EXISTING tokens (constructed with `['enroll','battle','evolve','badge_mint']` only) raise `ConsentError` on `verify(scope='cite')`. `/enrollment` plaintext response lists `cite` BEFORE this PR merges. **[11d.1 + 11d.4]**
3. **`test_cite_mint_free_tier_rejected`** — `POST /replay/{battle_id}/cite` by free-tier owner returns 403 "membership required" (verify_membership step 2 of call order). **[11d.2]**
4. **`test_cite_mint_non_participant_opaque_404`** — `POST /replay/{battle_id}/cite` by paid owner whose `agent_name not in {p1, p2}` returns 404-opaque, NOT 403 (D6 V1 binding + anti-enumeration). **[11d.2]**
5. **`test_cite_mint_quarantined_battle_opaque_404`** — `POST /replay/{battle_id}/cite` on quarantined `battle_id` returns 404-opaque even for eligible participant with valid paid token (D6 anti-laundering closure parallel to gateway.py:1385 sandbox-fork ban). **[11d.2]**
6. **`test_receipt_dual_format_html_and_json_ld`** — `GET /receipt/{battle_id}/{cite_token}` with valid token returns 200 HTML containing agent_name + battle_id + inline `<pre>` BibTeX + `<script type="application/ld+json">` with **single `@type="Dataset"` + `@context` array carrying the `adx:` namespace + `additionalType="adx:SignedReplayCite"` + non-empty `name` AND `description` (Google Dataset rich-result eligibility — PR #151 review #3417784949) rendered deterministically from the signed payload so two fetches yield byte-identical metadata (O2 ratification)** + `og:description` carrying lane string; same path with `Accept: application/ld+json` returns JSON-LD body directly with `Content-Type: application/ld+json` (no HTML chrome). **[11d.3]**
7. **`test_receipt_opaque_404_on_enumeration_vectors`** — `GET /receipt/{...}` returns opaque 404 on: tampered signature, expired payload (signed_at + 365d < now), unknown battle_id, kid mismatch. All return identical body (no leak of which check failed). 503 only on receipt-signing-key-not-configured. **[11d.3]**
8. **`test_receipt_quarantine_renders_200_with_banner`** — Battle quarantined AFTER mint: `GET /receipt/{battle_id}/{cite_token}` returns 200 with visible "this battle is under dispute" banner in HTML; JSON-LD response carries `"creativeWorkStatus": "disputed"`; signature still cryptographically valid (NOT 404). Closes the /replay-vs-/receipt side-channel. **[11d.3]**
9. **`test_q5_anti_pay_to_rank_property_extension`** — For any (free-owner-A, paid-owner-B) pair with identical (skill, opponent sequence, N battles), `recompute_ladder` rating ceiling is equal. Asserts cite_mint endpoint introduces ZERO rating-bending paths: `cite_mint` EventLog entry carries no rating fields, `recompute_ladder` explicitly skips `type=='cite_mint'`, `/receipt` render reads `gateway.ladder_public()` (live mirror) but never writes. **[11d.2]**
10. **`test_receipt_third_party_verifiability`** — JSON-LD `identifier` field equals `blake2b16("\n".join(GET /replay/{battle_id}.input_log).encode())`; signed payload's `input_log_blake2b16` matches both. Three-way determinism cross-check holds (signed digest == public /replay re-derived digest == EventLog `battle_end` payload digest). **[11d.3]**
11. **`test_cite_quota_agent_name_keyed_survives_rotation`** — Two agents same owner each get independent 5/day cite quota (§3b §5e else-branch); 6th cite mint same agent same day returns 429; re-enrolling agent A (new token_id, same agent_name via `/enroll/reissue`) does NOT reset the counter (key is `agent_name`, not `token_id`). **[11d.1 + 11d.2]**
12. **`test_skill_md_documents_mint_omits_admin`** — `GET /skill.md` response contains `POST /replay/{battle_id}/cite` (paid mint surface, matches badge_mint precedent per D9); response does NOT contain `cite-admin` / `/admin/grant-membership` / `ARENA_RECEIPT_SIGNING_KEY_HEX`. Extends `test_skill_md_does_not_mention_admin_surface` family. **[11d.4]**
13. **`test_admin_grant_does_not_widen_cite_quota`** — `POST /admin/grant-membership` cannot raise `claims.quotas['cite']` above default 5/day (mirrors §3b constraint 3 + 11c PR-M test pattern). **[11d.2]**
14. **`test_cite_revocation_via_kid_rotation_not_membership_check`** — Cancelling membership for a paid owner with already-minted `cite_token` does NOT cause `/receipt` to 404 (token remains valid until its own `valid_until_epoch`); future kid-v2 rotation invalidates all kid-v1 tokens uniformly. Explicit anti-§3a-violation regression lock for D10. **[11d.3]**
15. **`test_receipt_emits_highwire_citation_meta_tags`** — (O2 2a) `GET /receipt/{battle_id}/{cite_token}` HTML response contains `<meta name="citation_title">`, `<meta name="citation_author">` (= agent_name), `<meta name="citation_publication_date">` (= signed_at date), `<meta name="citation_public_url">` (= absolute receipt_url). These are the Google-Scholar-readable tags (JSON-LD is invisible to Scholar); asserts the parked-draft discovery-model correction is actually wired. **[11d.3]**
16. **`test_receipt_og_image_is_per_receipt_dynamic`** — (O3) `GET /receipt/{battle_id}/{cite_token}` HTML `og:image` URL resolves to a render that varies by `agent_name` / `winner` / `lane` (two distinct receipts → two distinct `og:image` byte streams), NOT a single static placeholder. Cache header on the image matches the page `max-age=300`. **[11d.3]**

## Funnel instrumentation (Q2 ADR-0011 §6 — bundled with 11d.3)

The receipt render endpoint logs each fetch with `Referer` host-only:

```python
# inside the receipt render handler
referer_host = _badge_referer_host(request.headers.get("Referer"))  # reuse from 11c.3
log.info(
    "receipt_fetch agent=%s battle_id=%s referer_host=%s kid=%s",
    payload["agent_name"], payload["battle_id"], referer_host, payload["kid"],
)
```

Distinct log key from `badge_fetch` so the operator can disambiguate badge embeds from receipt citations in the aggregation V2 endpoint (`GET /admin/citation-fetches/{agent}` deferred).

## Ratification log (all three resolved 2026-06-16 — 11d.1 unblocked)

> The three open questions below were ratified by the user on 2026-06-16 in
> session `adx-cli-8`. O2 was resolved against adversarial workflow
> `wf_873c1d08-480` (live-fetched real publisher JSON-LD + Scholar/Semantic-
> Scholar inclusion docs) which overturned the parked draft's recommendation
> and three of its four rejection rationales. §D3 (HTML + JSON-LD response)
> has been amended in-place to reflect O2 + O3; this section records the
> decisions + rationale. 11d.1 may now ship.

### O1. Receipt page verification posture — RATIFIED 2026-06-16: static signed payload only

**Decision: Static signed payload only, no embedded re-sim.** Receipt HTML footer documents: *"Independent verifiers can re-derive input_log_blake2b16 from GET /replay/{battle_id} or re-simulate via POST /battle/{battle_id}/dispute."* Mirrors 11c verify's hand-you-the-public-key + ladder_url cross-check posture; keeps the receipt path cheap (no showdown sim on every embed-fetch — `Cache-Control: public, max-age=300` stays viable).

The receipt is a **self-contained signed artifact**: the server signs once at mint time, and the receipt verifies for its full TTL even if the gateway is down. Crucially this keeps the server OUT of the per-fetch verification loop — it never re-issues a "server-verified ✓" judgment, which would hand a future engineer a lever to verify paid receipts differently from free ones (a latent §3a anti-pay-to-rank side-door). DOI/arXiv idiom: hand the reader a stable URL + metadata; verification is the reader's job.

- **Rejected: embed live re-sim on every fetch** — expensive, defeats `Cache-Control`, opens a DoS surface (any anonymous visitor forces a showdown sim) on a public endpoint, and smuggles server-as-verifier back in.
- **Deferred to 11d.5: separate `POST /receipt/{battle_id}/{cite_token}/verify` endpoint** that does server-side re-sim on demand (rate-limited free). This is a strict, fully-reversible EXTENSION of the static posture — addable any time without breaking existing receipts. V1 ships static; real fetch-funnel data (Q2 log) decides whether on-demand verify is worth the second endpoint's scope/quota/rate-limit design surface.

### O2. JSON-LD vocabulary — RATIFIED 2026-06-16: single `Dataset` + hybrid `@context` + Highwire meta tags

The parked draft's recommendation **and three of its four rejection rationales were empirically wrong** — caught by adversarial workflow `wf_873c1d08-480` (7 agents, 425k tokens; fetched live JSON-LD from arXiv / Zenodo / Nature / Hugging Face / lmarena.ai / SWE-bench / MLPerf / Kaggle and cross-checked against Google Scholar + Semantic Scholar inclusion docs). Corrected decision:

**Discovery model correction (load-bearing):** Google Scholar does **NOT** read JSON-LD at all — its documented ingestion surface is Highwire `citation_*`, BE Press, PRISM, Eprints, and Dublin Core `DC.*` `<meta>` tags (`scholar.google.com/intl/en/scholar/inclusion.html`). arXiv — the AI-research preprint substrate — emits ZERO JSON-LD and uses only `citation_*` meta tags. Semantic Scholar does NOT harvest arbitrary HTML pages at all (it ingests 50+ registered partners + a PDF-only crawler; `arXiv:2301.10140`). **JSON-LD routes to Google Dataset Search + generic rich-results + AI agents, not to Scholar / Semantic Scholar.** The parked draft's entire "give Google Scholar a familiar entry shape" premise was misdirected.

**Decision (replaces the §D3 JSON-LD block):**

1. **JSON-LD = single `@type: "Dataset"`** (NOT `['Dataset','CreativeWork']`). `Dataset ⊂ CreativeWork` already, so the hybrid is the schema.org MTE-wiki's canonical redundant-stacking anti-pattern and forfeits Google Dataset Search rich-result eligibility (documented for single `Dataset` only).
2. **`@context` array + inline `adx:` namespace + `additionalType: "adx:SignedReplayCite"`** for agentdex-native precision. This is the live MLCommons Croissant pattern (Hugging Face), the Google Dataset Search `csvw` pattern, and Bioschemas / RO-Crate production usage. The "custom @context silently dropped" rejection was false — defined terms expand to IRIs and are preserved per JSON-LD 1.1.
3. **Pair the JSON-LD with Highwire `citation_*` `<meta>` tags (2a)** — `citation_title`, `citation_author`, `citation_publication_date`, `citation_public_url`. THIS is the channel Google Scholar actually reads. Mirrors arXiv / Nature.
4. **DOI minting (DataCite/Crossref) DEFERRED** to 11d.5 / 11e — the only real self-serve channel into Semantic Scholar, but it carries recurring operational cost (annual fee + per-DOI quota) and needs its own design pass. V1 uses the receipt URL as the stable identifier.

- **Rejected: `schema.org/SoftwareApplication`** — correct rejection, correct reason: the agent IS the software; the receipt is its output (measured data), not the software. Corroborated — no benchmark/leaderboard publisher uses SoftwareApplication at result granularity.
- **Rejected: `schema.org/ScholarlyArticle`** — REJECTION STANDS, but the parked reason ("over-claims peer-review status") was **wrong**: `schema.org/ScholarlyArticle` carries zero peer-review constraint in its spec, and preprint servers (arXiv, Zenodo) routinely self-apply it to non-peer-reviewed work. Corrected reason: **a battle receipt is measured data (→ Dataset → Google Dataset Search), not scholarly prose.** Right outcome, fixed rationale.
- **Custom `@context`** — the parked draft REJECTED this; the corrected decision ADOPTS the hybrid-context form (point 2 above). The "crawlers silently drop it" premise was empirically false.

### O3. SVG share-card in V1 — RATIFIED 2026-06-16: OG-tags only, dynamic per-receipt `og:image`

**Decision: no README-embeddable `.svg` share-card in V1; ship OG tags with a per-receipt dynamically-rendered `og:image` PNG.**

- cite_as's core value (paper citation, BibTeX, JSON-LD, Highwire meta tags) is entirely independent of an inline image. The README-inline-image slot is already occupied by the 11c badge SVG — a 11d SVG would be product overlap.
- **`og:image` is dynamic per-receipt** (carries `agent_name` + `winner` + `lane`), NOT a static agentdex logo — otherwise every Twitter/LinkedIn/Slack unfurl card looks identical and buries the battle facts in og:description text. Rendered on-demand at first fetch + cached on the page's `max-age=300`. Reuse the 11c badge SVG→raster pipeline.
- **Deferred to 11d.5: `GET /receipt/{battle_id}/{cite_token}.svg`** README-embeddable share-card. Strictly reversible-additive (same demand-deferral pattern as 11c D6) — no invariant breaks, ~50 src + ~80 tests when demand justifies it.
- **Rejected: ship neither OG nor SVG (JSON-LD only)** — loses Twitter/LinkedIn embed UX, undersells the paid feature.

## Out of scope (not 11d)

- **Per-paper-page rendering** (embedded battle-result widgets inside arXiv HTML, PDF citation footnote stamping) — deferred; reversible later as 11d.5 by extending receipt HTML to expose `<iframe>`-embeddable variants.
- **Multi-language cite formats** (CSL JSON, BibLaTeX-native `@software`, EndNote XML, RIS) — only `@misc` BibTeX + schema.org JSON-LD ship in V1; reversibly addable by adding `Accept: application/x-research-info-systems` etc. on `/receipt/{...}` without breaking the signed payload contract.
- **DOI minting (DataCite / Crossref)** — DEFERRED to 11d.5 / 11e per O2 ratification. A DataCite DOI is the only documented self-serve channel into Semantic Scholar (and a strong Scholar signal), but it carries recurring operational cost (annual membership + per-DOI fee/quota) and needs its own design pass (which authority mints, how the DOI binds to the cite_token, revocation semantics). V1 ships the receipt URL as the stable identifier + Highwire `citation_*` meta tags (the no-cost Scholar channel); DOI is a reversible add that does not change the signed-payload contract.
- **Citation graph indexing** (server-side tracking of which papers/URLs cite which battles, citation-count rollups on `/ladder`) — V1 receipts are stateless from the gateway perspective post-mint; a future graph layer can be added by scraping public receipt URLs in inbound HTTP referer logs without changing the signed payload.
- **Live re-simulation embedded in `/receipt` page** (O1 alternative) — paper-publishable receipts should be cheap to fetch; re-sim stays on `POST /battle/{battle_id}/dispute`.
- **SVG share-card endpoint** `/receipt/{battle_id}/{cite_token}.svg` (O3 alternative) — OG tags on the HTML page cover Twitter / LinkedIn / Slack embed in V1; SVG is reversibly addable later.
- **Owner-level cite quota pooling** (cross-agent under one owner) — V1 keys quota on `agent_name` per §3b §5e else-branch; durable owner→agents mapping (register_v2) is the 11e prerequisite, not 11d's job.
- **Cite revocation list / token blocklist endpoint** — kid-rotation is the V1 revocation primitive (matches §11c O2 ratification); explicit blocklist defers to 11d.5 if ever needed.
- **Auto-extending TTL while membership active** — D4 chose explicit re-mint instead; auto-extend would require verify-time membership lookup which D10 explicitly forbids (§3a violation).

## References

- ADR-0011 §1 (paid feature table) + §3 invariants (anti-pay-to-rank, §3b 11e binding, §3b §5e scope-conditional spend_quota, §3c property test, §3d no-silent-widening)
- ADR-0011 §8 (11c verified-badge SVG ratification — O1 separate-key blast-radius isolation precedent that this PR mirrors)
- 11c design spec: `docs/references/2026-06-14-arena-verified-badge-svg-design.md` (the structural template this design mirrors)
- 11c badge admin runbook: `docs/runbooks/badge-admin.md` (operator-only posture this 11d's `cite-admin.md` will mirror)
- 11c PRs that established the precedent: #129 (BadgeAuthority substrate), #130 (mint route + scope-conditional spend_quota), #132 (public render + verify endpoints), #133 (docs sync + ADR amendment + runbook)
- Bene-7 cross-team alignment 2026-06-15 04:32Z: 11d implements consumer layer against bene's stable replay-manifest substrate; thin-CLI reverse-PR into bene-main accepted after 11d.4 (≤200 LOC, hugging existing CLAIMS-AUDIT line 52 substrate)
- Workflow provenance: `wf_a0a5743a-8f3` (13 agents, 879k tokens, 9.8 min, 4 lens proposals × adversarial scoring)
- CLAUDE.md § "Membership gate call order" and § "Badge signing key + mint call order" (the doctrine sections this PR's call order mirrors)
