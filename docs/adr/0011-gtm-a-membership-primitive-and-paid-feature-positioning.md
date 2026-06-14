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
  - claim: "§3b V1 binding constraint 3: admin grant MUST NOT raise quotas['battle'] (battle quota stays symmetric per §3a)"
    test: "packages/agentdex_arena/tests/test_q5_anti_pay_to_rank_property.py::test_admin_grant_does_not_widen_battle_quota (ships PR-M)"
  - claim: "§3b V1 binding constraint 2: export PoP uses verify_export_pop with arena-export:{token_id}:{export_nonce}:{requested_agent_name} domain — NOT verify_pop's battle shape"
    test: "packages/agentdex_arena/tests/test_export_pop_domain_separation.py (ships 11e)"
  - claim: "§3b V1 binding constraint 5: register_v2 event persists durable {name, agent_pubkey_hex, owner_email_hash}; reissue verifies fresh PoP against the original registered pubkey, never against an expired token"
    test: "packages/agentdex_arena/tests/test_enroll_reissue_durable_mapping.py (ships register_v2 + reissue PR, blocks 11e)"
  - claim: "§3b V1 binding constraint 4: export selection closes under parent_battle_id (forks included) and joins period rows via payload.events[*].battle_id (rating receipts included)"
    test: "packages/agentdex_arena/tests/test_bulk_export_owner_scope.py::test_fork_battles_included_in_export + ::test_period_rating_receipts_included_in_export (ships 11e)"
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

This invariant binds the admin / membership-grant path symmetrically — see §3b V1 binding constraint 3 for the explicit lockout against raising `claims.quotas['battle']` at grant time, and §3c property test for the behavioural assertion.

Encoded as the property test in §3c.

#### 3b. Bulk export is server-side owner-scoped (locked 2026-06-14)

`GET /export/agent/<name>` (11e) MUST filter server-side so the caller can only export an agent they hold a valid `ConsentClaims` token for. It MUST NEVER return another owner's battles, ratings, evolution lineage, or any field derived from them. The export is paid because it is an enriched aggregate / format conversion of YOUR OWN data; it is NOT a paid window into other users' work.

(All other-owner data remains accessible to anyone — but only through the existing free `/replay/{id}`, `/ladder`, and `/methodology` surfaces, in the granular shapes those routes already serve.)

##### V1 binding: `caller.agent_name == requested_agent_name` (locked 2026-06-14)

The enrollment path persists `register` events with `{name, frozen}`; it does NOT persist a durable `agent → owner_email` mapping. The owner email is carried inside the 7-day `ConsentClaims` token only, and `_registered` is rebuilt from `register` events alone. Without a durable mapping the server cannot prove that an arbitrary requested agent name belongs to `caller.owner_email` after a 7-day token rotation; the alternative — trusting the agent name on the request — would let a paid caller export any owner's history by name.

V1 therefore narrows the §3b contract from `caller.owner_email == agent.owner_email` to **`caller.agent_name == requested_agent_name`**, with five constraints made explicit so the implementation cannot drift:

