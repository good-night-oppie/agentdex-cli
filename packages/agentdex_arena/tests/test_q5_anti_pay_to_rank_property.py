"""Q5 anti-pay-to-rank PROPERTY test (ADR-0011 §3c — locked 2026-06-14).

`test_skill_md_does_not_mention_admin_surface` (11b.4) asserts the admin
surface stays invisible to agent clients. That's necessary but NOT sufficient
to prove the Q5 invariant. This file ships the complementary BEHAVIORAL
property test:

    For any (free, paid) owner pair with identical (skill, opponent sequence,
    N battles), the rating-ceiling expectation is equal.

Plus a STRUCTURAL test on the rating-path code so a future refactor that
adds a `is_member` parameter to RatingEvent / recompute_ladder fails at
import time, not at runtime.

If a future paid-feature proposal cannot keep these tests green, the proposal
IS pay-to-rank (by proxy or otherwise) — kill the proposal, NOT the tests.

This is the load-bearing test for ADR-0011 §3c.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from typing import TYPE_CHECKING

from agentdex_arena.admin_auth import AdminAuthority
from agentdex_arena.consent import ConsentAuthority

if TYPE_CHECKING:
    from agentdex_arena.consent import ConsentClaims  # for _build_real_claims return type
from agentdex_arena.gateway import ArenaGateway
from agentdex_engine.modules.arena import RatingEvent, recompute_ladder
from agentdex_engine.modules.arena.events import EventLog
from agentdex_engine.modules.arena.glicko import Rating, update_rating
from agentdex_engine.modules.arena.ladder import Ladder
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_ADMIN_TOKEN = "q5-property-test-admin"  # noqa: S105 — fixture
_ADMIN_HASH = hashlib.sha256(_ADMIN_TOKEN.encode()).hexdigest()
_NOW = 1_700_000_000.0


# ---- structural invariants (fail at import / signature inspection) ----


# Forbidden EXACT names — multi-token denylist entries kept as exact matches
# because the snake-case-token splitter below would not catch them (e.g.
# `valid_until_epoch` splits into ["valid", "until", "epoch"], none of which
# would be in the single-word token set on their own).
_FORBIDDEN_RATING_FIELDS = frozenset(
    {
        # explicit membership shapes
        "membership",
        "memberships",
        "is_member",
        "is_paid",
        "subscription",
        "valid_until_epoch",
        "actor_hash",
        # owner / tenant identifiers that would let rating join against memberships
        "owner",
        "owner_email",
        "tenant",
        "tenant_id",
        # paid-feature aliases observed across Langfuse / LangSmith / Braintrust
        "member",
        "premium",
        "plan",
        "tier",
        "paid",
    }
)

# Single-word forbidden TOKENS — caught at any position inside a snake-case
# name. Without this set, the earlier exact-name intersection let compound
# aliases slip through:
#   - `paid_owner`   carries `paid` AND `owner` but matches neither exactly
#   - `member_until` carries `member` but matches no exact entry
#   - `tier_level`   carries `tier`   but matches no exact entry
#   - `_owner_email` (private attr) → splits to ["owner", "email"]; `owner` matches
# A future `update_rating(..., paid_owner=False)` or `Rating(.., member_until=0)`
# now trips the guard. The set is conservative — only the *unambiguous* paid/
# membership/identity tokens; legitimately-overloaded words (e.g. "rating",
# "ladder") are NOT included.
_FORBIDDEN_RATING_TOKENS = frozenset(
    {
        "membership",
        "memberships",
        "member",
        "premium",
        "subscription",
        "tier",
        "paid",
        "owner",
        "tenant",
        "plan",
    }
)


def _snake_tokens(name: str) -> set[str]:
    """Lowercased snake_case tokens, stripping any leading underscores so
    private-attr `_owner_email` tokenises the same as public `owner_email`.
    `"_paid_owner"` → `{"paid", "owner"}`; `"tier"` → `{"tier"}`."""
    return {tok for tok in name.lower().lstrip("_").split("_") if tok}


def _leaks_membership_shape(name: str) -> bool:
    """True if `name` is an EXACT denylist entry OR carries a single-word
    forbidden token in its snake_case split. This is the combined check
    every structural guard now uses — exact-name coverage for multi-token
    entries (`valid_until_epoch`, `actor_hash`) plus token coverage for
    compound aliases (`paid_owner`, `member_until`, `tier_level`)."""
    lowered = name.lower()
    if lowered in _FORBIDDEN_RATING_FIELDS or lowered.lstrip("_") in _FORBIDDEN_RATING_FIELDS:
        return True
    return bool(_snake_tokens(name) & _FORBIDDEN_RATING_TOKENS)


def test_rating_event_has_no_membership_field():
    """RatingEvent schema must not reference membership / paid / tier / etc.,
    including compound aliases like `paid_owner` or `member_until` that
    would slip through an exact-name intersection.

    If a future refactor adds such a field, this test catches it before any
    paid-feature route can read it — encoding the anti-pay-to-rank-by-proxy
    invariant at the type-system level."""
    leak = {f for f in RatingEvent.model_fields if _leaks_membership_shape(f)}
    assert not leak, f"RatingEvent leaks membership-shaped field(s): {leak}"


def test_rating_model_has_no_membership_field():
    """`Rating` (glicko.py) carries the per-player score state — `rating`,
    `rd`, `vol`, `games`. A future paid-by-proxy field added directly to
    the model (e.g. `tier`, `owner_email`, `paid_owner`, `member_until`)
    would let the rating pipeline join against membership state at the
    type-system level even without any membership import.

    Score-state companion to `test_rating_event_has_no_membership_field`
    (the event side); both run their model fields through the same
    `_leaks_membership_shape` matcher so the denylist + token set scale
    atomically across both sides of the rating path."""
    leak = {f for f in Rating.model_fields if _leaks_membership_shape(f)}
    assert not leak, f"Rating leaks membership-shaped field(s): {leak}"


def test_update_rating_signature_takes_no_membership_input():
    """`update_rating(player: Rating, results: list[tuple[Rating, float]])`
    is the per-player math `Ladder.rate_period` delegates to. A future
    signature addition like `membership=None`, `tier="free"`, or the
    reviewer's exact regression case `paid_owner=False` would let the math
    branch on payment status at the most load-bearing function in the
    rating pipeline.

    Parallel to `test_recompute_ladder_signature_takes_no_membership_input`
    one level up the call chain."""
    sig = inspect.signature(update_rating)
    leak = {p for p in sig.parameters if _leaks_membership_shape(p)}
    assert not leak, f"update_rating signature leaks membership params: {leak}"


def test_recompute_ladder_signature_takes_no_membership_input():
    """recompute_ladder must depend only on (log_path, frozen, expected_digest).

    Any future signature addition of membership/paid/tier — or any compound
    alias carrying those tokens — means the rating pipeline now branches on
    payment status, pay-to-rank-by-proxy."""
    sig = inspect.signature(recompute_ladder)
    leak = {p for p in sig.parameters if _leaks_membership_shape(p)}
    assert not leak, f"recompute_ladder signature leaks membership params: {leak}"


def test_ladder_class_has_no_membership_state():
    """`Ladder._ratings` / `_frozen` / `badges` — no membership store. If
    a future engineer adds one (paid users get rating boost / decay
    protection / etc.) — public name like `tier` or compound private like
    `_paid_owner_cache` — this test fires.

    Both public and leading-underscore-private attribute names are run
    through the same matcher; `_snake_tokens()` strips leading underscores
    so `_owner_email` tokenises identically to `owner_email`."""
    all_attrs = {a for a in dir(Ladder()) if not a.startswith("__")}
    leak = {a for a in all_attrs if _leaks_membership_shape(a)}
    assert not leak, f"Ladder leaks membership state: {leak}"


def test_rating_path_does_not_import_admin_or_consent():
    """Every rating-path module — currently events.py (recompute_ladder),
    ladder.py (RatingEvent + Ladder.rate_period), AND glicko.py (Rating +
    update_rating) — must not import AdminAuthority or membership helpers
    from agentdex_arena.consent.

    The first scan only read the source of `recompute_ladder` (events.py),
    then PR #109 extended it to `ladder.py` because `Ladder.rate_period` is
    where the per-period math happens. But `rate_period` delegates each
    rating update to `update_rating(player, results)` in `glicko.py`, and
    the `Rating` class itself lives there too — a future paid-by-proxy
    field added to `Rating` (e.g. `owner_email` / `tier`) or a membership
    branch in `update_rating` would have slipped through scans that only
    covered events.py + ladder.py. Adding `Rating` + `update_rating` to
    the symbol set closes that gap and preserves the doctrine: adding a
    new module to the rating path means adding its source-defining symbol
    here too."""
    rating_path_symbols = (recompute_ladder, RatingEvent, Ladder, Rating, update_rating)
    sources = {inspect.getsourcefile(obj) for obj in rating_path_symbols}
    sources.discard(None)
    assert sources, "could not resolve any rating-path source file"
    forbidden_imports = [
        "from agentdex_arena.consent import",
        "from agentdex_arena.admin_auth import",
        "import agentdex_arena.admin_auth",
        "verify_membership",
        ".memberships",
    ]
    for src in sorted(sources):
        text = Path(src).read_text()
        for needle in forbidden_imports:
            assert needle not in text, (
                f"rating path ({src}) references {needle!r} — pay-to-rank-by-proxy risk"
            )


# ---- behavioral property: same input → same rating regardless of membership ----


def _build_rated_events(
    *,
    p1: str,
    p2: str,
    n_battles: int,
    winner_pattern: list[str],
) -> list[dict]:
    events = []
    for i in range(n_battles):
        winner = winner_pattern[i % len(winner_pattern)]
        if winner == "p1":
            w = p1
        elif winner == "p2":
            w = p2
        else:
            w = ""
        events.append(
            {
                "battle_id": f"battle-{i:04d}",
                "p1": p1,
                "p2": p2,
                "winner": w,
                "input_log_blake2b16": f"{i:032x}",
            }
        )
    return events


def _make_event_log_with_battles(
    tmp_path: Path,
    *,
    p1: str,
    p2: str,
    n_battles: int,
    winner_pattern: list[str],
) -> Path:
    """Build an event log with `register` events for both players + N battles
    of paired RatingEvents (one per battle). Winners pattern is cycled."""
    log_path = tmp_path / "events.jsonl"
    elog = EventLog(log_path)
    elog.append("register", {"name": p1, "frozen": False})
    elog.append("register", {"name": p2, "frozen": False})
    elog.append(
        "period",
        {
            "events": _build_rated_events(
                p1=p1, p2=p2, n_battles=n_battles, winner_pattern=winner_pattern
            )
        },
    )
    return log_path


def _build_real_claims(
    *,
    owner: str,
    agent_name: str,
    token_id: str,
) -> ConsentClaims:
    """Build a production-shaped `ConsentClaims` so the membership-context
    information travels through `BattleSession` + `battle_begin` + `_finish`
    via the same field shape production uses: `claims.owner` (what
    `verify_membership` keys on per consent.py:179-180) and
    `claims.token_id` (what `BattleSession.claims_token_id` stores per
    gateway.py:506-508).

    The earlier helper passed a token-id surrogate string
    `f"tok-{owner_email}"` which production code never sees; a future
    regression like `if self.authority.is_paid_owner(claims.owner):
    rating_event["bonus"] = +200` could not observe the paid membership
    via that surrogate."""
    from agentdex_arena.consent import ConsentClaims

    return ConsentClaims(
        token_id=token_id,
        owner=owner,
        agent_name=agent_name,
        agent_pubkey_hex="0" * 64,
        scopes=["enroll", "battle", "evolve"],
        issued_at=_NOW,
        expires_at=_NOW + 7 * 86_400,
        confirmed_via="q5-property-test-fixture",
    )


async def _run_rated_battle_via_finish(
    gateway: ArenaGateway,
    *,
    claims: ConsentClaims,
    opponent: str,
    winner: str,
    battle_id: str,
) -> None:
    """Drive one rated battle through the REAL production end-of-battle code
    path — `gateway._finish(session, end)` — with the production-shaped
    `battle_begin` event appended FIRST so `_check_collusion`'s
    win-transfer scan and any future paid-by-owner logic see the same event
    history production code does.

    Earlier this helper skipped the `battle_begin` append (production does
    that in `battle_begin()` per gateway.py:560-578 before `battle_choose`
    can ever call `_finish`). Without it, `_check_collusion`'s `begin_map`
    is empty and the win-transfer rail's `total_matches` counter stays at
    0 — a paid-specific change in the collusion gate, or a future
    membership-dependent emission branch keyed off prior `battle_begin`'s
    `visitor`/`tenant_id` join, would have been silently bypassed.

    Driving `_finish` directly + mirroring the `battle_begin` event closes
    that gap: every production line in `_finish` runs over the same event
    history shape production code sees."""
    from agentdex_arena.gateway import BattleSession

    # Production shape: `gateway.battle_begin` appends `battle_begin` BEFORE
    # the session can ever reach `_finish` (gateway.py:560-578). Mirror it
    # so `_check_collusion`'s win-transfer scan + any future
    # owner/tenant-history-dependent branch sees the real shape.
    gateway.events.append(
        "battle_begin",
        {
            "tenant_id": claims.token_id,
            "battle_id": battle_id,
            "lane": "rated",
            "visitor": claims.agent_name,
            "opponent": opponent,
        },
    )

    session = BattleSession(
        battle_id=battle_id,
        # Real `claims.token_id` (not a surrogate string) — matches what
        # production stores at gateway.py:506-508 so `replays[battle_id]
        # ["tenant"]` tracks the same identifier any future paid-owner
        # branch would key against.
        claims_token_id=claims.token_id,
        visitor_name=claims.agent_name,
        lane="rated",
        opponent=opponent,
        seed=[0, 0, 0, 0],
        sidecar=None,
        opponent_policy=None,
    )
    end_payload = {
        "winner": winner,
        # turns >= 3 keeps `_check_collusion`'s early-forfeit branch quiet,
        # so the battle is NOT quarantined and the rating event lands in
        # `recompute_ladder()`'s output.
        "turns": 5,
        # Non-empty inputLog gates the rated-emission block at
        # `_finish` ("if session.lane == 'rated' and len(input_log) > 0").
        "inputLog": [
            "|start",
            "|teampreview",
            "|turn|1",
            "|turn|2",
            "|turn|3",
        ],
        "keyLines": [],
    }
    await gateway._finish(session, end_payload)


def _seed_gateway_with_rated_battles_via_finish(
    gateway: ArenaGateway,
    *,
    visitor: str,
    opponent: str,
    visitor_owner: str,
    n_battles: int,
    winner_pattern: list[str],
) -> None:
    """Run N rated battles end-to-end via the production `_finish` path.

    `visitor_owner` is the membership-context the test wants to inject; it
    flows in via `ConsentClaims.owner` (the field `verify_membership`
    actually keys on per consent.py:179-180), NOT as a string surrogate
    inside `claims_token_id`. A paid-only mutation in `_finish` reading
    `self.authority.is_paid_owner(claims.owner)` (or the moral equivalent)
    would surface as a free vs paid ladder divergence because the real
    owner field, not a synthetic prefix, is what arrives at the gate."""
    import asyncio

    claims = _build_real_claims(
        owner=visitor_owner,
        agent_name=visitor,
        # Deterministic but distinct per-owner token_id so the two gateways'
        # event logs cannot collide on tenant_id; 12-char digits keeps the
        # ConsentClaims `token_id` `min_length=8` rule happy.
        token_id=f"q5tok{abs(hash(visitor_owner)) % (10**12):012d}",
    )

    async def _run() -> None:
        for i in range(n_battles):
            pattern_winner = winner_pattern[i % len(winner_pattern)]
            if pattern_winner == "p1":
                w = visitor
            elif pattern_winner == "p2":
                w = opponent
            else:
                w = ""
            await _run_rated_battle_via_finish(
                gateway,
                claims=claims,
                opponent=opponent,
                winner=w,
                battle_id=f"rated-{i:04d}",
            )

    asyncio.run(_run())


def _assert_no_membership_shaped_keys(node, *, path: str = "$") -> None:
    """Recursively scan a JSON-shaped payload for keys / dict-values whose
    NAMES carry membership-shaped tokens (`membership`, `paid`, `member`,
    `premium`, `tier`, `subscription`). Earlier this scan only inspected
    the OUTER `entrants` key — a public payload like
    `{"entrants": {"probe-bot": {"paid": false}}}` would have slipped
    through. Recursion is required now that the test seeds non-empty
    entrant rows, since membership-shaped leakage is most likely to land
    INSIDE the per-entrant row, not at the top of the view."""
    forbidden_tokens = ("membership", "paid", "member", "premium", "tier", "subscription")
    if isinstance(node, dict):
        for k, v in node.items():
            key_lower = str(k).lower()
            for tok in forbidden_tokens:
                assert tok not in key_lower, (
                    f"ladder leaks membership-shaped key {k!r} at {path}.{k}"
                )
            _assert_no_membership_shaped_keys(v, path=f"{path}.{k}")
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            _assert_no_membership_shaped_keys(item, path=f"{path}[{idx}]")


def test_rating_ceiling_independent_of_membership_status(tmp_path):
    """Property: two owners, one a paying member, one not, identical battle
    sequence → identical Glicko-2 ratings. Encodes ADR-0011 §3c.

    Low-level invariant: `recompute_ladder` is a pure function of the event
    log. The complementary gateway-driven test below
    (`test_gateway_emission_path_does_not_couple_ladder_to_membership`)
    exercises the production emission path through `gateway.events.append`
    so a future paid-path emission change is also caught."""
    # 1. Build the membership table: free-owner has nothing; paid-owner has a
    #    far-future grant. (The test does NOT exercise the route — it directly
    #    instantiates the rating pipeline to prove rating is decoupled from
    #    membership state.)
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    free_authority = ConsentAuthority(signing_key_hex=signing, now=lambda: _NOW)
    paid_authority = ConsentAuthority(
        signing_key_hex=signing,
        now=lambda: _NOW,
        memberships={"paid-owner@example.com": _NOW + 365 * 86_400},
    )
    # Sanity: the membership table actually differs
    assert "paid-owner@example.com" in paid_authority.memberships
    assert "free-owner@example.com" not in free_authority.memberships

    # 2. Same opponent sequence for both — identical skill model captured as
    #    identical winner pattern. (Realistic Glicko-2 input.)
    pattern = ["p1", "p2", "p1", "p1", "p2", "p1", "p2", "p1"]

    # 3. Build TWO event logs, structurally identical except for the player names.
    #    Both have same number of battles, same winner pattern, same opponent.
    free_log = _make_event_log_with_battles(
        tmp_path / "free", p1="free-bot", p2="opponent-bot", n_battles=16, winner_pattern=pattern
    )
    paid_log = _make_event_log_with_battles(
        tmp_path / "paid", p1="paid-bot", p2="opponent-bot", n_battles=16, winner_pattern=pattern
    )

    # 4. Recompute the ladder for both. recompute_ladder MUST NOT consult the
    #    authority's memberships dict — it takes only the log path.
    free_ladder = recompute_ladder(free_log)
    paid_ladder = recompute_ladder(paid_log)

    # 5. Compare ratings under the renaming free-bot ↔ paid-bot. Glicko-2
    #    ratings are deterministic from the event sequence — the only thing
    #    different between the two simulations is the player name string,
    #    not the membership status of the owner.
    free_entrants = free_ladder.entrants
    paid_entrants = paid_ladder.entrants
    free_player = free_entrants["free-bot"]
    paid_player = paid_entrants["paid-bot"]
    free_opp = free_entrants["opponent-bot"]
    paid_opp = paid_entrants["opponent-bot"]

    # The property: any rating dimension (mu, sigma/rd, vol) must match.
    assert free_player == paid_player, (
        f"free-bot rating {free_player} differs from paid-bot rating {paid_player}"
        " — membership leaked into the rating pipeline (pay-to-rank-by-proxy)"
    )
    assert free_opp == paid_opp, (
        "opponent rating differs between the two simulations — should be impossible"
        " if rating is purely a function of (RatingEvent stream)"
    )


def test_gateway_emission_path_does_not_couple_ladder_to_membership(tmp_path):
    """End-to-end variant: stand up TWO gateways with DIFFERENT memberships,
    drive identical rated battles through each gateway's REAL production
    end-of-battle path (`_finish`), and assert `ladder_public()` returns
    identical non-empty entrant rows — with ORDER preserved AND with no
    membership-shaped key leaking at ANY depth of the public payload.

    Three sensitivities the earlier version did not have:

    1. **Production emission path.** The earlier helper fabricated the
       `period` payload and wrote it via `EventLog.append`; that is just
       persistence — a paid-only mutation inside `_finish` itself (e.g.
       reading `self.authority.is_paid_owner(...)` to add a `bonus` field
       on the RatingEvent) would have been silently bypassed. Driving
       `gateway._finish(session, end)` runs every production line between
       `sanitize_name` and the period-event append.

    2. **Ladder ORDER, not just dict equality.** Python `dict == dict`
       ignores insertion order, but `ladder_public()` deliberately builds
       `entrants` sorted by descending rating. A pay-to-rank regression
       that re-sorted paid entrants ahead WITHOUT touching per-row rating
       values would change the served ranking but leave the dict-equality
       check green. Comparing `list(items())` in BOTH the outer view AND
       the inner `entrants` dict catches the ordering-only attack.

    3. **Recursive key-name scan.** The earlier loop only inspected the
       top-level `entrants` key. A future row like
       `{"entrants": {"probe-bot": {"paid": false}}}` would have slipped
       through. `_assert_no_membership_shaped_keys` recurses into nested
       dicts and lists.

    This is the load-bearing behavioural property for ADR-0011 §3c."""
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()

    free_gw = ArenaGateway(
        authority=ConsentAuthority(signing_key_hex=signing, now=lambda: _NOW),
        events_path=tmp_path / "free-events.jsonl",
        artifacts_dir=tmp_path / "free-arena",
        notify_owner=lambda o, c: None,
        admin_authority=None,
        now=lambda: _NOW,
    )
    paid_authority = ConsentAuthority(
        signing_key_hex=signing,
        now=lambda: _NOW,
        memberships={"paid-owner@example.com": _NOW + 1_000_000},
    )
    paid_gw = ArenaGateway(
        authority=paid_authority,
        events_path=tmp_path / "paid-events.jsonl",
        artifacts_dir=tmp_path / "paid-arena",
        notify_owner=lambda o, c: None,
        admin_authority=AdminAuthority(token_hash_hex=_ADMIN_HASH),
        now=lambda: _NOW,
    )

    # Sanity: the two authorities differ on membership state before the seed.
    assert "paid-owner@example.com" in paid_gw.authority.memberships
    assert "paid-owner@example.com" not in free_gw.authority.memberships
    assert "free-owner@example.com" not in free_gw.authority.memberships

    # Drive IDENTICAL rated-battle sequences through each gateway's REAL
    # production `_finish` path. Owner context differs by gateway — paid
    # gateway carries the paid owner; free gateway carries the free owner.
    # A paid-only mutation injected inside `_finish` that consulted the
    # owner's membership status would diverge the resulting ladder.
    #
    # The pattern flips the win-share so the VISITOR loses 4 of 8 cycles
    # — opponent-bot ends with ~12 wins to probe-bot's ~4 over 16 battles.
    # Crucial for the ordered-comparison guard below: if probe-bot won the
    # majority, it would already sort ahead of opponent-bot by rating and
    # a paid-first-reorder regression that promotes paid entrants to the
    # top would leave the order unchanged in BOTH views (the assertion
    # would be vacuously true). With probe-bot below opponent-bot in the
    # free view, any paid-first promotion in the paid view would diverge
    # the `list(items())` comparison. Both sides still win some battles,
    # so `_check_collusion`'s win-transfer rail stays quiet.
    pattern = ["p2", "p1", "p2", "p2", "p2", "p1", "p2", "p2"]
    _seed_gateway_with_rated_battles_via_finish(
        free_gw,
        visitor="probe-bot",
        opponent="opponent-bot",
        visitor_owner="free-owner@example.com",
        n_battles=16,
        winner_pattern=pattern,
    )
    _seed_gateway_with_rated_battles_via_finish(
        paid_gw,
        visitor="probe-bot",
        opponent="opponent-bot",
        visitor_owner="paid-owner@example.com",
        n_battles=16,
        winner_pattern=pattern,
    )

    free_view = free_gw.ladder_public()
    paid_view = paid_gw.ladder_public()

    # The non-empty ladder must be byte-identical between the free and paid
    # gateway — same registered entrants, same rated battles, same Glicko-2
    # output, AND same ladder order. If `ladder_public()` ever boosted,
    # filtered, re-sorted, or annotated paid entrants conditionally on
    # `authority.memberships`, one of the assertions below fires.
    assert free_view["entrants"], "free gateway ladder should have entrants after seeding"
    assert paid_view["entrants"], "paid gateway ladder should have entrants after seeding"

    # Order-sensitive comparison — guards against pay-to-rank reordering
    # that leaves per-row rating values untouched. `ladder_public()`
    # deliberately constructs `entrants` in sorted (descending rating) order;
    # we compare the ordered key/value sequence in BOTH the outer view AND
    # the inner `entrants` dict.
    assert list(free_view.items()) == list(paid_view.items()), (
        f"ladder_public outer-view order diverges — "
        f"free={list(free_view.items())!r} paid={list(paid_view.items())!r}"
    )
    assert list(free_view["entrants"].items()) == list(paid_view["entrants"].items()), (
        f"ladder_public entrant ordering diverges between free and paid gateways — "
        f"free={list(free_view['entrants'].items())!r} "
        f"paid={list(paid_view['entrants'].items())!r} — pay-to-rank-by-proxy"
    )

    # Recursive belt-and-suspenders: even if the ordered-equality check were
    # ever relaxed, NO key at ANY depth of the public payload may carry
    # membership-shaped naming (`paid`, `member`, `tier`, etc.).
    _assert_no_membership_shaped_keys(free_view, path="free_view")
    _assert_no_membership_shaped_keys(paid_view, path="paid_view")


# ---- meta: doctrine vs code parity check ----


def test_adr_0011_section_3c_exists_and_references_this_file():
    """Cheap parity check: ADR-0011 §3c must reference this test file by name.
    If someone deletes the §3c section, this test fails — keeping doctrine and
    code in lockstep (anti-doctrine-drift)."""
    adr_path = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "adr"
        / "0011-gtm-a-membership-primitive-and-paid-feature-positioning.md"
    )
    text = adr_path.read_text()
    assert "§3c" in text or "3c " in text, "ADR-0011 §3c heading was removed"
    assert "test_q5_anti_pay_to_rank_property" in text, (
        "ADR-0011 must reference this test file in §3c / frontmatter enforced_by"
    )
