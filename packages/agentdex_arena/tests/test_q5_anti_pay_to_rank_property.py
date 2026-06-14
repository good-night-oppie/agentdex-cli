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

from agentdex_arena.admin_auth import AdminAuthority
from agentdex_arena.consent import ConsentAuthority
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


# Aliases used by every structural guard below. The earlier sets covered the
# explicit (membership / is_member / tier / paid) shape, but a future refactor
# could attach owner / tenant_id / member / premium / plan to the rating path
# and satisfy those denylists while still letting the rating pipeline join
# against membership state. Centralising the alias set means a single edit
# tightens every guard (RatingEvent fields, recompute_ladder signature, Ladder
# state) consistently.
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


def test_rating_event_has_no_membership_field():
    """RatingEvent schema must not reference membership / paid / tier / etc.

    If a future refactor adds such a field, this test catches it before any
    paid-feature route can read it — encoding the anti-pay-to-rank-by-proxy
    invariant at the type-system level."""
    fields = set(RatingEvent.model_fields.keys())
    leak = fields & _FORBIDDEN_RATING_FIELDS
    assert not leak, f"RatingEvent leaks membership-shaped field(s): {leak}"


def test_recompute_ladder_signature_takes_no_membership_input():
    """recompute_ladder must depend only on (log_path, frozen, expected_digest).

    Any future signature addition of membership/paid/tier means the rating
    pipeline now branches on payment status — pay-to-rank-by-proxy."""
    sig = inspect.signature(recompute_ladder)
    leak = set(sig.parameters.keys()) & _FORBIDDEN_RATING_FIELDS
    assert not leak, f"recompute_ladder signature leaks membership params: {leak}"


def test_ladder_class_has_no_membership_state():
    """Ladder._ratings / _frozen / badges — no membership store. If you
    add one (paid users get rating boost / decay protection / etc.), this
    test fires."""
    public_attrs = {a for a in dir(Ladder()) if not a.startswith("_")}
    private_attrs = {a for a in dir(Ladder()) if a.startswith("_") and not a.startswith("__")}
    # Match the alias set against both public and leading-underscore private
    # names so a hypothetical `_owner_email` fires identically to `owner_email`.
    forbidden = _FORBIDDEN_RATING_FIELDS | {f"_{name}" for name in _FORBIDDEN_RATING_FIELDS}
    leak = (public_attrs | private_attrs) & forbidden
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


async def _run_rated_battle_via_finish(
    gateway: ArenaGateway,
    *,
    visitor: str,
    opponent: str,
    visitor_owner: str,
    winner: str,
    battle_id: str,
) -> None:
    """Drive one rated battle through the REAL production end-of-battle code
    path — `gateway._finish(session, end)` — so the test is sensitive to a
    paid-only mutation injected anywhere in the actual emission block, not
    just on the `EventLog.append` call.

    The earlier helper fabricated the `period` payload and wrote it directly
    to `EventLog`; since `EventLog.append` is just persistence, a paid-only
    mutation in `_finish` itself (e.g. `if self.authority.is_paid(owner):
    rating_event["bonus"] = +200` injected around the RatingEvent
    construction at `gateway.py:849-870`) would have been silently bypassed.
    Driving `_finish` directly closes that gap: every production line
    between sanitize_name and `events.append("period", ...)` runs."""
    from agentdex_arena.gateway import BattleSession

    session = BattleSession(
        battle_id=battle_id,
        # claims_token_id is opaque to _finish (used only for replay tenancy
        # tagging); we encode the owner-membership context in visitor_owner
        # so a future engineer wiring `self.authority.is_paid(owner)` into
        # the emission path has a real way to read it.
        claims_token_id=f"tok-{visitor_owner}",
        visitor_name=visitor,
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

    `visitor_owner` is the membership-context the test wants to inject —
    a paid-only mutation in `_finish` reading
    `self.authority.is_paid_owner(visitor_owner)` (or the moral equivalent)
    would surface as a free vs paid ladder divergence."""
    import asyncio

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
                visitor=visitor,
                opponent=opponent,
                visitor_owner=visitor_owner,
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
    pattern = ["p1", "p2", "p1", "p1", "p2", "p1", "p2", "p1"]
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
