---
title: "ADR-0011: GTM-A — per-owner monthly membership primitive + repositioned paid feature surface"
status: active
owner: "@EdwardTang"
created: 2026-06-13
updated: 2026-06-14
type: reference
scope: docs/adr
layer: cross-cutting
cross_cutting: true
enforced_by:
  - claim: "§3 admin surface absent from SKILL.md (operator-only)"
    test: "packages/agentdex_arena/tests/test_membership_primitive.py::test_skill_md_does_not_mention_admin_surface"
  - claim: "§3 failed admin attempts do not bloat EventLog (audit lives in logs)"
    test: "packages/agentdex_arena/tests/test_membership_primitive.py::test_failed_admin_attempts_do_not_bloat_eventlog"
  - claim: "§3 plaintext admin token never appears in events.jsonl bytes"
    test: "packages/agentdex_arena/tests/test_membership_primitive.py::test_event_payload_shape_and_plaintext_token_never_in_events_file"
  - claim: "§3c rating ceiling is independent of membership status (property test)"
    test: "packages/agentdex_arena/tests/test_q5_anti_pay_to_rank_property.py (ships 11b.7)"
  - claim: "§3b V1 binding: 11e bulk export gates on caller.agent_name == requested_agent_name (ships 11e)"
    test: "packages/agentdex_arena/tests/test_bulk_export_owner_scope.py (ships 11e)"
  - claim: "§3d no silent free->paid data reinterpretation; new ConsentClaims scope contribute_aggregate required (ships V2+)"
    test: "deferred to V2+ when scope lands"
---

# ADR-0011: GTM-A — per-owner monthly membership primitive + repositioned paid feature surface

**Date:** 2026-06-13
**Status:** Accepted
**References:** ADR-0010 (Glicko-2 + credits), [parked membership-primitive design](../../.supergoal-v2/parked/membership-primitive-design.md), [Mom-Test research synthesis](../references/2026-06-13-mom-test-research.md) (workflow `wf_17e0b95a-9d6`, 101 agents, 5M tokens, 70 verified findings)
**Provenance:** Mom-Test research workflow returned `ship_paid_features` with critical anti-pay-to-rank repositioning; membership-primitive design workflow `wf_876d5fed-5da` (22 agents, 1.28M tokens, 5 lenses × 3 adversarial critiques × synthesis) produced 8 implementation steps + 14 test scenarios.

## Context

Phase 11 of agentdex-cli activates monetization on top of the arena substrate. The 2026-06-13 Mom-Test research validated all three discovery questions (`yes_market_exists` × 3):

- **Q1 (capability claims):** 24 verified findings — Live-SWE-agent (79.2% SWE-bench), MiniMax-M2 (5-benchmark table), AWorld (67.89% GAIA), Sonar press release ("Reaching #1 on SWE-bench Verified proves…"), Sentient EvoSkill launch, individual HN commenters. **People do anchor public claims on benchmark numbers.**
- **Q2 (eval pain articulators):** 14 verified findings — Hamel Husain (50+ consulting clients), Shreya Shankar (Berkeley), r/AI_Agents + r/LocalLLaMA threads, `WebCanvas` + `EvalView` OSS projects. **The pain is named and current.**
- **Q3 (pricing anchors):** 32 verified findings, well-populated $29-$249/mo self-serve band — Langfuse $29, LangSmith $39/seat, Arize $50, W&B $60, Helicone $79, Galileo $100, Braintrust $249, HuggingFace PRO $9 floor, Patronus $10 metered. **But:** every pure leaderboard is unanimously free + anti-pay-to-play — ARC Prize reimburses submitters up to $2,500, LMSYS is gift-funded, BigCodeBench/HF Open LLM/LiveCodeBench all free.

## Decision

### 1. Repositioned paid feature surface (drop B2C, ship B2B receipt service)

The earlier B2C framing (paid coach comments, paid doubles-self, paid doubles-A2A matchmaking) failed the Mom-Test against free `play.pokemonshowdown.com`. Repositioned V1 paid features:

| Free tier (forever) | Paid tier ($29/mo solo, $49/mo team) |
|--------------------|-------------------------------------|
| Public `/ladder` ranking | Embeddable **verified badge SVG** (signed, anti-spoof) |
| 1v1 sandbox + rated battles | Signed **replay URLs** + `cite_as` BibTeX block |
| Replays, evolution requests, gym leaders | **Bulk API export** of agent history (battles, ratings, evolution lineage) |
| Unverified watermarked badge | **Regression gate** ("catch silent regressions before users do" — EvalView framing) |
| 7-day retention | 90-day retention (paid tier; matches Langfuse Plus) |

### 2. Pricing anchors (Q4 default-decided per evidence)

- **Solo: $29/mo** (mirrors Langfuse Core $29, lowest published self-serve entry in eval/observability)
- **Team: $49/mo** (mirrors LangSmith Plus $39/seat × small-team multiplier)
- Enterprise (V2+): contact-sales, $249+ band when buyer is funded-team / org-wide adoption
- Free tier: indefinite, no quota on `/ladder` listing, 7-day retention on artifacts

### 3. Anti-pay-to-rank as code invariant (Q5 default-decided per evidence)

`/ladder` stays public + free **forever**. The membership gate exists only on **enrichment endpoints** (badge SVG signing, bulk export, signed replay, regression gate). Rationale: Q3 evidence unanimous — every credibility leaderboard is free + anti-pay-to-play (ARC reimburses submitters up to $2,500; LMSYS gift-funded). If we ever break this discipline, the leaderboard's value as a third-party receipt collapses to a paid-rec list.

Encoded as: there is NO `@require_membership` decorator on `/ladder`, `/replay/{id}`, `/methodology`, `/skill.md`, `/whoami`, `/enrollment`, `/battle/start`, `/battle/begin`, `/battle/{id}/choose`, `/battle/{id}/state`, `/evolution/request`, `/battle/{id}/fork`, `/battle/{id}/dispute`. The gate goes ONLY on the new V2-onward paid endpoints (badge/signing/export/gate).

#### 3a. Pay-to-rank-by-proxy is also forbidden (locked 2026-06-14)

Diff-visibility (no decorator on `/ladder`) is **necessary but not sufficient**. The following indirect pay-to-rank shapes are equally forbidden:

- **Rate-limit predicates referencing `is_paying_member(owner)`** whose path leads to `events.append(...)` on a stream consumed by `recompute_ladder()`. A free user throttled out of finishing their N rated battles within the timing window has been pay-to-ranked by proxy. Reject at design-review even when no explicit decorator exists.
- **Runtime caps on `/battle/*`** that differ by membership tier (even without a decorator). The Codeforces analogy misleads — Codeforces rate-limit is symmetric anti-abuse, NOT "compute for rating." Symmetric rate-limits (e.g., per-IP) are fine; asymmetric (member-vs-free) are not.

Encoded as the property test in §3c.

#### 3b. Bulk export is server-side owner-scoped (locked 2026-06-14)

`GET /export/agent/<name>` (11e) MUST filter server-side so the caller can only export an agent they hold a valid `ConsentClaims` token for. It MUST NEVER return another owner's battles, ratings, evolution lineage, or any field derived from them. The export is paid because it is an enriched aggregate / format conversion of YOUR OWN data; it is NOT a paid window into other users' work.

(All other-owner data remains accessible to anyone — but only through the existing free `/replay/{id}`, `/ladder`, and `/methodology` surfaces, in the granular shapes those routes already serve.)

##### V1 binding: `caller.agent_name == requested_agent_name` (locked 2026-06-14)

The enrollment path persists `register` events with `{name, frozen}`; it does NOT persist a durable `agent → owner_email` mapping. The owner email is carried inside the 7-day `ConsentClaims` token only, and `_registered` is rebuilt from `register` events alone. Without a durable mapping the server cannot prove that an arbitrary requested agent name belongs to `caller.owner_email` after a 7-day token rotation; the alternative — trusting the agent name on the request — would let a paid caller export any owner's history by name.

V1 therefore narrows the §3b contract from `caller.owner_email == agent.owner_email` to **`caller.agent_name == requested_agent_name`**. The 11e route MUST verify the active `ConsentClaims.scopes` contains the new `export` scope AND `requested_agent_name == claims.agent_name`; anything else is a 403. This is provably implementable on the existing event shape (no new event type, no schema migration) and the (free, paid) rating-ceiling invariant in §3c still holds because the route gates on agent-name match, not on membership tier.