1. **Call order — membership gate is ADDITIVE; PoP is domain-separated from battle; quota shares the battle budget.** The 11e route runs the standard paid-feature gate stack defined in CLAUDE.md "Membership gate call order", extended with an export-shaped proof-of-possession step that mirrors the battle path's two-step nonce consumption (gateway.py:455-469):

   ```python
   # Issued by sister GET /export/begin route (analogous to /battle/start):
   #     export_nonce = secrets.token_hex(12)
   #     self.export_nonces[export_nonce] = claims.token_id
   #     return {"export_nonce": export_nonce,
   #             "pop_challenge": f"arena-export:{claims.token_id}:{export_nonce}:{agent_name}"}

   # On GET /export/agent/<name>:
   claims = authority.verify(token, scope="battle")              # 1. signature + expiry + scope
   authority.verify_membership(claims)                           # 2. §3 paid-feature gate (REQUIRED)
   if claims.agent_name != requested_agent_name:                 # 3. §3b V1 binding (additive)
       raise _opaque_error(403, "agent name mismatch")
   # 4a. Single-use nonce consumption lives in the gateway, NOT in the verifier
   #     (mirrors battle_begin's `self.battle_nonces.pop(...)` at gateway.py:467).
   if gateway.export_nonces.pop(export_nonce, None) != claims.token_id:
       raise _opaque_error(403, "unknown export nonce")
   # 4b. Domain-separated PoP verifier — a NEW helper that verifies a signature over
   #     `arena-export:{token_id}:{export_nonce}:{requested_agent_name}`. DO NOT reuse
   #     `verify_pop`, which is hard-coded to the battle challenge
   #     `arena-pop:{token_id}:{battle_nonce}` (consent.py:198-211) and would accept a
   #     cross-domain replay if reused. See constraint 2 for the helper definition.
   authority.verify_export_pop(claims, export_nonce, requested_agent_name, pop_signature_hex)
   authority.spend_quota(claims, scope="battle")                 # 5. daily cap (shares battle budget)
   # ... assemble export ...
   ```

   The agent-name check sits BELOW `verify_membership`, never around it. A future engineer reading "the route gates on agent-name match, not on membership tier" must understand that **agent-name match is the §3b owner-scoping invariant; the membership gate is the §3 paid-feature invariant. Both are required for V1 11e; neither replaces the other.**

2. **PoP-bound export with a NEW domain-separated helper — DO NOT reuse `verify_pop`.** Battle begin already requires the caller to sign `arena-pop:{token_id}:{battle_nonce}` with the Ed25519 key whose public half the owner registered at enrollment (gateway.py:466-469); a bearer-only export route would let a leaked token download the full paid history without the private key. 11e MUST therefore require an `export_nonce` (server-issued, single-use per request) plus an Ed25519 signature over `arena-export:{token_id}:{export_nonce}:{requested_agent_name}` — a SHAPE that is deliberately distinct from the battle PoP. The export endpoint emits the nonce from a sister `/export/begin` route the same way `/battle/start` issues `battle_nonce`.

   **Domain separation is load-bearing.** The existing `ConsentAuthority.verify_pop` (consent.py:198-211) is a `@staticmethod` that hard-codes the challenge string to `arena-pop:{token_id}:{battle_nonce}` via `pop_challenge` (consent.py:199-200). Reusing it for export would either (a) verify the WRONG message — silently passing if a leaked battle PoP signature is replayed against an export request that happens to use the same 12-byte hex nonce — or (b) require widening its signature with an `agent_name` parameter that battle callers do not pass. Neither path is safe. 11e MUST add a NEW helper:

   ```python
   # in consent.py, alongside pop_challenge / verify_pop:
   @staticmethod
   def export_pop_challenge(token_id: str, export_nonce: str, requested_agent_name: str) -> bytes:
       return f"arena-export:{token_id}:{export_nonce}:{requested_agent_name}".encode()

   @staticmethod
   def verify_export_pop(
       claims: ConsentClaims,
       export_nonce: str,
       requested_agent_name: str,
       signature_hex: str,
   ) -> None:
       agent_pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(claims.agent_pubkey_hex))
       try:
           agent_pub.verify(
               bytes.fromhex(signature_hex),
               ConsentAuthority.export_pop_challenge(
                   claims.token_id, export_nonce, requested_agent_name
               ),
           )
       except (ValueError, InvalidSignature) as e:
           raise ConsentError("export proof-of-possession failed") from e
   ```

   Single-use enforcement stays in the gateway (`gateway.export_nonces.pop(...)`) mirroring the battle path (`gateway.battle_nonces.pop(...)` at gateway.py:467) — `verify_export_pop`, like `verify_pop`, is a pure cryptographic check with no nonce-store reference. The two-step contract (gateway consumes nonce → verifier checks signature) is what makes the nonce truly single-use. The 11e integration test MUST assert that a signature over `arena-pop:{token_id}:{nonce}` (the battle shape) is REJECTED by `verify_export_pop` even when `nonce` and `token_id` match — locking domain separation as a behavioural invariant rather than a comment.

