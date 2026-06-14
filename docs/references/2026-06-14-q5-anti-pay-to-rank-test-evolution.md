---
title: "Q5 anti-pay-to-rank property test — strengthening lineage (2026-06-14)"
status: active
owner: "@EdwardTang"
created: 2026-06-14
updated: 2026-06-14
type: reference
scope: packages/agentdex_arena/tests
layer: service
cross_cutting: false
enforced_by:
  - "packages/agentdex_arena/tests/test_q5_anti_pay_to_rank_property.py (9 tests; ADR-0011 §3c)"
---

# Q5 anti-pay-to-rank property test — strengthening lineage (2026-06-14)

The `test_q5_anti_pay_to_rank_property.py` file is the load-bearing
behavioural + structural test for ADR-0011 §3c (anti-pay-to-rank-by-proxy
invariant). It went through five rounds of code-review-driven
strengthening on 2026-06-14; this doc captures the lineage so future
contributors can read the evolution rather than re-derive the rationale.

## Round 1 — initial ship (PR #108)

Five tests:
- `test_rating_event_has_no_membership_field`
- `test_recompute_ladder_signature_takes_no_membership_input`
- `test_ladder_class_has_no_membership_state`
- `test_rating_path_does_not_import_admin_or_consent` (events.py only)
- `test_rating_ceiling_independent_of_membership_status` + a gateway
  shape-check that only inspected an empty `{"entrants": {}}`

## Round 2 — structural-guard hardening (PR #109)

- `_FORBIDDEN_RATING_FIELDS` centralised + broadened with
  `owner / owner_email / tenant / tenant_id / member / premium / plan`.
- `test_rating_path_does_not_import_admin_or_consent` extended to scan
  `events.py` + `ladder.py` (the actual `Ladder.rate_period` math).

## Round 3 — gateway-emission property (PR #110)

- New `test_gateway_emission_path_does_not_couple_ladder_to_membership`
  drives identical 16-battle rated sequences through each gateway's own
  `EventLog` handle, comparing non-empty `ladder_public()` views.

## Round 4 — real `_finish` + order + recursive scan (PR #113)

- Switched the gateway-emission test from `gateway.events.append` to
  the production `gateway._finish(session, end)` path so any paid-only
  mutation inside `_finish` itself is observable.
- Ordered `list(items())` comparison on both the outer view and inner
  `entrants` dict catches pay-to-rank reordering that leaves per-row
  values untouched.
- `_assert_no_membership_shaped_keys` recurses into nested dicts +
  lists.

## Round 5 — glicko coverage + token-matching (PRs #115, #116, #118)

- `Rating` + `update_rating` added to `rating_path_symbols` so the
  scan covers `glicko.py` (PR #115).
- Two new field/sig denylist tests for `Rating.model_fields` and
  `update_rating` signature (PR #116).
- Switched the denylist from exact-name set intersection to
  snake-case token matching via `_leaks_membership_shape(name)` so
  compound aliases like `paid_owner`, `member_until`, `tier_level`
  trip the guard (PR #118).

## Round 6 — real claims + battle_begin mirror + visitor-loses (PR #113 followup)

- `_build_real_claims()` constructs production-shaped `ConsentClaims`
  (real `owner`, `agent_name`, `agent_pubkey_hex`, scopes, quotas);
  `BattleSession.claims_token_id = claims.token_id` matches the
  production assignment at `gateway.py:506-508` so any future
  paid-by-`claims.owner` regression observes the real owner field.
- Mirror `battle_begin` event before each `_finish` so
  `_check_collusion`'s `begin_map` sees production-shaped participant
  history.
- Winner pattern flipped (`[p2, p1, p2, p2, p2, p1, p2, p2]`) so the
  visitor loses 12/16; opponent sorts ahead and a paid-first reorder
  in the paid view diverges the ordered `list(items())` comparison
  (previously vacuous because the visitor was already on top).

## Round 7 — thread owner onto the session (PR #120 followup)

- Round 6 built a real `ConsentClaims` but `claims.owner` died
  immediately after construction because `BattleSession` has no
  `owner` field — it carries only `claims_token_id` and `visitor_name`,
  and the mirrored `battle_begin` payload carries `tenant_id` /
  `visitor` / `opponent`. A future paid-only emission branch in
  `_finish` reading the owner string had nowhere to read it from.
- `_run_rated_battle_via_finish` now attaches `session.owner =
  claims.owner` as a dynamic attribute (current production
  `BattleSession` at gateway.py:217-247 is a plain `@dataclass` with
  no `__slots__`, so this works without source changes). This mirrors
  what production code would do if it ever wired the owner through
  for membership-keyed emission — either by adding an `owner` field
  to `BattleSession`'s definition or via a hypothetical
  `authority.owner_for_token` lookup.

## Final state (after round 7)

9 tests. 5 structural guards (4 model/sig denylists + 1 multi-module
scan) running through a single `_leaks_membership_shape(name)` matcher.
1 behavioural property at `recompute_ladder` level. 1 behavioural
property at gateway `_finish` level driving real `ConsentClaims` +
production-shaped event history + `session.owner` carrying the
membership-context surface. 1 ADR↔code parity check.

## References

- ADR-0011 §3c (anti-pay-to-rank property test as code invariant)
- PRs #108, #109, #110, #113, #115, #116, #118, #120, plus PR-M
  (this round's follow-up).