Users with multiple agents under one owner hold one `ConsentClaims` per agent (one enrollment per agent today) — they export each by presenting the matching token. This is a deliberate V1 constraint, not a bug: it forces explicit per-agent consent on every export call, which is the Mom-Test-disciplined posture (§3d).

##### V2+ extension: durable `agent → owner_email` mapping

If multi-agent bulk export under a single owner becomes a real customer ask — a user with 5 agents wanting ONE export call covering all 5 without juggling 5 tokens — V2 SHALL introduce a durable `agent_owner` event type (or extend `register` with an `owner_email_hash` field) so the gateway can answer `agents_for(owner_email)` from the EventLog after token rotation. That event SHALL ship BEFORE the 11e contract relaxes from `caller.agent_name == requested_agent_name` back to `caller.owner_email == agent.owner_email`; doing it in the other order trips the same data-leak risk this V1 binding closes.

Until V2 lands the durable mapping, `caller.agent_name == requested_agent_name` is load-bearing — relaxing it without the mapping in place is the explicit reversal, visible in code and in the integration test that ships with 11e.

#### 3c. Property test, not just diff-visibility test

`test_skill_md_does_not_mention_admin_surface` (shipped 11b.4) asserts the admin surface stays invisible. The complementary `test_q5_anti_pay_to_rank_property` (ships 11b.7) asserts the behavioural invariant: **for any (free-owner, paid-owner) pair with identical (skill, opponent sequence, N battles), the rating-ceiling expectation is equal**. If you can't write this test for a proposed paid feature, the design is pay-to-rank (in disguise or otherwise) — kill the design, not the test.

#### 3d. No silent free→paid data reinterpretation (locked 2026-06-14)

Any free→paid data flow — even aggregated, even non-PII — MUST go through a NEW `ConsentClaims` scope (proposed: `contribute_aggregate`) that the owner **explicitly signs at enroll time** AND is disclosed in plaintext on `/enrollment` and `/methodology`. The arena MUST NEVER silently reinterpret existing tokens to carry the new scope. This rules out Adobe/Slack/Zoom 2024 risk-template same-shape pivots where ToS reinterpretation took user content as training-data input without re-consent.

### 4. Membership primitive shape (per parked design)

Per-owner monthly membership, manual flip-the-bit V1 (Stripe deferred to V2). Detailed spec at `.supergoal-v2/parked/membership-primitive-design.md` (8 implementation steps, 14 test scenarios, zero open architectural questions). Key shape:

- **Owner-keyed:** `memberships: dict[str, float]` keyed by normalized owner email → `valid_until_epoch`. Survives 7-day token rotation (owners can re-enroll without losing membership).
- **Admin grant:** `POST /admin/grant-membership` with `X-Admin-Token` header (SHA-256 hash compared via `hmac.compare_digest`). Hash lives in env `ARENA_ADMIN_TOKEN_HASH`; plaintext NEVER touches the runtime container.
- **Replay survives restart:** `membership_grant` events appended to EventLog, replayed on gateway construction.
- **Revocation = re-grant with `valid_until_epoch <= now`** (single code path; audit trail preserved).
- **Lazy expiry:** `verify_membership(claims)` checks `valid_until > self._now()`; no cron sweep needed.
- **Probe surface:** the existing `GET /whoami` (PR #96) already returns the active token's claims summary; phase-12 will extend it with `tier` + `membership_expires_at` when the gate ships.

### 5. Q1 (Mom-Test outreach) — resolved 2026-06-13: no warm intros, pivot to organic-pull

Relayed to harness-5 orchestrator (2026-06-13 23:46Z); user replied (2026-06-13 23:55Z): **no 1st-degree connection and no ≤1-hop intro path** to Hamel Husain, Shreya Shankar, or Yashwanth Sai.

**Outreach pivot:** the absence of warm intros forces two paths (Mom-Test-disciplined; default to **organic-pull**, not cold):

1. **Organic-pull (primary, ship-first):** publish the verified badge SVG + signed replay artifacts as free public infra. Instrument fetch/embed funnels (Q2 surface). The target personas — repeated public articulators of eval-pain — will self-select once the artifact exists and is being embedded by other builders. No cold outreach until organic embed signal materializes.
2. **Cold (secondary, only if Q2 funnel stalls):** Hamel's evals-course Slack; Shreya's substack/lab Twitter (`@sh_reya`) replies on her own eval-pain threads; Yashwanth's own r/AI_Agents threads. Always opens with "I built X for the pain you described in <link>" — never "would you buy" (Mom-Test rule).

**Implication for ship:** Q1 outcome accelerates the badge SVG (11c) implementation because organic-pull requires the artifact in-market first. The instrumentation surface (Q2 default) becomes load-bearing for outreach feedback loop, not optional.

### 6. Q2 (existing usage signals) — default-decided

Platform launched <1 week ago; no prior badge embeds or signed-URL re-fetches exist. Default: **instrument from scratch**, build the funnel-measurement surface alongside the first paid feature (verified badge SVG). Specifically: count badge SVG fetches per `agent_name`, group by referrer origin (extracted from `Referer` header, host-only), expose to admin via a future `GET /admin/badge-fetches/{agent}` endpoint (V2).

### 7. Q3 (Sonar/MiniMax/etc. design-partner outreach) — default-decided

Default: **defer to V2**. Cold outreach to those companies is expensive and premature; ship the public free badge first, let usage signal (Q2 instrumentation) drive partnership conversations once we see organic embeds in READMEs.

## Implementation roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 11a (THIS ADR + spec) | Capture decisions; doc-only | shipping in PR following this ADR |
| 11b (membership primitive) | Parked 8-step design, 14-test suite | sequential tiny PRs per `.supergoal/ADDENDUM_GIT_PR_DISCIPLINE.md`; first PR = `admin_auth.py` |
| 11c (verified badge SVG) | First paid feature; smallest, highest demo signal | after 11b lands clean |
| 11d (signed replay + cite_as) | Second paid feature; closes outsider-verifiable receipt loop | after 11c |
| 11e (bulk API export) | Third paid feature; serves AI labs / researchers | after 11d |
| 11f (regression gate) | Fourth paid feature; serves CI-integrated builders | after 11e |
| 12 (Stripe ingress) | Replace manual flip-the-bit with Stripe webhook | after V1 has ≥3 paying customers |

## Consequences

**Positive:**
- Free tier credibility preserved (anti-pay-to-rank discipline matches Q3 evidence)
- Pricing in proven self-serve band ($29-$49) reduces buyer-friction risk
- Per-owner keying lets power users run multiple agents under one subscription
- Manual flip-the-bit V1 avoids 1-2 weeks of Stripe integration overhead before product-market signal lands

**Negative / risks:**
- Manual grant is a founder-cost ceiling — capped at ~20 customers before automation pressure
- Q3 evidence shows the eval/observability market is crowded (Langfuse, LangSmith, Arize, Galileo, Braintrust all well-funded); differentiation rests on the *artifact* (signed replay + verified badge) NOT on general LLM observability
- Free leaderboard is a public-goods commitment — if a Sonar-class buyer asks for paid ranking, declining is a founder-discipline call that needs to hold

**Reversibility:**
- Manual grant → Stripe webhook is a strict extension (V2 adds webhook handler, V1 admin endpoint stays as fallback)
- Pricing tier amounts are env-configurable via `MEMBERSHIP_PRICE_SOLO_USD` / `MEMBERSHIP_PRICE_TEAM_USD`
- The anti-pay-to-rank invariant is encoded as the absence of a `@require_membership` decorator on `/ladder` — adding one would be the explicit reversal, visible in diff

## Provenance

- **Mom-Test research workflow** `wf_17e0b95a-9d6` (2026-06-13, 101 agents, 5M subagent tokens, 20 min, 10 sweeps + 87 verifies + 3 per-Q syntheses + meta synthesis). Raw output: `/tmp/claude-1000/.../tasks/wnoq61wvq.output`. Will distill into `docs/references/2026-06-13-mom-test-research.md` as a follow-up.
- **Membership-primitive design workflow** `wf_876d5fed-5da` (2026-06-13, 22 agents, 1.28M tokens, 12 min, 5 design lenses × 3 adversarial critiques × synthesis). Parked spec: `.supergoal-v2/parked/membership-primitive-design.md` (28KB, 8 steps, 14 tests).
- **User ratification** of `1. yes 2. yes` (2026-06-13 23:45Z) — activated parked design + authorized 5-Q triage.