3. **No new scope; quota shared with battle; admin grant MUST NOT widen `battle` quota.** 11e accepts the standard tokens minted at enrollment (`["enroll", "battle", "evolve"]`) — gating on `scope="battle"` keeps existing agents reachable without a token-reissue endpoint. Free vs paid is determined by `verify_membership`, not by scope. The quota call MUST also spend the existing `battle` budget; an `export` scope would always trip `spend_quota`'s missing-key path (which returns cap 0; consent.py:158-167) on legacy claims minted only with `{"battle": 5, "evolve": 2}` — re-introducing the reachability problem this section is closing. Sharing the daily 5-battle budget keeps the V1 contract honest about export being a "your own data, repackaged" affordance, not a new compute budget.

   **The `battle` quota MUST stay symmetric across membership tiers.** No admin / membership-grant path — and no future operator knob — may raise `claims.quotas["battle"]` for a paying owner. The `battle` quota gates the RATED lane at gateway.py:470-471 (`if req.lane == "rated": self.authority.spend_quota(claims, scope="battle")`), and rated battles drive the `period` event stream consumed by `recompute_ladder` (gateway.py:849-870, events.py:130-164). A membership-tier-conditional raise of `quotas["battle"]` is precisely the asymmetric `/battle/*` runtime cap §3a forbids — paid owners would get more rated-ladder attempts per UTC day than free owners, which is pay-to-rank by proxy regardless of the operator's stated intent.

   If a paying customer credibly needs more export headroom than 5/day, the operator's only options are: (a) accept that V1 caps export at the shared 5/day budget and document it in `docs/runbooks/membership-admin.md` as the V1 contract; (b) ship a separate `export` scope + quota in V2 — the §3d-disciplined path, explicit new `ConsentClaims` scope, plaintext-disclosed on `/enrollment` and `/methodology`, signed at enroll, NOT silently re-minted. Path (b) is OUT OF SCOPE for V1 11e and MUST NOT be retrofitted by raising the battle cap.

   This is enforced by the §3c property test extended in PR-M: any code path — including an admin grant — that produces unequal rated-battle headroom across (free-owner, paid-owner) pairs with identical (skill, opponent sequence, N battles) violates the rating-ceiling-equality invariant and asserts directly that `claims.quotas["battle"]` is independent of membership status at mint time AND post-grant.

