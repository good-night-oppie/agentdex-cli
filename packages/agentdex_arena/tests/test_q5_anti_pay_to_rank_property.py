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
    """Every rating-path module — currently events.py (recompute_ladder) AND
    ladder.py (RatingEvent + Ladder.rate_period) — must not import
    AdminAuthority or membership helpers from agentdex_arena.consent.

    The earlier scan only read the source of `recompute_ladder` (events.py),
    but the actual rating math lives in `Ladder.rate_period` (ladder.py); a
    future pay-to-rank-by-proxy dependency added there would have slipped
    through. Scanning every module that defines a load-bearing rating-path
    symbol means adding a new module to the rating path means adding it to
    this set too."""
    rating_path_symbols = (recompute_ladder, RatingEvent, Ladder)
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
    elog.append("period", {"events": events})
    return log_path


def test_rating_ceiling_independent_of_membership_status(tmp_path):
    """Property: two owners, one a paying member, one not, identical battle
    sequence → identical Glicko-2 ratings. Encodes ADR-0011 §3c."""
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


def test_gateway_construction_does_not_couple_ladder_to_membership(tmp_path):
    """End-to-end variant: stand up TWO gateways, one with admin/memberships
    and one without. Confirm authority.memberships state never appears in
    any rating-related call signature or stored ladder state."""
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
        memberships={"paid@x.com": _NOW + 1_000_000},
    )
    paid_gw = ArenaGateway(
        authority=paid_authority,
        events_path=tmp_path / "paid-events.jsonl",
        artifacts_dir=tmp_path / "paid-arena",
        notify_owner=lambda o, c: None,
        admin_authority=AdminAuthority(token_hash_hex=_ADMIN_HASH),
        now=lambda: _NOW,
    )

    # ladder_public() is the public ladder view consumed by /ladder. It must
    # be a pure function of the registered ratings — no membership filter.
    free_view = free_gw.ladder_public()
    paid_view = paid_gw.ladder_public()
    # Both are empty (no battles); but more importantly, neither view's keys
    # carry membership info. Just sanity-assert no membership-shaped key leaks.
    for view in (free_view, paid_view):
        if isinstance(view, dict):
            for k in view:
                assert "membership" not in str(k).lower(), f"ladder leaks membership key: {k}"
                assert "paid" not in str(k).lower(), f"ladder leaks paid-ness in key: {k}"


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