4. **History selection uses canonical `agent_name` + battle_id joins, NOT `claims.token_id` and NOT a flat `payload.visitor` filter; closes under `parent_battle_id` and joins `period.events[*].battle_id`.** The existing event feeds at gateway.py:1401-1406 and mcp_surface.py:250-253 filter by `payload.tenant_id == claims.token_id`; battle rows are written with the originating token's id (gateway.py:569-576 for `battle_begin`, gateway.py:809-816 for `battle_end`). A rotated token would pass the §3b agent-name check but silently drop the agent's pre-rotation history under a token-id filter. A naive `payload.visitor == agent_name` filter on every event type drops `battle_end` / `period` / `quarantine` rows entirely because those payloads carry only `tenant_id` + `battle_id` (no `visitor`). The contract therefore selects via a canonical join with three steps — visitor seed, fork closure, two-shape battle_id match:

   ```python
   # Step 1a: find the agent's seed battles by visitor (only battle_begin carries visitor).
   seed_battle_ids: set[str] = {
       ev["payload"]["battle_id"]
       for ev in gateway.events.iter_events()
       if ev["type"] == "battle_begin"
       and ev["payload"].get("visitor") == requested_agent_name
   }

   # Step 1b: close under fork traversal. battle_fork emits NO battle_begin
   # (gateway.py:885-934 only writes battle_fork → {tenant_id, battle_id,
   # parent_battle_id, fork_turn}); without this pass, every fork battle —
   # its battle_fork marker, its battle_end, any quarantine, plus any
   # fork-of-a-fork descendant — vanishes from the export even though the
   # fork route already proved the parent is owned by this tenant
   # (gateway.py:1306-1309 enforces sandbox-only + tenant-match at fork
   # time). Transitive closure handles fork-of-fork chains in one pass.
   agent_battle_ids: set[str] = set(seed_battle_ids)
   changed = True
   while changed:
       changed = False
       for ev in gateway.events.iter_events():
           if ev["type"] != "battle_fork":
               continue
           if ev["payload"].get("parent_battle_id") in agent_battle_ids:
               child = ev["payload"].get("battle_id")
               if child and child not in agent_battle_ids:
                   agent_battle_ids.add(child)
                   changed = True

   # Step 2: include EVERY related row. Two join shapes are REQUIRED, not
   # optional, because the EventLog stores `battle_id` in two places:
   #   - top-level    payload["battle_id"]              → battle_begin / battle_end /
   #                                                       quarantine / badge / battle_fork
   #   - nested       payload["events"][i]["battle_id"] → period (the ONLY rating-bearing row)
   # A single top-level filter silently drops every period row and ships an
   # export with battle metadata but no rating receipts — violating the
   # §3b promise of "battles, ratings, evolution lineage".
   def _touches_agent(ev: dict) -> bool:
       payload = ev.get("payload") or {}
       if payload.get("battle_id") in agent_battle_ids:
           return True
       if ev["type"] == "period":
           # period.payload = {"events": [RatingEvent(...).model_dump(), ...]}
           # mirrors recompute_ladder's read shape (events.py:157-164).
           return any(
               sub.get("battle_id") in agent_battle_ids
               for sub in payload.get("events", [])
           )
       return False

   rows = [
       ev for ev in gateway.events.iter_events()
       if (
           _touches_agent(ev)
           or (ev["type"] == "register"    and ev["payload"].get("name") == requested_agent_name)
           or (ev["type"] == "register_v2" and ev["payload"].get("name") == requested_agent_name)
           or (ev["type"] == "badge"       and ev["payload"].get("agent_name") == requested_agent_name)
       )
   ]

   # WRONG (1): flat visitor filter — drops battle_end / period / quarantine rows.
   #   if ev["payload"].get("visitor") == requested_agent_name
   #
   # WRONG (2): token-id filter — drops pre-rotation history.
   #   if ev["payload"].get("tenant_id") == claims.token_id
   #
   # WRONG (3): visitor-seed-only (no Step 1b closure) — drops the entire
   #   fork family (fork marker + fork end + fork quarantine) because the
   #   fork's new battle_id is introduced ONLY in battle_fork, which carries
   #   no visitor field. Without 1b, "remix-the-loss" history disappears.
   #
   # WRONG (4): top-level battle_id filter only — silently drops EVERY
   #   `period` row, because period nests battle_id at
   #   payload["events"][i]["battle_id"] (gateway.py:857-870, mirrored by
   #   events.py:157-164). Period rows carry the rating math; without them,
   #   the export has begins/ends but no Glicko deltas, which downstream
   #   recompute cannot reconstruct.
   #       if ev["payload"].get("battle_id") in agent_battle_ids   # ← misses period
   ```

   The agent-name check in §3b §1 above is what makes the canonical-identity join safe: only callers whose active token names `agent_name` can request that agent's full historical record. The Step 1b closure surfaces the `/battle/{id}/fork` "remix-the-loss" affordance — owner-created alternate timelines stay visible to the owner. Fork inclusion does NOT touch §3a: forks are sandbox-only (gateway.py:1306) and emit no `period` events (gateway.py:849), so the fork rows added to the export carry no rating math. The nested-period join, conversely, is what makes the export round-trippable through `recompute_ladder` — without it the agent's Glicko deltas are gone.

5. **V1 covers UNEXPIRED tokens only; reissue is a V1 11e prerequisite that requires a NEW durable mapping (`register_v2`) shipped FIRST.** `ConsentAuthority.verify` rejects past-`expires_at` tokens (consent.py:151-152) before returning claims; both enrollment paths reject duplicate `agent_name` (gateway.py:413-415, gateway.py:434-435). A paid owner whose 7-day token has expired before 11e ships therefore cannot present a matching token and cannot re-enroll under the same name. The token-reissue endpoint flagged "planned post-MVP" in `SKILL.md` Layer 1.2 is promoted to a **V1 11e prerequisite** — BUT the current substrate does not yet support it safely, and §3b must not pretend otherwise.

   **Gap (verified consent.py:89 + gateway.py:437-439):** the only `register` event payload is `{name, frozen}`. The `agent_pubkey_hex` lives inside `ConsentClaims` and transiently in `pending_enrollments`; the `owner` email is likewise only inside `ConsentClaims`. After token expiry the gateway has no durable `agent_name → agent_pubkey_hex` mapping and no durable `agent_name → owner_email` mapping. (An earlier draft of this paragraph said reissue "preserves the registered `agent_name + owner_pubkey_hex`" — that wording carried both a typo — the field is `agent_pubkey_hex`, not `owner_pubkey_hex` — AND a substantive error: there is nothing "registered" on the server side to preserve.) Accepting a signature-only parse of the expired token would let any replay of a leaked-then-rotated token re-mint a fresh 7-day window, gutting rotation.

   **V1 reissue contract — durable-mapping-first, two-step:**

   a. **Ship a new event type `register_v2`** (additive; old `register` events keep replaying for ladder recompute via events.py:155-156) carrying `{name, frozen, agent_pubkey_hex, owner_email_hash}`. `owner_email_hash` is `sha256(_normalize_owner(email))` so the durable mapping is owner-recoverable but does not store plaintext PII on disk. `enroll_confirm` writes BOTH `register` (back-compat) AND `register_v2` (new). Replay rebuilds two side-tables on the gateway: `_pubkey_by_name: dict[str, str]` and `_owner_hash_by_name: dict[str, str]`.

   b. **Ship `POST /enroll/reissue`** shaped like `/enroll/confirm/{code}`: caller supplies `{agent_name, owner_email}` and a fresh `pop_signature_hex` over `arena-reissue:{agent_name}:{reissue_nonce}` (nonce issued by a sister `/enroll/reissue/start` route, single-use). The handler verifies in this order:

      ```python
      pub_hex = gateway._pubkey_by_name.get(req.agent_name)
      if pub_hex is None:
          raise _opaque_error(404, "unknown agent")
      if gateway._owner_hash_by_name.get(req.agent_name) != sha256(_normalize_owner(req.owner_email)):
          raise _opaque_error(403, "owner mismatch")
      # PoP against the ORIGINAL registered pubkey — proves possession of the
      # private key the agent enrolled with, without trusting any expired token.
      if gateway.reissue_nonces.pop(req.reissue_nonce, None) != req.agent_name:
          raise _opaque_error(403, "unknown reissue nonce")
      Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex)).verify(
          bytes.fromhex(req.pop_signature_hex),
          f"arena-reissue:{req.agent_name}:{req.reissue_nonce}".encode(),
      )
      # Mint a fresh ConsentClaims with the SAME agent_name + agent_pubkey_hex
      # + owner, default scopes ["enroll", "battle", "evolve"], default quotas
      # {"battle": 5, "evolve": 2}. The default quotas are symmetric per
      # constraint 3 — reissue MUST NOT widen the battle cap.
      ```

      Reissue does NOT call `verify(expired_token)`; it does not touch the expired token at all. Proof-of-ownership flows entirely through the durable mapping + a fresh PoP signature against the original registered key. A leaked-then-rotated token is therefore useless: the attacker would also need the private half of `agent_pubkey_hex`, which never left the agent's machine. The reissue PoP shape (`arena-reissue:{agent_name}:{nonce}`) is intentionally distinct from both the battle (`arena-pop:`) and export (`arena-export:`) shapes — by definition no valid `token_id` exists at reissue time, so the join key is `agent_name`.

   c. **`register_v2` ships BEFORE 11e bulk export ships, and `POST /enroll/reissue` ships BEFORE OR WITH 11e.** Doing it in any other order leaves a gap where paid owners whose token expired during the 11e rollout window have no recovery path except a name change.

   d. **Reissue is free, not paid.** It is an identity-recovery primitive, not an enriched feature. Per §3a, gating recovery on membership would be pay-to-rank-by-proxy (a free user who lets a token expire could not resume their rated battles). The `/enroll/reissue` and `/enroll/reissue/start` routes MUST NOT carry `@require_membership`.

Users with multiple agents under one owner hold one `ConsentClaims` per agent (one enrollment per agent today) — they export each by presenting the matching token. This is a deliberate V1 constraint, not a bug: it forces explicit per-agent consent on every export call, which is the Mom-Test-disciplined posture (§3d). V2's relaxation to single-token multi-agent export is gated on the §3d `contribute_aggregate` scope landing — the `register_v2` durable mapping above is the substrate enabler, NOT the broadened data-flow consent.

##### V2+ extension: multi-agent owner-scoped bulk export

The durable substrate previously deferred here — a `register_v2` event carrying `{name, frozen, agent_pubkey_hex, owner_email_hash}` — has been escalated to a **V1 11e prerequisite** per §3b V1 binding constraint 5 (it is what makes `POST /enroll/reissue` implementable safely on expired tokens). The durable mapping lands in V1.

V2's remaining relaxation is the data-flow widening: a single export call covering ALL agents owned by `owner_email` (the `agents_for(owner_email)` query enabled by the V1 mapping). That relaxation broadens the per-call data flow from one-agent to multi-agent and therefore requires the §3d-disciplined `contribute_aggregate` `ConsentClaims` scope — plaintext-disclosed on `/enrollment` and `/methodology`, signed at enroll time, NEVER silently re-minted onto legacy tokens. V2 SHALL ship the scope BEFORE the 11e contract relaxes from `caller.agent_name == requested_agent_name` back to `caller.owner_email == agent.owner_email`; doing it in the other order trips the same data-leak risk this V1 binding closes.

Until V2 lands the scope, `caller.agent_name == requested_agent_name` is load-bearing — relaxing it without the consent in place is the explicit reversal, visible in code and in the integration test that ships with 11e.

#### 3c. Property test, not just diff-visibility test

`test_skill_md_does_not_mention_admin_surface` (shipped 11b.4) asserts the admin surface stays invisible. The complementary `test_q5_anti_pay_to_rank_property` (ships 11b.7) asserts the behavioural invariant: **for any (free-owner, paid-owner) pair with identical (skill, opponent sequence, N battles), the rating-ceiling expectation is equal**. If you can't write this test for a proposed paid feature, the design is pay-to-rank (in disguise or otherwise) — kill the design, not the test. The test went through several rounds of review-driven strengthening on 2026-06-14 (PRs #108/#109/#110/#113/#115/#116/#118 + this PR-K follow-up); the lineage is preserved at [docs/references/2026-06-14-q5-anti-pay-to-rank-test-evolution.md](../references/2026-06-14-q5-anti-pay-to-rank-test-evolution.md).

#### 3d. No silent free→paid data reinterpretation (locked 2026-06-14)

Any free→paid data flow — even aggregated, even non-PII — MUST go through a NEW `ConsentClaims` scope (proposed: `contribute_aggregate`) that the owner **explicitly signs at enroll time** AND is disclosed in plaintext on `/enrollment` and `/methodology`. The arena MUST NEVER silently reinterpret existing tokens to carry the new scope. This rules out Adobe/Slack/Zoom 2024 risk-template same-shape pivots where ToS reinterpretation took user content as training-data input without re-consent. §3d permits paid format conversion of capabilities already in scope on the existing token (e.g., 11e bulk export is a format conversion of the same `battle`-scoped read access `/replay/{id}` already serves); §3d does NOT permit silently widening the per-token budget for those capabilities — see §3b V1 binding constraint 3.

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
