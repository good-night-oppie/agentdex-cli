"""Arena gateway — the ONLY visitor surface (A1/A3/A6 anchors in code).

Lanes (A3): the day-one fun loop lives in the UNRATED sandbox (gym leaders,
disclosed seeds, same-seed rematches); published Glicko moves only via the
RATED lane — server-matchmade vs held-out anchors, server-secret seeds
revealed post-result. Direct challenges stay sandbox, permanently.

Consent (A1): every acting endpoint takes an owner-minted token; battles
additionally demand per-battle proof-of-possession. Enrollment REQUIRES an
out-of-band human confirmation (the confirm code goes to the OWNER via the
injected notifier, never into the agent-visible response).

Injection (A6): all visitor strings pass sanitize_name at the boundary;
errors are opaque ids (details server-side); battle renders re-use the
phase-6 bounded renderer.

The gateway owns the clock: a battle idle past `turn_budget_s` forfeits to
the opponent on next touch (SLEEPING-tolerant — no background task needed).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import math
import os
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote as _url_quote

from adx_bridges.showdown_battle_bridge import render_state
from adx_showdown.bots import (
    balance_bot,
    heuristic_bot,
    hyper_offense_bot,
    max_damage_bot,
    random_bot,
    stall_bot,
    trick_room_bot,
)
from adx_showdown.pool import SidecarPool
from adx_showdown.protocol import (
    ParsedRequest,
    active_species,
    legal_choices,
    parse_request,
    sanitize_name,
)
from adx_showdown.sidecar import Sidecar, SidecarError
from adx_showdown.sim import BattleContext, Policy, call_policy
from adx_showdown.teams import pack_team, starter_pack, validate_team
from agentdex_engine.modules.arena import (
    EventLog,
    Ladder,
    Rating,
    RatingEvent,
    extract_signatures,
    recompute_ladder,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentdex_arena.account import AccountStore
from agentdex_arena.admin_auth import AdminAuthError, AdminAuthority
from agentdex_arena.badge_auth import BadgeAuthError, BadgeAuthority
from agentdex_arena.consent import (
    ConsentAuthority,
    ConsentClaims,
    ConsentError,
    _normalize_owner,
)
from agentdex_arena.device_flow import DeviceFlowError, GitHubDeviceFlow
from agentdex_arena.invite import (
    InviteError,
    InviteStore,
    hash_invite_code,
    new_invite_code,
)
from agentdex_arena.session import SessionAuthority, SessionClaims, SessionError

log = logging.getLogger(__name__)

Lane = Literal["sandbox", "rated"]
GYM_LEADERS = (
    "anchor-random",
    "anchor-max_damage",
    "anchor-heuristic",
    "gym-balance",
    "gym-hyper-offense",
    "gym-stall",
    "gym-trick-room",
)
GYM_BADGES = {
    "anchor-random": "Boulder Badge",
    "anchor-max_damage": "Cascade Badge",
    "anchor-heuristic": "Thunder Badge",
    "gym-balance": "Balance Badge",
    "gym-hyper-offense": "Hyper Offense Badge",
    "gym-stall": "Stall Badge",
    "gym-trick-room": "Trick Room Badge",
}
RATED_POOL = ("anchor-max_damage", "anchor-heuristic")  # held-out matchmaking pool

# 11c: 30-day badge_token TTL per design D3. Matches the monthly membership
# cycle: a revoked member loses MINT immediately, but already-minted badges
# render until expiry — same semantic as a paid cert.
BADGE_TOKEN_TTL_SEC = 30 * 86_400
# 11c.3 D5: 5-minute CDN/browser cache for /badge/<>.svg. Battles are sparse;
# <5min staleness is acceptable, blocks sig-spam on README hits.
BADGE_SVG_CACHE_SEC = 300
BADGE_ISSUER = "agentdex.ai-builders.space"
BADGE_LADDER_URL = "https://agentdex.ai-builders.space/ladder"


def _badge_referer_host(referer: str | None) -> str:
    """Extract host (no port, no path, no query) from a Referer header for
    the 11c.3 Q2 funnel. Returns '' when the header is missing or malformed
    so the log line stays structured; aggregation lives in V2."""
    if not referer:
        return ""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(referer)
    except ValueError:
        return ""
    return (parsed.hostname or "").lower()


def _badge_rating_color(rating: float) -> str:
    """shields.io / Codeforces gradient per spec D4:
    < 1500 → gray, 1500-1750 → light green, 1750+ → dark green."""
    if rating < 1500:
        return "#9f9f9f"
    if rating < 1750:
        return "#6cb868"
    return "#4ba14a"


def _render_badge_svg(*, agent_name: str, rating: float, rd: float, verify_url: str) -> str:
    """shields.io-style 2-cell badge. Inline SVG so deployments don't need a
    template file; values are XML-escaped to block injection through the
    agent_name surface (the gateway already sanitize_name()s at enrollment,
    but defense-in-depth at the render boundary is cheap).

    Two escaping shapes used here, deliberately distinct (PR #132 review
    #3411007726):
      * Element-text escape (`_text_esc`) escapes `&<>` but NOT `"`. The
        title element body is plain XML text, so leaving `"` literal is
        safe AND keeps the screen-reader prose readable.
      * Attribute-value escape (`_attr_esc`) escapes `&<>"` so the
        `aria-label="..."` and any other double-quoted attribute survive
        a value containing a `"` without letting the attacker close the
        attribute and inject extra attributes.

    The previous render only escaped element-text shape on the value used
    inside `aria-label="..."` — a `verify_url` carrying a `"` produced a
    malformed SVG and let the caller inject attributes. The test
    `test_badge_svg_xml_escapes_agent_name` even fed an attacker-shaped
    URL but only asserted the element-text side; the attribute path was
    silently broken."""
    from xml.sax.saxutils import escape as _xml_escape

    def _text_esc(s: str) -> str:
        # Default xml.sax.saxutils.escape covers `&`, `<`, `>`.
        return _xml_escape(s)

    def _attr_esc(s: str) -> str:
        # Same as _text_esc plus `"` → `&quot;` so the value can sit inside
        # a double-quoted attribute. Single-quoted-attr support isn't
        # required (we never emit `'`-quoted attrs here).
        return _xml_escape(s, {'"': "&quot;"})

    safe_name_text = _text_esc(agent_name)
    safe_verify_url_text = _text_esc(verify_url)
    color = _badge_rating_color(rating)
    value_text = f"{safe_name_text} · {rating:.0f} ±{rd:.0f} ✓"
    label_text = "agentdex"
    label_w = 12 + int(6.2 * len(label_text)) + 12
    value_w = 12 + int(6.2 * len(value_text)) + 12
    total_w = label_w + value_w
    title_text = f"agentdex verified badge — see {safe_verify_url_text}"
    # aria-label is an XML attribute, so it gets the attribute escape on
    # the SAME raw input — NOT the element-text-escaped string (double-
    # escaping `&` would surface as `&amp;amp;` in screen readers).
    aria_label = _attr_esc(f"agentdex verified badge — see {verify_url}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20" '
        f'role="img" aria-label="{aria_label}">'
        f"<title>{title_text}</title>"
        f'<linearGradient id="s" x2="0" y2="100%">'
        f'<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        f'<stop offset="1" stop-opacity=".1"/>'
        f"</linearGradient>"
        f'<rect width="{total_w}" height="20" fill="#555" rx="3"/>'
        f'<rect x="{label_w}" width="{value_w}" height="20" fill="{color}" rx="3"/>'
        f'<rect x="{label_w - 3}" width="6" height="20" fill="{color}"/>'
        f'<rect width="{total_w}" height="20" fill="url(#s)" rx="3"/>'
        f'<g fill="#fff" text-anchor="middle" '
        f'font-family="DejaVu Sans,Verdana,sans-serif" font-size="11">'
        f'<text x="{label_w / 2:.0f}" y="14">{label_text}</text>'
        f'<text x="{label_w + value_w / 2:.0f}" y="14">{value_text}</text>'
        f"</g></svg>"
    )


# Break-the-mirror (#3, sandbox lane): each gym leader fields a FIXED, DISCLOSED
# signature team drawn from the starter pack by sorted index — distinct from the
# visitor's default (pack index 0), so even two defaults never mirror. The packed
# team is returned in the begin response: sandbox is the open-information matchup
# puzzle; scouting it is the point.
#
# Break-the-mirror (#8, rated lane): i.i.d. anchor-team matchmaking. The opponent
# is drawn from RATED_POOL via nonce hash (unchanged). The opponent TEAM is drawn
# i.i.d. from RATED_ANCHOR_TEAMS via an extended nonce hash, so the matchmaker
# samples anchor team independently of the visitor's team. Seed and opponent team
# disclosed post-result via the existing seed-disclosure rail.
ARCHETYPE_GYM_TEAMS = {
    "gym-balance": "01-balance-tusk-gambit",
    "gym-hyper-offense": "02-hyper-offense",
    "gym-stall": "03-stall",
    # starter_pack() ships trick-room as 09-trick-room (04 is 04-sand-balance);
    # the old "04-trick-room" KeyError'd starter_pack() -> 500 on this advertised
    # gym, dead-ending the agent. Locked by test_every_gym_resolves_to_a_real_team
    # (codex dogfood P1).
    "gym-trick-room": "09-trick-room",
}
GYM_TEAM_INDEX = {"anchor-random": 1, "anchor-max_damage": 2, "anchor-heuristic": 3}
RATED_ANCHOR_TEAMS = (
    "10-pivot-spam",
    "11-dragon-spam",
    "12-fat-fwg",
)  # held-out i.i.d. pool for rated mirror-break


def sanitize_packed_team(packed: str) -> str:
    if not packed:
        return packed
    mons = []
    for mon in packed.split("]"):
        if not mon:
            continue
        parts = mon.split("|")
        if parts:
            parts[0] = sanitize_name(parts[0])
        mons.append("|".join(parts))
    return "]".join(mons)


def _gym_team_name(opponent: str) -> str:
    if opponent in ARCHETYPE_GYM_TEAMS:
        return ARCHETYPE_GYM_TEAMS[opponent]
    names = sorted(starter_pack())
    return names[GYM_TEAM_INDEX.get(opponent, 1) % len(names)]


def _opaque_error(status: int, exc: Exception | str) -> HTTPException:
    err_id = uuid.uuid4().hex[:12]
    log.warning("arena error (ref=%s): %s", err_id, exc)
    return HTTPException(status_code=status, detail=f"arena error (ref: {err_id})")


def _anchor_policy(name: str, sidecar: Sidecar, seed: int):
    kind = name.removeprefix("anchor-")
    if kind == "random":
        return random_bot(seed)
    if kind == "max_damage":
        return max_damage_bot(sidecar, fallback_seed=seed)
    return heuristic_bot(sidecar, fallback_seed=seed)


def _opponent_policy(name: str, sidecar: Sidecar, seed: int):
    if name == "gym-balance":
        return balance_bot(sidecar, fallback_seed=seed)
    if name == "gym-hyper-offense":
        return hyper_offense_bot(sidecar, fallback_seed=seed)
    if name == "gym-stall":
        return stall_bot(sidecar, fallback_seed=seed)
    if name == "gym-trick-room":
        return trick_room_bot(sidecar, fallback_seed=seed)
    return _anchor_policy(name, sidecar, seed)


# Default-sandbox autopilot-punisher (codex dogfood P2). The default sandbox
# opponent (no gym_leader) is anchor-random, which loses to "always choose 1" —
# a reward hack on the sandbox win-signal (win without playing). Rather than raise
# the floor for everyone (which breaks the gentle on-ramp doctrine), detect the
# low-entropy autopilot SIGNATURE and escalate only against it. Sandbox-only:
# never wired into the rated lane, so it cannot touch the Glicko / anti-pay-to-rank
# rails.
_AUTOPILOT_WINDOW = 3


def _is_autopilot(session: BattleSession) -> bool:
    """True once the visitor shows the autopilot signature: the last
    _AUTOPILOT_WINDOW choices identical. LATCHES — varying play after the latch
    does not de-escalate, closing the vary-once-to-reset game."""
    if session.autopilot_escalated:
        return True
    recent = session.visitor_choices[-_AUTOPILOT_WINDOW:]
    if len(recent) >= _AUTOPILOT_WINDOW and len(set(recent)) == 1:
        session.autopilot_escalated = True
    return session.autopilot_escalated


def autopilot_punisher(
    sidecar: Sidecar,
    seed: int,
    *,
    on_autopilot: Callable[[], bool],
    gentle: Policy | None = None,
    strong: Policy | None = None,
) -> Policy:
    """Default sandbox opponent: gentle random play until ``on_autopilot()`` flips
    True, then max-damage for the rest of the battle. A real player who varies
    their moves keeps the gentle bot (on-ramp preserved); only low-entropy
    autopilot triggers the escalation. ``gentle``/``strong`` are injectable so the
    routing is testable without a sidecar."""
    gentle_policy = gentle if gentle is not None else random_bot(seed)
    strong_policy = strong if strong is not None else max_damage_bot(sidecar, fallback_seed=seed)

    async def _policy(req: ParsedRequest, ctx: BattleContext) -> str | None:
        return await call_policy(strong_policy if on_autopilot() else gentle_policy, req, ctx)

    return _policy


def _hp_pct(condition: str) -> int | None:
    """'245/371 par' -> 66; '0 fnt' -> 0. Server-rendered condition strings only."""
    if not condition:
        return None
    head = condition.split()[0]
    if head == "0" or condition.endswith("fnt"):
        return 0
    if "/" in head:
        try:
            cur, mx = head.split("/", 1)
            return max(0, min(100, round(100 * int(cur) / int(mx))))
        except (ValueError, ZeroDivisionError):
            return None
    return None


RECENT_TURNS_MAX = 8
# Public quarantine reason surfaced on the wire. The specific forensic signal
# (which heuristic fired + its threshold) stays in the durable "quarantine"
# EventLog row + the server log only — naming it on the receipt would hand a
# colluder the exact evasion recipe (D7 anti-enumeration; mirrors the badge /
# battle_id opaque-error posture).
_QUARANTINE_PUBLIC_REASON = "quarantined by collusion forensics"


def _push_recent(session: BattleSession, line: str) -> None:
    if session.recent and session.recent[-1] == line:
        return
    session.recent.append(line)
    del session.recent[:-RECENT_TURNS_MAX]


def _choice_label(choice: str, pending: Any) -> str:
    """Resolve a PS choice string to a human-readable label.

    'move 1' -> 'Earthquake'; 'switch 3' -> 'switch to Dragonite'.
    Falls back to the raw choice string if the request is unavailable or the
    slot is out of range — this must never raise.
    """
    try:
        if choice.startswith("move ") and pending is not None:
            slot = int(choice.split()[1])
            for moves in (pending.active_moves or [])[:1]:
                for mv in moves:
                    if mv.slot == slot:
                        return mv.id or choice
        if choice.startswith("switch ") and pending is not None:
            slot = int(choice.split()[1])
            for s in pending.bench:
                if s.index == slot:
                    return f"switch → {s.species or slot}"
        if choice == "team preview" or choice.startswith("team "):
            return f"team preview {choice.split()[-1]}"
    except Exception:  # noqa: BLE001 — telemetry path must never crash
        pass
    return choice


@dataclass
class BattleSession:
    battle_id: str
    claims_token_id: str
    visitor_name: str
    lane: Lane
    opponent: str
    seed: list[int]
    sidecar: Sidecar
    opponent_policy: Any
    pending: ParsedRequest | None = None
    turns: int = 0
    started_at: float = field(default_factory=time.time)
    last_touch: float = field(default_factory=time.time)
    ended: dict[str, Any] | None = None
    visitor_side: str = "p1"
    # Live observability (playtest G-01/G-02/G-10): the opponent's request —
    # which the gateway already parses to drive the anchor policy — carries the
    # opponent's exact HP via its bench condition strings. Server-rendered data;
    # no sidecar change, no determinism impact.
    # Seed a "(battle start)" marker so the turn-0 state response carries a
    # non-empty, self-describing recent_turns instead of an ambiguous empty
    # list (ADX-P2-002 legibility; matches the SKILL.md §3a example). Real turn
    # lines (`T#: ...`) append after it via _push_recent; it ages out under
    # RECENT_TURNS_MAX like any other line. Fork-reconstructed sessions start
    # the same way — a fork is itself a fresh battle start.
    recent: list[str] = field(default_factory=lambda: ["(battle start)"])
    foe_species: str | None = None
    foe_hp_pct: int | None = None
    # Fork support (#6): the exact inputs needed to re-create this battle from
    # its seed and branch at a turn. parent=(battle_id, fork_turn) on forks.
    p1_team: str | None = None
    p2_team: str | None = None
    visitor_choices: list[str] = field(default_factory=list)
    # Latched once the default sandbox opponent escalates against autopilot play
    # (see autopilot_punisher / _is_autopilot). Sandbox-only; never set in rated.
    autopilot_escalated: bool = False
    # True when the visitor explicitly named an opponent via req.gym_leader
    # (as opposed to leaving it defaulted to GYM_LEADERS[0] = anchor-random).
    # Persisted to the replay record so battle_fork can restore the same policy:
    # default anchor-random forks install autopilot_punisher (mirror battle_begin);
    # explicit anchor-random forks keep the plain random bot the visitor chose.
    explicit_opponent: bool = False
    parent: tuple[str, int] | None = None
    scratchpad: str = ""
    last_state: dict[str, Any] | None = None
    # In-flight shielded finish (PR #289 review): a strong reference so the event
    # loop's weak task ref cannot GC a backgrounded _finish mid-wait, AND a
    # "finishing" marker so _expire_if_stale won't queue a second forfeit finish
    # while one is outstanding. Set in _advance, cleared by its done-callback.
    finish_task: Any = None
    # Normalized owner — keys the per-owner concurrency cap (ADR-0012 §7). Defaulted
    # so existing constructions (tests, fork) need no change; battle_begin sets it.
    owner: str = ""


class EnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)
    owner: str = Field(min_length=3, max_length=120)
    agent_name: str = Field(min_length=1, max_length=64)
    agent_pubkey_hex: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("owner")
    @classmethod
    def _owner_is_a_contact(cls, v: str) -> str:
        # The owner is the HUMAN contact the out-of-band confirmation code reaches
        # (A1). Reject template placeholders / non-addresses with a self-describing
        # error so the arena never silently enrolls a literal "{OWNER}" and teaches
        # the visiting agent the wrong lesson (playtest G-04).
        if any(c in v for c in "{}<>") or any(c.isspace() for c in v):
            raise ValueError("owner must be a contact address, not a placeholder")
        if "@" not in v or "." not in v.rsplit("@", 1)[-1]:
            raise ValueError("owner must be a reachable contact, e.g. name@example.com")
        return v


class DevicePollRequest(BaseModel):
    """Body of POST /auth/device/poll (ADR-0013 D2). The CLI echoes the
    device_code it received from /auth/device/start on every poll; the arena
    stays stateless between the two (GitHub tracks the grant)."""

    model_config = ConfigDict(extra="forbid", strict=False)
    device_code: str = Field(min_length=1, max_length=512)


class EnrollAccountRequest(BaseModel):
    """Body of POST /enroll/account (ADR-0013 D3). No `owner` field — the owner
    is the session token's verified email, never client-supplied (that is the
    whole point of account-authed enroll). The pubkey pattern is validated here
    so a bad key 422s before any name is reserved."""

    model_config = ConfigDict(extra="forbid", strict=False)
    agent_name: str = Field(min_length=1, max_length=64)
    agent_pubkey_hex: str = Field(pattern=r"^[0-9a-f]{64}$")


class BeginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)
    token: str
    battle_nonce: str
    pop_signature_hex: str
    lane: Lane = "sandbox"
    team: str | None = None  # packed; validated server-side; None = starter draft 1
    gym_leader: str | None = None  # opt-in gym leader challenge in sandbox


class ChooseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)
    token: str
    choice_index: int = Field(ge=1, le=64)


# Max future horizon for an admin-granted membership: 400 days. Past 400 days
# the grant looks more like a typo than a deliberate annual subscription, and
# rejecting it at the boundary prevents accidental "lifetime free" tickets
# from being created via a bad valid_until_epoch.
MAX_GRANT_HORIZON_SEC = 400 * 86_400

# Shown when a battle the caller begun/forked in a PRIOR process is touched after a
# gateway restart (in-memory sessions are wiped). Owner-scoped — others still get the
# opaque 403. Single-sourced so the HTTP 409 + the MCP error read identically (#246).
INTERRUPTED_RESTART_MSG = "battle interrupted by a gateway restart — start a new battle"


class RedeemInviteRequest(BaseModel):
    """POST /enroll/redeem-invite body (GA-CORE-1). The owner is the session
    token's verified email, never client-supplied — only the code is."""

    model_config = ConfigDict(extra="forbid", strict=False)
    invite_code: str = Field(min_length=1, max_length=128)


class MintInvitesRequest(BaseModel):
    """POST /admin/mint-invites body (GA-CORE-1). Operator-only; auth runs BEFORE
    body parse via Depends, same anti-enumeration posture as grant-membership."""

    model_config = ConfigDict(extra="forbid", strict=False)
    count: int = Field(ge=1, le=1000)


class GrantMembershipRequest(BaseModel):
    """POST /admin/grant-membership body (ADR-0011 11b.3). Auth runs BEFORE
    body parse via FastAPI Depends, so a malformed body cannot leak schema
    via 422 to an unauthenticated probe."""

    model_config = ConfigDict(extra="forbid", strict=False)
    owner: str = Field(min_length=1, max_length=254)
    valid_until_epoch: float

    @field_validator("owner")
    @classmethod
    def _owner_normalizes(cls, v: str) -> str:
        # Reject upstream what _normalize_owner would reject; keep the original
        # casing in the field — we re-normalize at storage time so the EventLog
        # records what the admin actually sent.
        _normalize_owner(v)
        return v

    @field_validator("valid_until_epoch")
    @classmethod
    def _valid_until_finite_and_bounded(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("valid_until_epoch must be finite (no NaN/Inf)")
        if v < 0:
            raise ValueError("valid_until_epoch must be >= 0")
        # NOTE: upper-bound check (now + MAX_GRANT_HORIZON_SEC) needs the
        # gateway's clock and runs inside the route handler, not here, because
        # field_validator does not have access to runtime state.
        return v


class ArenaGateway:
    def __init__(
        self,
        *,
        authority: ConsentAuthority,
        events_path: str | Path,
        artifacts_dir: str | Path,
        notify_owner: Callable[[str, str], None],
        turn_budget_s: float = 120.0,
        rated_seed_secret: str = "",
        now: Callable[[], float] = time.time,
        event_sync: Callable[[dict], None] | None = None,
        admin_authority: AdminAuthority | None = None,
        badge_authority: BadgeAuthority | None = None,
        session_authority: SessionAuthority | None = None,
        device_flow: GitHubDeviceFlow | None = None,
        public_base_url: str = "",
    ) -> None:
        self.authority = authority
        # Admin bearer for operator-only routes (ADR-0011 11b.3). None means
        # admin endpoints respond 403 'admin not configured' at request time —
        # the production __main__ constructs AdminAuthority eagerly so the
        # container fail-closed-boots if ARENA_ADMIN_TOKEN_HASH is missing.
        self.admin = admin_authority
        # Badge signing authority for ADR-0011 11c (first paid feature). None
        # means /badge/mint responds 503 'badge mint not configured' (the
        # production __main__ tolerates a missing ARENA_BADGE_SIGNING_KEY_HEX
        # and lets the other routes come up — PR #135 review #3410920013).
        self.badge_auth = badge_authority
        # ADR-0013 D2/D3 onboarding. session_auth mints the human login session;
        # device_flow brokers GitHub device-flow. Both None means the
        # /auth/device/* + account routes respond 503 'session auth not
        # configured' (same optional-at-boot posture as badge_auth) — the
        # production __main__ tolerates missing ARENA_SESSION_SIGNING_KEY_HEX /
        # GITHUB_OAUTH_CLIENT_ID and brings every existing route up regardless.
        self.session_auth = session_authority
        self.device_flow = device_flow
        # Absolute base URL used to construct README-embeddable badge URLs
        # in the /badge/mint response (PR #130 review #3410920009). Empty
        # string keeps the legacy relative-URL shape for test fixtures; the
        # production __main__ reads ARENA_PUBLIC_BASE_URL and falls back to
        # f"https://{BADGE_ISSUER}" so an unconfigured prod deploy still
        # produces working README embeds. Caller-supplied value MUST omit
        # trailing slash; the route builder will join with f"/badge/...".
        self.public_base_url = public_base_url.rstrip("/")
        self.events = EventLog(events_path, sync=event_sync)
        self._registered: set[str] = set()
        # ADR-0013 D3/D6: the github_id<->owner link + account->agents join,
        # rebuilt below from account_link / account_enroll events (same
        # write-ahead-then-replay discipline as membership_grant / quota_spend).
        # Writers (device-flow login, /enroll/account) land in later PRs.
        self.accounts = AccountStore()
        # GA-CORE-1: the agentdex.builders beta registration gate. Rebuilt at boot
        # from invite_grant / invite_redeem events (same replay discipline).
        self.invites = InviteStore()
        # ADX-P1-007: one asyncio.Lock per visitor_name serializing the rated
        # before->append->after rating window in _finish, so two concurrent
        # finishes for the same agent cannot interleave their recompute brackets
        # and inflate a published_delta. Defensive: a single agent may hold up to
        # ARENA_MAX_BATTLES_PER_OWNER concurrent rated battles, so same-visitor
        # finishes can race. Keyed on the rating subject (visitor_name).
        self._finish_locks: dict[str, asyncio.Lock] = {}
        # Battles begun but never ended in a PRIOR process — sessions are in-memory
        # only (reset to {} on boot), so after a restart a client touching such a
        # battle should get a clear 409 'interrupted', not an opaque 403 'no such
        # battle'. Maps battle_id -> owning tenant (token_id) so the 409 is owner-
        # scoped (others still get 403, D7). Begun-minus-ended over the log replay.
        self._interrupted: dict[str, str] = {}
        for event in self.events.iter_events():
            etype = event.get("type")
            payload = event.get("payload") or {}
            try:
                if etype == "register":
                    self._registered.add(payload["name"])
                elif etype in ("battle_begin", "battle_fork"):
                    # A fork is a live sandbox battle too (recorded as battle_fork with
                    # its own battle_id + tenant_id, closed by the same battle_end). It
                    # must join the interrupted set so a post-restart touch gets the 409
                    # signal, not an opaque 403 (PR #246 review).
                    bid, tid = payload.get("battle_id"), payload.get("tenant_id")
                    if isinstance(bid, str) and isinstance(tid, str):
                        self._interrupted[bid] = tid
                elif etype == "battle_end":
                    bid = payload.get("battle_id")
                    if isinstance(bid, str):
                        self._interrupted.pop(bid, None)
                elif etype == "membership_grant":
                    # Replay parses defensively (malformed events must NOT crash boot).
                    owner_raw = payload.get("owner", "")
                    valid_until_raw = payload.get("valid_until_epoch")
                    if not isinstance(owner_raw, str) or not owner_raw:
                        raise ValueError("owner missing/non-string")
                    valid_until = float(valid_until_raw)
                    if not math.isfinite(valid_until) or valid_until < 0:
                        raise ValueError(f"non-finite/negative valid_until: {valid_until!r}")
                    self.authority.grant_membership(owner_raw, valid_until)
                elif etype == "quota_spend":
                    # ADX-P2-004: rehydrate the per-UTC-day quota counter so a
                    # restart no longer resets every agent's daily cap. Same
                    # write-ahead-then-replay shape as membership_grant; the
                    # authority's replay drops stale prior-day keys itself.
                    key = payload.get("key")
                    if not isinstance(key, str) or not key:
                        raise ValueError("quota_spend key missing/non-string")
                    self.authority.replay_quota_spend(key)
                elif etype == "account_link":
                    # ADR-0013 D3: rehydrate the github_id<->owner link so a
                    # returning device-flow login resolves to the same verified
                    # email across restarts. Defensive parse (a malformed event
                    # must not crash boot); AccountStore.link re-validates owner.
                    github_id = payload.get("github_id")
                    owner_raw = payload.get("owner")
                    if not isinstance(github_id, str) or not github_id:
                        raise ValueError("account_link github_id missing/non-string")
                    if not isinstance(owner_raw, str) or not owner_raw:
                        raise ValueError("account_link owner missing/non-string")
                    self.accounts.link(github_id, owner_raw)
                elif etype == "account_enroll":
                    # ADR-0013 D6: rehydrate the account->agents join that
                    # `adx status` reads. Same defensive shape as above.
                    owner_raw = payload.get("owner")
                    agent_name = payload.get("agent_name")
                    if not isinstance(owner_raw, str) or not owner_raw:
                        raise ValueError("account_enroll owner missing/non-string")
                    if not isinstance(agent_name, str) or not agent_name:
                        raise ValueError("account_enroll agent_name missing/non-string")
                    self.accounts.add_agent(owner_raw, agent_name)
                elif etype == "invite_grant":
                    # GA-CORE-1: rehydrate a minted invite by its hash (idempotent).
                    # Tolerate a legacy plaintext "code" payload by hashing it
                    # (migration-safe for any log written before codes were hashed).
                    code_hash = payload.get("code_hash")
                    if (
                        code_hash is None
                        and isinstance(payload.get("code"), str)
                        and payload["code"]
                    ):
                        code_hash = hash_invite_code(payload["code"])
                    if not isinstance(code_hash, str) or not code_hash:
                        raise ValueError("invite_grant code_hash missing/non-string")
                    self.invites.grant_hash(code_hash)
                elif etype == "invite_redeem":
                    # GA-CORE-1: rehydrate a redemption so an admitted owner stays
                    # admitted across restarts (and a used code stays used). Same
                    # legacy plaintext fallback as invite_grant.
                    code_hash = payload.get("code_hash")
                    if (
                        code_hash is None
                        and isinstance(payload.get("code"), str)
                        and payload["code"]
                    ):
                        code_hash = hash_invite_code(payload["code"])
                    owner_raw = payload.get("owner")
                    if not isinstance(code_hash, str) or not code_hash:
                        raise ValueError("invite_redeem code_hash missing/non-string")
                    if not isinstance(owner_raw, str) or not owner_raw:
                        raise ValueError("invite_redeem owner missing/non-string")
                    self.invites.grant_hash(code_hash)  # ensure the code exists before redeem
                    self.invites.redeem_hash(code_hash, owner_raw)
            except Exception:
                log.warning(
                    "skipping malformed event during replay: type=%r seq=%r",
                    etype,
                    event.get("seq"),
                    exc_info=True,
                )
        self.artifacts_dir = Path(artifacts_dir)
        self.notify_owner = notify_owner  # out-of-band channel (email/webhook)
        self.turn_budget_s = turn_budget_s
        self._rated_seed_secret = rated_seed_secret or secrets.token_hex(16)
        self.now = now
        self.sessions: dict[str, BattleSession] = {}
        # In-flight /battle/begin (or /fork) starts that have passed the per-owner
        # admission check but not yet published their session into self.sessions —
        # an atomic reservation so concurrent starts from one owner can't burst past
        # the cap (ADR-0012 §7; PR #243 review). owner_norm -> reserved count.
        self._owner_inflight: dict[str, int] = {}
        self.cap_503_total = 0  # capacity-shed counter (sidecar pool full) — surfaced on /metrics
        self.pending_enrollments: dict[str, EnrollRequest] = {}
        self.battle_nonces: dict[str, str] = {}  # nonce -> token_id
        self.replays: dict[str, dict[str, Any]] = {}
        self._publication_allowed_override = True

    @property
    def publication_allowed(self) -> bool:
        import os

        selftest_dir = Path(os.environ.get("ARENA_SELFTEST_DIR", "/tmp/agentdex/arena-selftest"))
        if selftest_dir.is_dir():
            reports = sorted(selftest_dir.glob("*.report.json"))
            if reports:
                try:
                    report = json.loads(reports[-1].read_text())
                    return bool(report.get("publication_allowed", True))
                except Exception:
                    pass
        return self._publication_allowed_override

    @publication_allowed.setter
    def publication_allowed(self, val: bool) -> None:
        self._publication_allowed_override = val

    # ---------- enrollment (A1: human-in-the-loop) ----------
    #
    # ONE enrollment validator, shared by the email-OOB path (enroll_request +
    # enroll_confirm) and the account path (enroll_account, ADR-0013 D3). Global
    # agent-name uniqueness is load-bearing — the arena's public identity is
    # keyed by agent_name ALONE (ladder, badges) — so account-enroll must claim
    # a name through the SAME reserved-name guard, the SAME global _registered
    # rejection, and the SAME durable register event, never a per-account fork
    # (D3: two owners claiming one name would collapse onto one ladder identity).

    def _guard_reserved_name(self, raw_name: str) -> str:
        """Sanitize a requested name + reject the reserved set (case-insensitive:
        anchor- prefix, visitor, foe, _house, _ladder). Returns the clean name;
        raises opaque 400 on a reserved name. Does NOT touch _registered."""
        agent_name = sanitize_name(raw_name) or "visitor"
        name_lower = agent_name.lower()
        if name_lower.startswith("anchor-") or name_lower in (
            "visitor",
            "foe",
            "_house",
            "_ladder",
        ):
            raise _opaque_error(400, "reserved agent name")
        return agent_name

    def _register_agent(self, agent_name: str) -> None:
        """Claim a (sanitized) name globally: reject a duplicate (opaque 409),
        then append the durable register event BEFORE mutating _registered
        (append-before-publish, P2 PR #56). The single global-uniqueness gate."""
        if agent_name in self._registered:
            raise _opaque_error(409, "agent name already registered")
        self.events.append("register", {"name": agent_name, "frozen": False})
        self._registered.add(agent_name)

    def _mint_consent(
        self, owner: str, agent_name: str, agent_pubkey_hex: str, confirmed_via: str
    ) -> dict[str, Any]:
        """Mint a 7-day consent token with the standard scopes. Shared by every
        enrollment path so the token shape never diverges by how it was obtained
        (D3: account-enroll changes only HOW the token is obtained)."""
        claims = ConsentClaims(
            token_id=uuid.uuid4().hex[:16],
            owner=owner,
            agent_name=agent_name,
            agent_pubkey_hex=agent_pubkey_hex,
            scopes=["enroll", "battle", "evolve", "badge_mint"],
            issued_at=self.now(),
            expires_at=self.now() + 7 * 86_400,
            confirmed_via=confirmed_via,
        )
        return {"token": self.authority.mint(claims), "expires_at": claims.expires_at}

    def enroll_request(self, req: EnrollRequest) -> dict[str, Any]:
        # GA-CORE-1 beta gate: the legacy email-OOB path also mints a consent
        # token (at /enroll/confirm, via _mint_consent), so it must be invite-
        # gated too — otherwise ARENA_INVITE_REQUIRED is bypassable by self-
        # serving through request→confirm and never presenting an invite. Fail
        # fast BEFORE generating/sending the OOB code so an un-admitted owner
        # never receives one. Optional-at-boot (flag unset → open enroll). The
        # owner is client-supplied here, but admission is keyed on the normalized
        # owner an invite was redeemed for (a session-authed act), so a client
        # cannot self-admit by naming an arbitrary owner.
        if self._invite_required() and not self.invites.is_admitted(req.owner):
            raise _opaque_error(403, "an invitation code is required for the beta")
        code = secrets.token_urlsafe(16)
        agent_name = self._guard_reserved_name(req.agent_name)
        # Request-time fail-fast on a taken name (the authoritative register is at
        # confirm); keep it so the OOB code is never sent for a doomed name.
        if agent_name in self._registered:
            raise _opaque_error(409, "agent name already registered")

        clean = EnrollRequest(
            owner=req.owner,
            agent_name=agent_name,
            agent_pubkey_hex=req.agent_pubkey_hex,
        )
        self.pending_enrollments[code] = clean
        # the code goes to the OWNER out-of-band — never into this response
        self.notify_owner(clean.owner, code)
        return {
            "status": "pending_owner_confirmation",
            "detail": "confirmation code sent to the owner out-of-band",
        }

    def enroll_confirm(self, code: str) -> dict[str, Any]:
        # Peek (not pop) first so a rejected confirm does not consume the pending
        # code — the caller can re-confirm once admitted.
        req = self.pending_enrollments.get(code)
        if req is None:
            raise _opaque_error(404, "unknown/expired enrollment code")
        # GA-CORE-1 beta gate (defense-in-depth at the authoritative mint): never
        # mint a consent token for an un-admitted owner when invites are required.
        # Covers a flag flipped ON after this enrollment was already pending (the
        # enroll_request gate only saw the flag's state at request time).
        if self._invite_required() and not self.invites.is_admitted(req.owner):
            raise _opaque_error(403, "an invitation code is required for the beta")
        self.pending_enrollments.pop(code, None)
        # req.agent_name was already sanitized + guarded at request time.
        self._register_agent(req.agent_name)
        return self._mint_consent(
            req.owner, req.agent_name, req.agent_pubkey_hex, f"web-confirm:{code[:6]}…"
        )

    def enroll_account(
        self, claims: SessionClaims, agent_name: str, agent_pubkey_hex: str
    ) -> dict[str, Any]:
        """Account-authed enroll (ADR-0013 D3): a logged-in human mints a per-agent
        consent token WITHOUT the email-OOB code — the session IS the human proof.

        Runs the SAME validator as the email-OOB path (reserved-name guard +
        global _registered claim + durable register), mints the consent token
        with the session's VERIFIED EMAIL as owner (so membership + quota stay
        single-keyed per human), and records the account->agents join (durable
        account_enroll before returning, so `adx status` survives a restart).
        The pubkey is validated by the request model before this runs, so the
        name is never reserved for a token that then fails to mint."""
        # GA-CORE-1 beta gate: when invites are required, only an owner who has
        # redeemed an invite may enroll. Optional-at-boot (ARENA_INVITE_REQUIRED
        # unset → open enroll, existing behavior). Checked BEFORE reserving a name.
        if self._invite_required() and not self.invites.is_admitted(claims.owner):
            raise PermissionError("an invitation code is required for the beta")
        clean_name = self._guard_reserved_name(agent_name)
        self._register_agent(clean_name)
        # account->agents join (D6) — durable BEFORE returning the token.
        self.events.append("account_enroll", {"owner": claims.owner, "agent_name": clean_name})
        self.accounts.add_agent(claims.owner, clean_name)
        return self._mint_consent(
            claims.owner, clean_name, agent_pubkey_hex, f"account:{claims.session_id}"
        )

    @staticmethod
    def _invite_required() -> bool:
        """Whether the beta invite gate is on (``ARENA_INVITE_REQUIRED=1``). Default
        off so every existing enroll flow + test is unaffected (optional-at-boot)."""
        return os.environ.get("ARENA_INVITE_REQUIRED") == "1"

    def mint_invites(self, count: int, *, actor_hash: str) -> list[str]:
        """Operator-only: mint ``count`` fresh single-use invite codes. Each code's
        ``invite_grant`` is appended to the durable log BEFORE it is returned, so a
        code an operator sees is always one a fresh replay will honor (Class-A)."""
        if not isinstance(count, int) or not (1 <= count <= 1000):
            raise ValueError("count must be an int in [1, 1000]")
        codes: list[str] = []
        for _ in range(count):
            code = new_invite_code()
            # Only the HASH is logged — the plaintext code is a seat-claiming secret
            # and is returned ONCE to the authed operator, never persisted.
            code_hash = hash_invite_code(code)
            self.events.append("invite_grant", {"code_hash": code_hash, "actor_hash": actor_hash})
            self.invites.grant_hash(code_hash)
            codes.append(code)
        return codes

    def redeem_invite(self, claims: SessionClaims, code: str) -> dict[str, Any]:
        """A logged-in human redeems an invite code, admitting their owner to the
        beta. Idempotent for an already-admitted owner (no code burned — survives
        token rotation / re-enrollment). The ``invite_redeem`` event is written-ahead
        BEFORE the in-memory admission (Class-A), so a replay can never disagree."""
        owner_key = _normalize_owner(claims.owner)
        if self.invites.is_admitted(owner_key):
            return {"ok": True, "admitted": True, "owner": owner_key}  # already in, no code burned
        if not self.invites.redeemable(code):
            raise InviteError("invite code is invalid or already used")
        # write-ahead the redemption (HASH only — never the plaintext code), THEN
        # apply it to the in-memory store.
        code_hash = hash_invite_code(code)
        self.events.append("invite_redeem", {"code_hash": code_hash, "owner": owner_key})
        self.invites.redeem_hash(code_hash, owner_key)
        return {"ok": True, "admitted": True, "owner": owner_key}

    def account_quota(self, claims: SessionClaims) -> dict[str, Any]:
        """The ADR-0013 D6 read-only quota dashboard for `adx status`: owner-pooled
        battle + per-agent evolve/badge_mint for today, over the account's agents
        (the account->agents join). Delegates the key/cap/remaining math to the
        ConsentAuthority so it reports against the exact keys spend_quota debits."""
        names = self.accounts.agents_for(claims.owner)
        return self.authority.account_quota_report(claims.owner, names)

    # ---------- battle flow ----------

    def battle_start(self, token: str) -> dict[str, Any]:
        try:
            claims = self.authority.verify(token, scope="battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        nonce = secrets.token_hex(12)
        self.battle_nonces[nonce] = claims.token_id
        return {"battle_nonce": nonce, "pop_challenge": f"arena-pop:{claims.token_id}:{nonce}"}

    async def _append_or_fail_closed(
        self,
        type_: str,
        payload: dict[str, Any],
        *,
        sidecar: Sidecar | None = None,
        battle_id: str | None = None,
        session: BattleSession | None = None,
    ) -> dict[str, Any]:
        """Append a canonical EventLog row with Class-A fail-closed semantics.

        Every externally visible side effect — publishing a session into
        ``self.sessions``, writing a replay/artifact to disk, returning a
        completion receipt — MUST be preceded by the durable EventLog append
        that records it, so a fresh recompute from the log can never disagree
        with what an owner or agent already saw (the honesty contract A8).

        If the append throws (e.g. disk full), FAIL CLOSED: tear down the live
        sidecar battle (no orphan live-but-unlogged battle), mark any live
        session ended-fatal so a retry sees the failure instead of a hang, and
        surface an opaque 500. The caller therefore never publishes a receipt
        the log cannot back. This generalizes the known-good ``/choose`` path.
        """
        try:
            return self.events.append(type_, payload)
        except Exception as e:  # noqa: BLE001 — any append failure is fail-closed
            if session is not None:
                session.ended = {
                    "winner": "",
                    "turns": getattr(session, "turns", 0),
                    "reason": f"fatal: event log write failed: {e!r}",
                }
            if sidecar is not None and battle_id is not None:
                try:
                    await sidecar.request("stop", battle=battle_id)
                except Exception:  # noqa: BLE001 — best-effort teardown
                    pass
            raise _opaque_error(500, f"event log write failed: {e!r}") from None

    async def _append_many_or_fail_closed(
        self,
        items: list[tuple[str, dict[str, Any]]],
        *,
        sidecar: Sidecar | None = None,
        battle_id: str | None = None,
        session: BattleSession | None = None,
    ) -> list[dict[str, Any]]:
        """Append a canonical EventLog group with Class-A fail-closed semantics."""
        try:
            return self.events.append_many(items)
        except Exception as e:  # noqa: BLE001 — any grouped append failure is fail-closed
            if session is not None:
                session.ended = {
                    "winner": "",
                    "turns": getattr(session, "turns", 0),
                    "reason": f"fatal: event log write failed: {e!r}",
                }
            if sidecar is not None and battle_id is not None:
                try:
                    await sidecar.request("stop", battle=battle_id)
                except Exception:  # noqa: BLE001 — best-effort teardown
                    pass
            raise _opaque_error(500, f"event log write failed: {e!r}") from None

    def _record_quota_spend(self, key: str) -> None:
        """Durably record a successful quota spend (ADX-P2-004) so the per-UTC-day
        counter survives a gateway restart — boot replay re-folds ``quota_spend``
        events into ``authority.quota_used``. ``key`` is the exact day-stamped
        counter key ``spend_quota`` just debited.

        Best-effort, NOT fail-closed (Class B): the in-memory debit has already
        committed and — for a rated battle — the live sidecar battle is already
        running, so re-raising a 500 after a successful debit would be a worse
        regression than the bug. Worst case is one slot under-counted across a
        crash in the sub-millisecond append gap, which fails toward leniency
        (an extra slot), vastly better than today's full reset-on-restart.
        """
        try:
            self.events.append("quota_spend", {"key": key, "spent_at": self.now()})
        except Exception:  # noqa: BLE001 — best-effort; the in-memory debit stands
            log.warning("quota_spend append failed (in-memory debit stands)", exc_info=True)

    async def _stop_battle_robustly(self, sidecar: Sidecar, battle_id: str) -> None:
        """Best-effort stop of a live sidecar battle that survives cancellation.

        On the production ``SidecarPool`` path a plain ``await sidecar.request("stop")``
        can be cancelled BEFORE it routes the stop to the owning sidecar, leaving the
        battle live and the pool slot's capacity leaked even though the gateway then
        drops the session (PR #264 review). Dispatch the stop as its own task and
        shield-await it; if the caller is cancelled mid-flight, drain the task to
        completion before propagating so the stop always reaches the sidecar. stop's
        own errors are swallowed (best-effort).
        """

        async def _quiet_stop() -> None:
            with contextlib.suppress(Exception):
                await sidecar.request("stop", battle=battle_id)

        stop_task = asyncio.ensure_future(_quiet_stop())
        try:
            await asyncio.shield(stop_task)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await stop_task
            raise

    def _reserve_owner_slot(self, owner_norm: str) -> None:
        """Atomically admit one more concurrent LIVE battle for ``owner_norm`` or
        raise 429 (anti-monopolization, ADR-0012 §7).

        Counts live sessions (``ended is None`` — finished battles linger in
        ``self.sessions`` so /battle/{id}/state can serve the receipt) PLUS already
        reserved in-flight starts, so simultaneous /battle/begin (or /fork) calls
        from one owner can't each pass the check before any session is published and
        burst past ``ARENA_MAX_BATTLES_PER_OWNER``. MUST be called synchronously (no
        await) between the check and the first await; pair every reservation with
        ``_release_owner_slot`` in a finally (PR #243 review).
        """
        max_per_owner = int(os.environ.get("ARENA_MAX_BATTLES_PER_OWNER", "3"))
        live = sum(1 for s in self.sessions.values() if s.owner == owner_norm and s.ended is None)
        if live + self._owner_inflight.get(owner_norm, 0) >= max_per_owner:
            raise HTTPException(
                status_code=429,
                detail="too many concurrent battles for this owner — finish or forfeit one, then retry",
                headers={"Retry-After": os.environ.get("ARENA_RETRY_AFTER_SEC", "5")},
            )
        self._owner_inflight[owner_norm] = self._owner_inflight.get(owner_norm, 0) + 1

    def _release_owner_slot(self, owner_norm: str) -> None:
        """Release a reservation taken by ``_reserve_owner_slot`` (call in a finally)."""
        remaining = self._owner_inflight.get(owner_norm, 0) - 1
        if remaining > 0:
            self._owner_inflight[owner_norm] = remaining
        else:
            self._owner_inflight.pop(owner_norm, None)

    async def battle_begin(self, req: BeginRequest, *, sidecar: Sidecar) -> dict[str, Any]:
        try:
            claims = self.authority.verify(req.token, scope="battle")
            if self.battle_nonces.pop(req.battle_nonce, None) != claims.token_id:
                raise ConsentError("unknown battle nonce")
            self.authority.verify_pop(claims, req.battle_nonce, req.pop_signature_hex)
            if req.lane == "rated":
                # Class B (quota spend-after-success): publication_allowed is
                # the instrument-red kill-switch (PASS 36) — it is the
                # operator's responsibility, not the visiting agent's. Reject
                # BEFORE we spend a daily slot so the user does not lose a
                # rated slot to a server-side outage. The actual `spend_quota`
                # call moves below to AFTER the durable battle_begin append
                # succeeds, so invalid-team 422 (PASS 35) / capacity 503 /
                # sidecar error / append failure can no longer cost the user a
                # daily slot.
                if not self.publication_allowed:
                    raise ConsentError("rated lane paused: instrument self-test red")
                # Rated quota PREFLIGHT (read-only): reject an already-exhausted caller
                # HERE — before ANY team resolution or sidecar work (pack_team /
                # validate_team / sidecar.start) and before the durable battle_begin
                # append — so an over-quota client minting fresh nonces via
                # /battle/start can neither burn sidecar work nor write orphan rated
                # begins. check_quota does NOT debit; the authoritative spend_quota
                # still follows AFTER a successful append (Class B spend-after-success).
                # PR #181 review 3424588956 + PR #230 review 3432471668.
                self.authority.check_quota(claims, scope="battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None

        # Per-owner concurrency cap (anti-monopolization, ADR-0012 §7): one owner must
        # not fill the shared sidecar pool and starve the other ~99 users. Keyed on the
        # NORMALIZED owner (not token_id) so /enroll/reissue with a fresh token cannot
        # reset the cap — the same rotation-as-reset closure the battle quota uses.
        # Reserved synchronously BEFORE any sidecar/team work (so a capped owner burns
        # nothing AND concurrent starts can't burst past the cap) and released in the
        # finally below. 429 (too many live battles) is distinct from the pool-full 503.
        owner_norm = _normalize_owner(claims.owner)
        try:
            self._reserve_owner_slot(owner_norm)
        except HTTPException:
            # Transient admission failure: restore the nonce we popped above so a
            # client honoring Retry-After by replaying the SAME /battle/begin works
            # instead of hitting 403 unknown nonce (PR #243 review).
            self.battle_nonces[req.battle_nonce] = claims.token_id
            raise
        released = False

        def _hand_off() -> None:
            # Once the session is published the LIVE count covers this owner, so drop
            # the in-flight reservation (release-once) — else the post-publish work
            # would double-count and could spuriously 429 the owner's next battle. If
            # _run raises before publishing, the finally still releases (PR #254).
            nonlocal released
            if not released:
                released = True
                self._release_owner_slot(owner_norm)

        try:
            return await self._run_battle_begin(
                req, claims, owner_norm, sidecar=sidecar, on_published=_hand_off
            )
        finally:
            _hand_off()

    async def _run_battle_begin(
        self,
        req: BeginRequest,
        claims: ConsentClaims,
        owner_norm: str,
        *,
        sidecar: Sidecar,
        on_published: Callable[[], None],
    ) -> dict[str, Any]:
        """battle_begin's team-pack → sidecar-start → durable-append → publish body,
        run while the owner-slot reservation is held (PR #243). Split out so the
        reservation's try/finally wraps every await + the self.sessions publish."""
        if req.lane == "rated":
            if req.gym_leader is not None:
                raise _opaque_error(400, "cannot select gym leader in rated lane")
            # server-side matchmaking vs held-out pool; seed server-secret (A3)
            opponent = RATED_POOL[
                int.from_bytes(
                    hashlib.blake2b(req.battle_nonce.encode(), digest_size=2).digest(), "big"
                )
                % len(RATED_POOL)
            ]
            seed_material = hashlib.blake2b(
                f"{self._rated_seed_secret}:{req.battle_nonce}".encode(), digest_size=8
            ).digest()
            seed = [int.from_bytes(seed_material[i : i + 2], "big") for i in range(0, 8, 2)]
        else:
            if req.gym_leader is not None and req.gym_leader not in GYM_LEADERS:
                raise _opaque_error(400, f"unknown gym leader: {req.gym_leader}")
            opponent = req.gym_leader or GYM_LEADERS[0]
            seed = [
                int.from_bytes(
                    hashlib.blake2b(req.battle_nonce.encode(), digest_size=2).digest(), "big"
                ),
                7,
                7,
                7,
            ]

        battle_id = f"{req.lane}-{uuid.uuid4().hex[:10]}"
        visitor = claims.agent_name
        session = BattleSession(
            battle_id=battle_id,
            claims_token_id=claims.token_id,
            owner=owner_norm,
            visitor_name=visitor,
            lane=req.lane,
            opponent=opponent,
            seed=seed,
            sidecar=sidecar,
            opponent_policy=_opponent_policy(opponent, sidecar, seed[0] + 13),
        )
        # Default sandbox opponent (no explicit gym): swap the plain anchor-random
        # for the autopilot-punisher so "always choose 1" no longer trivially wins,
        # while a player who actually varies their play still faces the gentle bot.
        # Explicit gym picks keep their chosen difficulty; rated lane is untouched.
        if req.lane == "sandbox" and req.gym_leader is None:
            session.opponent_policy = autopilot_punisher(
                sidecar, seed[0] + 13, on_autopilot=lambda: _is_autopilot(session)
            )
        session.p1_team = None  # set below once the visitor team is resolved
        team = req.team
        if team is None:
            team = await pack_team(sidecar, next(iter(starter_pack().values())))
        else:
            # Sanitize team nicknames (P1 PR #51 comment follow-up)
            team = sanitize_packed_team(team)
            # A client-supplied team is UNTRUSTED: validate against the pinned
            # banlist server-side BEFORE it can enter a battle. This enforces the
            # F3 "an invalid team simply cannot play" contract that BeginRequest.team
            # only asserted in a comment — closing the trust gap the authoring loop
            # (POST /team/draft) leans on. Ship the gate before the axis it protects.
            valid, errors = await validate_team(sidecar, team)
            if not valid:
                raise _opaque_error(422, f"invalid team rejected: {errors[:3]}")
        if req.lane == "sandbox":
            gym_team_name = _gym_team_name(opponent)
            opp_team = await pack_team(sidecar, starter_pack()[gym_team_name])
            session.explicit_opponent = req.gym_leader is not None
        else:
            # Rated lane: i.i.d. anchor-team matchmaking (#8). Draw opponent team
            # from RATED_ANCHOR_TEAMS via extended nonce hash, independent of visitor
            # team. Seed and opponent team disclosed post-result (NOT at begin).
            gym_team_name = None  # rated does not pre-disclose
            anchor_team_idx = int.from_bytes(
                hashlib.blake2b(f"team:{req.battle_nonce}".encode(), digest_size=2).digest(),
                "big",
            ) % len(RATED_ANCHOR_TEAMS)
            anchor_team_name = RATED_ANCHOR_TEAMS[anchor_team_idx]
            opp_team = await pack_team(sidecar, starter_pack()[anchor_team_name])
        session.p1_team, session.p2_team = team, opp_team
        # (Rated quota preflight ran at the top of battle_begin — before any team or
        # sidecar work — so an exhausted caller never reaches here. PR #230 review.)
        try:
            resp = await sidecar.request(
                "start",
                battle=battle_id,
                format="gen9ou",
                seed=seed,
                p1={"name": visitor, "team": team},
                p2={"name": opponent, "team": opp_team},
            )
        except SidecarError as e:
            # The shared sim caps concurrent live battles. Surface that as a clear,
            # RETRYABLE 503 (not an opaque 400 a client reads as its own fault) so a
            # visiting agent knows to finish/forfeit a battle and retry (playtest G-03).
            if "capacity" in str(e).lower():
                self.cap_503_total += 1  # operator-visible shed counter (/metrics)
                raise HTTPException(
                    status_code=503,
                    detail="arena at capacity — finish or forfeit an active battle, then retry",
                    headers={"Retry-After": os.environ.get("ARENA_RETRY_AFTER_SEC", "5")},
                ) from None
            raise
        # Class A (atomicity): the durable begin receipt MUST exist before the
        # session is published into self.sessions — otherwise an append failure
        # would leave a live, choosable battle the log never recorded. Append
        # fail-closed FIRST; on failure the live sidecar battle is stopped and
        # we 500, so the session below is never reached. Chain event mirrors to
        # Postgres write-behind. NO seed in the payload: mirror rows are
        # tenant-readable and the rated seed stays secret until the post-result
        # disclosure (A3).
        await self._append_or_fail_closed(
            "battle_begin",
            {
                "tenant_id": claims.token_id,
                "battle_id": battle_id,
                "lane": req.lane,
                "visitor": visitor,
                "opponent": opponent,
            },
            sidecar=sidecar,
            battle_id=battle_id,
        )
        # Class B (quota spend-after-success): the rated battle has now passed
        # every fallible gate (verify / pop / publication_allowed / team-
        # validate / pack_team / sidecar.start / durable append). Spend the
        # daily slot HERE so any earlier failure cannot cost the user a slot.
        # If the cap is exhausted the sidecar battle is stopped before we
        # return 403, so no orphan live battle is left behind. Sandbox lanes
        # don't have a "battle" quota, so this stays behind the `rated` guard.
        if req.lane == "rated":
            try:
                _, spent_key = self.authority.spend_quota(claims, scope="battle")
            except ConsentError as e:
                try:
                    await sidecar.request("stop", battle=battle_id)
                except Exception:  # noqa: BLE001 — best-effort teardown
                    pass
                raise _opaque_error(403, e) from None
            # Durable so the daily cap survives a restart (ADX-P2-004).
            self._record_quota_spend(spent_key)
        self.sessions[battle_id] = session
        on_published()  # cap count handed off to the live session; drop the reservation
        try:
            state = await self._advance(session, resp["state"], visitor_choice=None)
            out = {"battle_id": battle_id, "lane": req.lane, **state}
            if gym_team_name is not None:
                # Disclosed signature team (#3): scouting it and drafting a counter IS
                # the sandbox game; this is what makes team_mutation a real lever.
                out["opponent_team_name"] = gym_team_name
                out["opponent_team"] = opp_team
            return out
        except BaseException:
            # Published but failed before returning — stop the live sidecar battle
            # (a pooled sidecar releases the slot's capacity only on an explicit
            # stop, PR #259/#264 review) BEFORE dropping our only handle. The stop is
            # dispatched cancellation-robustly; the pop sits in a finally so even a
            # cancelled cleanup still removes the dead battle from the cap (PR #261).
            try:
                await self._stop_battle_robustly(sidecar, battle_id)
            finally:
                self.sessions.pop(battle_id, None)
            raise

    async def _expire_if_stale(self, session: BattleSession) -> None:
        # Skip while a shielded finish is outstanding (session.finish_task set):
        # the battle already reached a terminal state and is being recorded in the
        # background, so forfeiting it here would queue a second _finish that
        # appends a duplicate battle_end and overwrites the real result with a
        # bogus timeout forfeit (PR #289 review 3435535478).
        if (
            session.ended is None
            and session.finish_task is None
            and self.now() - session.last_touch > self.turn_budget_s
        ):
            input_log = []
            if session.sidecar is not None:
                try:
                    resp = await session.sidecar.request(
                        "stop",
                        battle=session.battle_id,
                        forfeit_side=session.visitor_side,
                    )
                    if len(session.visitor_choices) > 0:
                        input_log = list(resp.get("inputLog") or [])
                except Exception:  # noqa: BLE001
                    pass
            await self._finish(
                session,
                {
                    "winner": session.opponent,
                    "turns": session.turns,
                    "inputLog": input_log,
                    "keyLines": [],
                },
            )
            if session.ended is not None:
                session.ended["forfeit"] = "turn budget exceeded"

    async def _advance(
        self, session: BattleSession, state: dict[str, Any], *, visitor_choice: str | None
    ) -> dict[str, Any]:
        """Drive the step protocol: submit visitor choice (if any) + opponent
        auto-choices until the visitor has a pending request or the battle ends."""
        sidecar = session.sidecar
        other = "p2" if session.visitor_side == "p1" else "p1"
        for _ in range(200):
            # Observability updates: update foe active details and log events
            active_info = state.get("active") or {}
            active_hp_info = state.get("active_hp") or {}
            foe_species = active_info.get(other)
            if foe_species:
                session.foe_species = sanitize_name(foe_species) or foe_species
            foe_pct = active_hp_info.get(other)
            if foe_pct is not None:
                session.foe_hp_pct = foe_pct

            log_events = state.get("log_events") or []
            current_event_turn = session.turns
            for line in log_events:
                if line.startswith("|turn|"):
                    try:
                        current_event_turn = int(line.split("|")[2])
                    except (IndexError, ValueError):
                        pass
                formatted = _format_log_line(line, session.visitor_side)
                if formatted:
                    _push_recent(session, f"T{current_event_turn}: {formatted}")

            if state.get("end"):
                # The battle has reached a terminal sidecar state — the finish
                # MUST run to completion even if THIS request is cancelled (e.g.
                # the /choose caller disconnects) while _finish is suspended on the
                # per-visitor rating lock. /choose clears session.pending before
                # calling here, and PR #276 keeps session.ended None until the
                # durable append succeeds, so a bare cancel mid-lock-wait would
                # strand a battle that already ended as pending=None + ended=None —
                # /state then 409s until stale-expiry records a bogus timeout
                # forfeit for a battle whose real result was lost. Run the finish
                # as a TRACKED task and shield the await: the cancel reaches the
                # caller while the durable battle_end/period/replay + session.ended
                # land in the background (PR #276 review 3434024561).
                #
                # session.finish_task holds a STRONG reference so the loop's weak
                # task ref can't GC the background finish mid-wait (PR #289 review
                # 3435535482), and doubles as a "finishing" marker so
                # _expire_if_stale won't queue a SECOND forfeit finish while this
                # one is outstanding under long lock contention (PR #289 review
                # 3435535478). No double-finish either way: a retry sees
                # pending=None and 409s rather than re-entering _finish.
                finish_task: asyncio.Task[dict[str, Any]] = asyncio.ensure_future(
                    self._finish(session, state["end"])
                )
                session.finish_task = finish_task

                def _clear_finish(task: asyncio.Future, sess: BattleSession = session) -> None:
                    sess.finish_task = None
                    # Retrieve any background failure so asyncio doesn't emit a bare
                    # "Task exception was never retrieved" — but LOG it first. When
                    # the /choose caller was cancelled, this callback is the ONLY
                    # server-side signal that committing the terminal receipt
                    # failed; silently consuming the exception would make those
                    # failures invisible (PR #291 review 3435604694). (The
                    # non-cancelled caller also gets it re-raised; a duplicate log
                    # for that rare path is acceptable vs. losing the signal.)
                    if not task.cancelled():
                        exc = task.exception()
                        if exc is not None:
                            log.error(
                                "backgrounded finish failed for battle %s: %r",
                                sess.battle_id,
                                exc,
                                exc_info=exc,
                            )

                finish_task.add_done_callback(_clear_finish)
                return await asyncio.shield(finish_task)

            choices: dict[str, str] = {}
            if visitor_choice is not None:
                choices[session.visitor_side] = visitor_choice
                visitor_choice = None
            raw_opp = (state.get("pending") or {}).get(other)
            if raw_opp is not None:
                opp_req = parse_request(raw_opp)
                ctx = BattleContext(
                    side=other,
                    my_species=(state.get("active") or {}).get(other) or active_species(opp_req),
                    opponent_species=(state.get("active") or {}).get(session.visitor_side),
                    turns=int(state.get("turns", 0)),
                )
                opp_choice = await call_policy(session.opponent_policy, opp_req, ctx)
                if opp_choice is not None:
                    choices[other] = opp_choice
            raw_vis = (state.get("pending") or {}).get(session.visitor_side)
            if raw_vis is not None and session.visitor_side not in choices:
                vis_req = parse_request(raw_vis)
                # A `wait` request (e.g. the visitor idles while the opponent
                # picks a post-faint switch) carries no legal choices — do NOT
                # prompt the agent for it; let the opponent's choice advance the
                # step and re-evaluate. Only surface a real, actionable request.
                if not vis_req.wait and legal_choices(vis_req):
                    session.pending = vis_req
                    session.turns = int(state.get("turns", 0))
                    return self._render(session, state)
            if not choices:
                raise _opaque_error(500, f"{session.battle_id}: protocol stall")
            resp = await sidecar.request("step", battle=session.battle_id, choices=choices)
            state = resp["state"]
        raise _opaque_error(500, f"{session.battle_id}: advance loop overrun")

    def _render(self, session: BattleSession, state: dict[str, Any]) -> dict[str, Any]:
        assert session.pending is not None
        session.last_state = state
        ctx = BattleContext(
            side=session.visitor_side,
            my_species=(state.get("active") or {}).get(session.visitor_side)
            or active_species(session.pending),
            opponent_species=(state.get("active") or {}).get(
                "p2" if session.visitor_side == "p1" else "p1"
            ),
            turns=session.turns,
        )
        return {
            "status": "your_move",
            "turn": session.turns,
            "state": render_state(
                session.pending,
                ctx,
                scratchpad=session.scratchpad,
                recent_turns=list(session.recent),
            ),
            "n_choices": len(legal_choices(session.pending)),
            "foe_active": session.foe_species,
            "foe_hp_pct": session.foe_hp_pct if session.foe_species else None,
            "recent_turns": list(session.recent),
        }

    def _check_collusion(self, session: BattleSession, turns: int) -> str | None:
        """Run collusion forensics heuristics: win-transfer, low-entropy choices, early forfeits.

        ``turns`` is passed in (not read off ``session.ended``) so _finish need not
        publish an in-memory end marker before the durable append — that early
        marker, set before the rated finish lock wait, could surface an unbacked
        partial receipt on /state /choose if the finish was cancelled mid-wait
        (PR #269 review 3433532481)."""
        if turns < 3:
            return "early forfeit (< 3 turns)"

        if len(session.visitor_choices) >= 5 and len(set(session.visitor_choices)) == 1:
            return (
                f"low-entropy sequence (repeatedly clicked choice: {session.visitor_choices[0]!r})"
            )

        # Win-transfer: build participant map and check history of matches between this pair
        begin_map = {}
        for ev in self.events.iter_events():
            if ev.get("type") == "battle_begin":
                p = ev.get("payload") or {}
                bid = p.get("battle_id")
                if bid:
                    begin_map[bid] = (p.get("visitor"), p.get("opponent"))

        visitor = session.visitor_name
        opponent = session.opponent
        visitor_wins = 0
        opponent_wins = 0
        total_matches = 0

        for ev in self.events.iter_events():
            if ev.get("type") == "battle_end":
                p = ev.get("payload") or {}
                bid = p.get("battle_id")
                if bid in begin_map:
                    vis, opp = begin_map[bid]
                    if (vis == visitor and opp == opponent) or (vis == opponent and opp == visitor):
                        winner = p.get("winner")
                        total_matches += 1
                        if winner == visitor:
                            visitor_wins += 1
                        elif winner == opponent:
                            opponent_wins += 1

        if total_matches >= 5:
            if visitor_wins == total_matches or opponent_wins == total_matches:
                return f"win-transfer: one-sided results over {total_matches} matches ({visitor_wins} - {opponent_wins})"

        return None

    async def _finish(self, session: BattleSession, end: dict[str, Any]) -> dict[str, Any]:
        winner = sanitize_name(end.get("winner") or "")
        input_log = list(end.get("inputLog") or [])
        log_digest = hashlib.blake2b("\n".join(input_log).encode(), digest_size=16).hexdigest()
        turns = int(end.get("turns", 0))
        # NOTE: session.ended stays None until the publish phase below. It is set
        # ONLY once every canonical append has succeeded (the full receipt) — never
        # as an early in-memory marker. /state + /choose surface any non-None
        # session.ended, so writing a partial marker here would advertise a battle
        # as "ended" with no durable battle_end/period/replay backing it — and the
        # rated finish lock wait (a suspension point) sits between such a marker and
        # the append, so a cancel mid-wait would strand the partial (PR #269 review
        # 3433532481). The collusion check takes `turns` directly for the same reason.

        # Check collusion forensics. The DETAILED reason (which heuristic +
        # threshold fired) is recorded in the durable "quarantine" EventLog row
        # and the server log for operator audit, but only the OPAQUE public
        # reason is surfaced on the wire — naming the exact signal lets a
        # colluder evade it (D7 anti-enumeration). The public quarantine flags are
        # applied to the receipt in the publish phase below, not to an early marker.
        collusion_reason = self._check_collusion(session, turns)
        if collusion_reason:
            log.warning("collusion quarantine (battle=%s): %s", session.battle_id, collusion_reason)

        # Sandbox gym badge eligibility — computed here, appended in the durable
        # phase below so a badge is never written without its battle_end anchor.
        badge_awarded = None
        if (
            session.lane == "sandbox"
            and session.opponent in GYM_BADGES
            and winner == session.visitor_name
        ):
            badge_awarded = GYM_BADGES[session.opponent]

        signatures = [
            s.model_dump()
            for s in extract_signatures(list(end.get("keyLines") or []), side=session.visitor_side)
        ]

        # ---- Class A (atomicity): durable append phase, fail-closed ----
        # Every canonical EventLog row is committed BEFORE any externally visible
        # publish (artifact file, /replay record, returned receipt). The end
        # receipt can span battle_end + badge/quarantine + register/period, so
        # commit the whole group via EventLog.append_many: either every row lands
        # with one valid hash chain, or none do. If the grouped append throws,
        # _append_many_or_fail_closed stops the sidecar, marks the session
        # ended-fatal, and 500s — nothing below is published.
        event_items: list[tuple[str, dict[str, Any]]] = [
            (
                "battle_end",
                {
                    "tenant_id": session.claims_token_id,
                    "battle_id": session.battle_id,
                    "lane": session.lane,
                    "winner": winner,
                    "turns": turns,
                    "input_log_blake2b16": log_digest,
                },
            )
        ]
        if badge_awarded:
            event_items.append(
                (
                    "badge",
                    {
                        # ADX-P1-002 (owner export): badge events carry the owner's
                        # tenant_id so /my/events can return them via the same
                        # top-level filter every other tenant-owned row uses.
                        "tenant_id": session.claims_token_id,
                        "agent_name": session.visitor_name,
                        "badge": badge_awarded,
                        "battle_id": session.battle_id,
                        "timestamp": self.now(),
                    },
                )
            )
        if collusion_reason:
            event_items.append(
                (
                    "quarantine",
                    {
                        "battle_id": session.battle_id,
                        "reason": collusion_reason,
                        "timestamp": self.now(),
                    },
                )
            )
        rating_block: dict[str, Any] | None = None
        before_rating: Rating | None = None
        new_registered: list[str] = []
        # ADX-P1-007: hold a per-visitor lock across the whole before->append->after
        # window so a concurrent same-visitor finish cannot land its rating period
        # between this one's `before` snapshot and `after` read (which would make
        # this receipt's published_delta absorb the other battle's movement). Only
        # rated finishes take the lock; sandbox finishes are unaffected.
        rating_lock: asyncio.Lock | None = None
        if session.lane == "rated" and len(input_log) > 0:
            rating_lock = self._finish_locks.setdefault(session.visitor_name, asyncio.Lock())
            await rating_lock.acquire()
        try:
            if session.lane == "rated" and len(input_log) > 0:
                before_rating = recompute_ladder(self.events.path).entrants.get(
                    session.visitor_name, Rating()
                )
                for name in (session.visitor_name, session.opponent):
                    if name not in self._registered:
                        event_items.append(
                            (
                                "register",
                                {"name": name, "frozen": name.startswith("anchor-")},
                            )
                        )
                        new_registered.append(name)
                event_items.append(
                    (
                        "period",
                        {
                            "events": [
                                RatingEvent(
                                    battle_id=session.battle_id,
                                    p1=session.visitor_name,
                                    p2=session.opponent,
                                    winner=winner,
                                    input_log_blake2b16=log_digest,
                                ).model_dump()
                            ]
                        },
                    )
                )

            await self._append_many_or_fail_closed(
                event_items,
                sidecar=session.sidecar,
                battle_id=session.battle_id,
                session=session,
            )
            for name in new_registered:
                self._registered.add(name)
            if before_rating is not None:
                after = recompute_ladder(self.events.path).rating(session.visitor_name)
                delta = Ladder.published_delta(before_rating, after)
                rating_block = {
                    "rating": round(after.rating, 1),
                    "rd": round(after.rd, 1),
                    "published_delta": round(delta, 1) if delta is not None else "INCONCLUSIVE",
                    "seed_disclosure": session.seed,  # revealed post-result (A3)
                    "opponent_team_disclosure": session.p2_team,  # i.i.d. team post-result (#8)
                }
        finally:
            if rating_lock is not None:
                rating_lock.release()

        # ---- publish phase: reached only once every append above succeeded ----
        receipt: dict[str, Any] = {
            "status": "ended",
            "battle_id": session.battle_id,
            "lane": session.lane,
            "winner": winner,
            "you_won": winner == session.visitor_name,
            "turns": turns,
            "failure_signatures": signatures,
            "replay": f"/replay/{session.battle_id}",
            "input_log_blake2b16": log_digest,
            "recent_turns": list(session.recent),
        }
        if collusion_reason:
            receipt["quarantined"] = True
            receipt["quarantine_reason"] = _QUARANTINE_PUBLIC_REASON
        if badge_awarded:
            receipt["badge_awarded"] = badge_awarded
        if session.parent is not None:
            receipt["parent_battle_id"], receipt["fork_turn"] = session.parent
        # Internal record is richer than the public /replay view (which filters to
        # input_log/winner/lane/parent): seed+teams+choices power #6 forks; tenant
        # scopes fork ownership. token_id never leaks publicly.
        self.replays[session.battle_id] = {
            "input_log": input_log,
            "winner": winner,
            "lane": session.lane,
            "tenant": session.claims_token_id,
            "seed": list(session.seed),
            "visitor": session.visitor_name,
            "opponent": session.opponent,
            "explicit_opponent": session.explicit_opponent,
            "teams": [session.p1_team, session.p2_team],
            "visitor_choices": list(session.visitor_choices),
            "parent": session.parent,
            "signatures": signatures,
        }
        if badge_awarded:
            self.replays[session.battle_id]["badge_awarded"] = badge_awarded
        if rating_block is not None:
            receipt["rating"] = rating_block
        session.ended = receipt
        # Durably persist the replay record (ADX-P0-001 residual). self.replays is
        # in-memory only — reset to {} on boot — so without this an honest
        # receipt's /replay/<id> (and /fork, /dispute) 404s for EVERY battle from a
        # prior process after a restart. Writing the full record alongside the
        # input log lets load_replay() rehydrate it on demand. Best-effort like the
        # input log: a write failure is logged, never fatal (the canonical EventLog
        # already committed above).
        try:
            self.artifacts_dir.mkdir(parents=True, exist_ok=True)
            (self.artifacts_dir / f"{session.battle_id}.inputlog.json").write_text(
                json.dumps(input_log, indent=1) + "\n"
            )
            (self.artifacts_dir / f"{session.battle_id}.replay.json").write_text(
                json.dumps(self.replays[session.battle_id], indent=1) + "\n"
            )
        except Exception:
            log.warning("failed to write replay artifact for %s", session.battle_id, exc_info=True)
        return receipt

    def load_replay(self, battle_id: str) -> dict[str, Any] | None:
        """Return a battle's replay record, rehydrating from the durable artifact
        when it is absent in-memory (ADX-P0-001 residual: self.replays is reset to
        {} on boot, so /replay /fork /dispute would otherwise 404 every battle from
        a prior process despite its receipt promising a replay). The rehydrated
        record is cached so subsequent hits stay in-memory. The public /replay view
        still filters to non-private fields, so this leaks nothing new."""
        data = self.replays.get(battle_id)
        if data is not None:
            return data
        # Path-traversal guard: battle_id is a URL path segment; only ever read a
        # `<id>.replay.json` basename inside artifacts_dir.
        if "/" in battle_id or "\\" in battle_id or ".." in battle_id:
            return None
        try:
            loaded = json.loads((self.artifacts_dir / f"{battle_id}.replay.json").read_text())
        except (OSError, ValueError):
            return None
        if not isinstance(loaded, dict):
            return None
        self.replays[battle_id] = loaded
        return loaded

    # ---------- fork (#6 remix-the-loss, sandbox-only) ----------

    async def battle_fork(
        self, src_battle_id: str, src: dict[str, Any], *, turn: int, sidecar: Sidecar, owner: str
    ) -> dict[str, Any]:
        """Branch a finished SANDBOX battle at `turn`: same seed, same teams, same
        fresh-seeded opponent policy; the visitor's recorded choices replay through
        the live step protocol up to the fork point, then control returns to the
        agent. Deterministic anchors make the same-choice suffix reproduce; the
        only free variable is the decision at the fork.

        Fork-determinism (#168 review follow-on): the opponent policy MUST
        mirror what the original battle_begin built, not a plain anchor —
        otherwise a default-sandbox battle (which escalates anchor-random to
        the autopilot_punisher when low-entropy play is detected, gateway.py
        :745) would reproduce here with a gentler bot and the same-choice
        suffix could diverge. So:
          - dispatch through `_opponent_policy` so gym leaders' actual bots
            come back from a fork instead of falling through to anchor-random;
          - when the source opponent is the default `anchor-random`, mirror
            battle_begin and wire up the autopilot_punisher escalation, with
            `_is_autopilot` reading the fork session's own visitor_choices
            list (populated below as choices replay).
        """
        # Forking starts a NEW live sidecar battle, so it must obey the same
        # per-owner concurrency cap as /battle/begin — otherwise an owner can
        # repeatedly fork a finished sandbox battle to create uncapped live
        # sessions and monopolize the shared sidecar pool (PR #243 review). Reserve
        # against the FORKING caller's owner (threaded from the route's verified
        # claims) so the fork session is counted and capped.
        owner_norm = _normalize_owner(owner)
        self._reserve_owner_slot(owner_norm)
        released = False

        def _hand_off() -> None:
            # Release-once at publish: the live session count takes over, so the
            # (potentially long) choice-replay below can't double-count and 429 the
            # owner's next battle; a pre-publish failure still releases (PR #254).
            nonlocal released
            if not released:
                released = True
                self._release_owner_slot(owner_norm)

        try:
            return await self._run_battle_fork(
                src_battle_id,
                src,
                turn=turn,
                sidecar=sidecar,
                owner_norm=owner_norm,
                on_published=_hand_off,
            )
        finally:
            _hand_off()

    async def _run_battle_fork(
        self,
        src_battle_id: str,
        src: dict[str, Any],
        *,
        turn: int,
        sidecar: Sidecar,
        owner_norm: str,
        on_published: Callable[[], None],
    ) -> dict[str, Any]:
        """battle_fork's sidecar-start → append → publish → choice-replay body, run
        while the owner-slot reservation is held (PR #243)."""
        battle_id = f"sandbox-fork-{uuid.uuid4().hex[:8]}"
        opponent = str(src["opponent"])
        session = BattleSession(
            battle_id=battle_id,
            claims_token_id=str(src["tenant"]),
            owner=owner_norm,  # fork is capped to the forking caller's owner (PR #243 review)
            visitor_name=str(src["visitor"]),
            lane="sandbox",
            opponent=opponent,
            seed=list(src["seed"]),
            sidecar=sidecar,
            opponent_policy=_opponent_policy(opponent, sidecar, src["seed"][0] + 13),
        )
        # Mirror battle_begin's default-sandbox escalation so a fork of a
        # default-sandbox battle replays through the SAME bot the original
        # faced (gateway.py:745). Explicit gym picks keep their chosen bot;
        # rated forks can never get here (battle_fork is sandbox-only).
        # `explicit_opponent` is persisted in the replay record: True when the
        # visitor named their opponent (req.gym_leader is not None). An explicit
        # anchor-random pick must NOT escalate — the visitor chose the gentle
        # bot; rewiring to autopilot_punisher in the fork diverges from the
        # original outcome (PR #176 review follow-up).
        if opponent == "anchor-random" and not src.get("explicit_opponent", False):
            session.opponent_policy = autopilot_punisher(
                sidecar,
                src["seed"][0] + 13,
                on_autopilot=lambda: _is_autopilot(session),
            )
        session.p1_team, session.p2_team = src["teams"]
        session.parent = (src_battle_id, turn)
        resp = await sidecar.request(
            "start",
            battle=battle_id,
            format="gen9ou",
            seed=session.seed,
            p1={"name": session.visitor_name, "team": session.p1_team},
            p2={"name": session.opponent, "team": session.p2_team},
        )
        # Class A (atomicity): record the fork lineage durably BEFORE the fork
        # session is published/replayed — an append failure must not leave a live
        # fork with no parent-lineage row. The payload is independent of the
        # choice replay below, so appending it up-front loses nothing. Fail-closed
        # stops the sidecar battle and 500s before the session is reachable.
        await self._append_or_fail_closed(
            "battle_fork",
            {
                "tenant_id": session.claims_token_id,
                "battle_id": battle_id,
                "parent_battle_id": src_battle_id,
                "fork_turn": turn,
            },
            sidecar=sidecar,
            battle_id=battle_id,
        )
        self.sessions[battle_id] = session
        on_published()  # cap count handed off to the live session; drop the reservation
        try:
            state = await self._advance(session, resp["state"], visitor_choice=None)
            for ch in src.get("visitor_choices", []):
                if session.ended is not None or session.turns >= turn:
                    break
                if session.pending is None:
                    break
                session.pending = None
                # Mirror what /battle/{id}/choose does for live choices: record the
                # replayed choice on the fork session so _is_autopilot sees the
                # same low-entropy sequence the original opponent saw. Without this
                # the autopilot_punisher (re-wired above for default sandbox forks)
                # would never escalate on the replayed prefix even though the
                # original battle had already escalated — same-choice suffix would
                # then diverge.
                session.visitor_choices.append(ch)
                step = await sidecar.request(
                    "step", battle=battle_id, choices={session.visitor_side: ch}
                )
                state = await self._advance(session, step["state"], visitor_choice=None)
            return {
                "battle_id": battle_id,
                "lane": "sandbox",
                "parent_battle_id": src_battle_id,
                "fork_turn": turn,
                **state,
            }
        except BaseException:
            # Published but failed mid-replay — stop the live sidecar battle (a pooled
            # sidecar frees the slot's capacity only on an explicit stop, PR #259/#264
            # review) BEFORE dropping our only handle, cancellation-robustly. The pop
            # sits in a finally so even a cancelled cleanup removes the dead fork from
            # the cap (PR #261 review).
            try:
                await self._stop_battle_robustly(sidecar, battle_id)
            finally:
                self.sessions.pop(battle_id, None)
            raise

    # ---------- public, read-only (L0) ----------

    def ladder_public(self) -> dict[str, Any]:
        if not self.events.path.is_file():
            return {"entrants": {}}
        ladder = recompute_ladder(self.events.path)
        return {
            "entrants": {
                name: {
                    "rating": round(r.rating, 1),
                    "rd": round(r.rd, 1),
                    "games": r.games,
                    "badges": ladder.badges.get(name, []),
                }
                for name, r in sorted(ladder.entrants.items(), key=lambda kv: -kv[1].rating)
                if r.games > 0 or len(ladder.badges.get(name, [])) > 0
            }
        }


def create_app(
    gateway: ArenaGateway, *, sidecar_factory: Callable[[], Sidecar | SidecarPool]
) -> FastAPI:
    @asynccontextmanager
    async def _lifespan(app_: FastAPI) -> AsyncIterator[None]:
        # the persistent sidecar is spawned lazily on first battle; stop it on
        # graceful shutdown so uvicorn (and TestClient teardown) never leak the
        # node subprocess.

        async with app_.state.mcp_session_manager.run():
            yield
            sidecar = app_.state.sidecar
            if sidecar is not None:
                await sidecar.stop()
                app_.state.sidecar = None

    app = FastAPI(title="agentdex-arena", version="0.1.0", lifespan=_lifespan)
    app.state.gateway = gateway
    app.state.sidecar = None
    # Sticky flag: a lazy sidecar start() that raised (e.g. node_modules/sidecar.mjs
    # missing). The instance is never stored on failure, so /healthz can't read it
    # off a returncode — this marker is how a failed start surfaces as unhealthy.
    app.state.sidecar_start_failed = False
    # Serialize the lazy start: two concurrent first sim requests must not each spawn
    # a Node sidecar (PR #248 review). The lock is created in this sync context and
    # binds to the running loop on first acquire.
    app.state.sidecar_lock = asyncio.Lock()

    from agentdex_arena.mcp_surface import current_gateway, current_sidecar_fn

    @app.middleware("http")
    async def set_mcp_context(request, call_next):
        t1 = current_gateway.set(gateway)
        t2 = current_sidecar_fn.set(_sidecar)
        try:
            return await call_next(request)
        finally:
            current_gateway.reset(t1)
            current_sidecar_fn.reset(t2)

    async def _sidecar() -> Sidecar:
        if app.state.sidecar is not None:
            return app.state.sidecar
        async with app.state.sidecar_lock:
            # Re-check under the lock — a concurrent first request may have started
            # it while we waited, so we don't spawn a second Node sidecar.
            if app.state.sidecar is None:
                sc = sidecar_factory()
                try:
                    await sc.start()
                except BaseException:
                    # A failed lazy start must surface as unhealthy. Don't leave a
                    # non-None, unstarted instance (returncode=None reads as "alive"
                    # to /healthz while every sim request fails "sidecar not started").
                    # Set the flag FIRST so a cancel mid-cleanup still marks unhealthy.
                    app.state.sidecar_start_failed = True
                    # If start() spawned a child before raising (ready-event timeout),
                    # stop it so we don't leak a Node process. Run stop() as its own
                    # task and shield-await it; if THIS cleanup is cancelled
                    # (disconnect / shutdown mid-cleanup), still AWAIT the task to
                    # completion before propagating — shield alone would let the cancel
                    # return immediately and the loop could close before the child is
                    # reaped (PR #248/#258/#262 review). stop()'s own errors are
                    # best-effort.
                    stop_task = asyncio.ensure_future(sc.stop())
                    try:
                        await asyncio.shield(stop_task)
                    except asyncio.CancelledError:
                        with contextlib.suppress(Exception):
                            await stop_task
                        raise
                    except Exception:
                        pass
                    raise
                app.state.sidecar = sc
                app.state.sidecar_start_failed = False
        return app.state.sidecar

    # Exposed for tests + non-request callers to drive the lazy start deterministically.
    app.state.ensure_sidecar = _sidecar

    _ARENA_HEALTH = {"ok": True, "service": "agentdex-arena", "lanes": ["sandbox", "rated"]}

    @app.get("/", include_in_schema=False)
    async def root(request: Request):
        # Browsers (Accept: text/html) get the agentdex landing page; API clients
        # and platform health checks (Accept: */* or application/json) get the JSON
        # health body — byte-compatible with the previous GET / behavior.
        landing = Path("web/index.html")
        if "text/html" in request.headers.get("accept", "") and landing.is_file():
            return FileResponse(str(landing), media_type="text/html")
        return _ARENA_HEALTH

    def _sidecar_dead(sc: Sidecar | SidecarPool) -> bool:
        """Liveness of the running sim tier — synchronous, IPC-free (no hang risk)."""
        if isinstance(sc, SidecarPool):
            return sc.any_dead()
        return sc.returncode is not None

    @app.get("/healthz", include_in_schema=False)
    async def healthz(response: Response) -> dict:
        # Real readiness probe (was a static {ok:true}). The sidecar spawns lazily
        # on the first battle, so a None sidecar is READY (it will start on demand).
        # Once spawned, a crashed node process → 503 so the platform recycles the
        # container instead of serving an OOM/dead-sidecar spiral. A lazy start that
        # RAISED (missing node_modules/sidecar.mjs) is unhealthy too — it left no
        # instance to read a returncode from, so the sticky flag carries it. Liveness
        # is read from the cached returncode (no IPC) to keep the probe cheap.
        sc = app.state.sidecar
        if app.state.sidecar_start_failed or (sc is not None and _sidecar_dead(sc)):
            response.status_code = 503
            return {"ok": False, "service": "agentdex-arena", "detail": "sidecar unavailable"}
        return _ARENA_HEALTH

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> dict:
        # Operator visibility for the launch (no metrics existed — the gap between a
        # healthy spike and an OOM spiral was invisible). Cheap counters read inline;
        # sidecar RSS is best-effort (IPC) and bounded by a short timeout so a wedged
        # sidecar can't hang the endpoint — null on timeout/None/crash, never a hang.
        sc = app.state.sidecar
        rss_mb: float | None = None
        if sc is not None and not _sidecar_dead(sc):
            try:
                rss_mb = await asyncio.wait_for(sc.rss_mb(), timeout=2.0)
            except Exception:  # noqa: BLE001 — RSS is diagnostic; never fail the probe
                rss_mb = None
        return {
            # Only unfinished battles — finished sessions stay in gateway.sessions
            # so /battle/{id}/state can return the ended receipt, so len(sessions)
            # would grow monotonically and over-report live load (PR #240 review).
            "active_battles": sum(1 for s in gateway.sessions.values() if s.ended is None),
            "registered_agents": len(gateway._registered),
            "cap_503_total": gateway.cap_503_total,
            "sidecar_spawned": sc is not None,
            "sidecar_pool_size": getattr(sc, "size", 1) if sc is not None else 0,
            "sidecar_rss_mb": rss_mb,
        }

    @app.get("/ladder")
    async def ladder() -> dict:
        return gateway.ladder_public()

    @app.get("/enrollment", response_model=None)
    async def enrollment_doc():
        from fastapi.responses import PlainTextResponse

        doc = Path(__file__).resolve().parent / "ENROLLMENT.md"
        return PlainTextResponse(doc.read_text(), media_type="text/markdown")

    @app.get("/methodology", response_model=None)
    async def methodology_doc():
        from fastapi.responses import PlainTextResponse

        doc = Path(__file__).resolve().parent / "METHODOLOGY.md"
        return PlainTextResponse(doc.read_text(), media_type="text/markdown")

    @app.get("/skill.md", response_model=None)
    async def skill_doc():
        from fastapi.responses import PlainTextResponse

        doc = Path(__file__).resolve().parent / "SKILL.md"
        return PlainTextResponse(doc.read_text(), media_type="text/markdown")

    @app.get("/whoami")
    async def whoami(authorization: str | None = Header(default=None)) -> dict:
        """Live-token probe: verifies the bearer is signed + not expired + not revoked,
        returns a safe summary of the claims for SKILL.md Layer 1.1 recovery."""
        if not authorization or not authorization.startswith("Bearer "):
            raise _opaque_error(401, "Bearer token required")
        token = authorization[len("Bearer ") :]
        try:
            claims = gateway.authority.verify(token, scope="battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        return {
            "agent_name": claims.agent_name,
            "owner": claims.owner,
            "scopes": list(claims.scopes),
            "issued_at": claims.issued_at,
            "expires_at": claims.expires_at,
            "expires_in_sec": max(0, int(claims.expires_at - gateway.now())),
        }

    # ---------- admin (operator-only; NOT documented in SKILL.md) ----------
    #
    # The admin surface lives behind X-Admin-Token (SHA-256-hashed env var) and
    # is intentionally absent from /skill.md, /enrollment, /methodology. Agent
    # clients are untrusted-by-default; admin surfaces stay in operator docs
    # only (docs/runbooks/membership-admin.md, ships 11b.5).

    def _check_admin(
        x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    ) -> str:
        """FastAPI dependency: verifies the admin header BEFORE the route body
        runs. Returns the opaque actor_hash (first 8 hex of the stored hash)
        for audit. Uniform _opaque_error(403, ...) on every failure mode.

        Note: FastAPI dependencies on path-operation params don't enforce
        ordering vs body parsing — a route declared as ``async def f(req:
        Model, _=Depends(_check_admin))`` will Pydantic-parse the body BEFORE
        calling _check_admin, leaking a 422 ``json_invalid`` / schema error
        to an unauthed probe (PASS 25). The /admin/grant-membership route
        below therefore takes a raw ``Request`` and parses the body manually
        AFTER the admin dependency runs."""
        if gateway.admin is None:
            raise _opaque_error(403, "admin not configured")
        try:
            return gateway.admin.verify_bearer(x_admin_token)
        except AdminAuthError as e:
            log.warning("admin auth rejected: %s", e)
            raise _opaque_error(403, e) from None

    @app.post("/admin/grant-membership", include_in_schema=False)
    async def grant_membership(
        request: Request,
        actor_hash: str = Depends(_check_admin),
    ) -> dict:
        """Grant a per-owner monthly membership (ADR-0011 11b). V1 manual
        flip-the-bit; Stripe deferred to V2. Last-write-wins on owner so this
        endpoint is idempotent on intent; revocation is a grant with
        valid_until_epoch <= now (single code path; audit trail preserved).

        ADR-0011 11b.3 anti-enumeration posture:
          - ``include_in_schema=False`` keeps the route OUT of OpenAPI / Swagger
            so an unauthed agent client cannot enumerate the admin surface
            (PASS 24). Operators discover the route via
            docs/runbooks/membership-admin.md, not /docs.
          - Auth runs BEFORE body parsing. The body is read with
            ``await request.json()`` and validated AFTER ``_check_admin``
            succeeds, so a malformed JSON body sent by an unauthed probe
            returns 403 (uniform admin posture) instead of 422 with
            ``json_invalid`` schema info (PASS 25).
        """
        # Body parse runs AFTER the _check_admin Depends — a malformed body
        # from an unauthed probe never reaches this point (PASS 25).
        try:
            body = await request.json()
        except Exception as e:  # noqa: BLE001 — opaque boundary
            raise _opaque_error(422, f"invalid JSON body: {e!r}") from None
        try:
            req = GrantMembershipRequest.model_validate(body)
        except Exception as e:  # noqa: BLE001 — opaque boundary; pydantic raises ValidationError
            raise _opaque_error(422, e) from None
        # Upper-bound check using gateway clock (field validator can't see it).
        now = gateway.now()
        if req.valid_until_epoch > now + MAX_GRANT_HORIZON_SEC:
            raise _opaque_error(
                422,
                f"valid_until_epoch exceeds {MAX_GRANT_HORIZON_SEC // 86400}-day horizon",
            )
        # Write-ahead the event, THEN mutate authority.memberships. Replay on
        # restart will hit the event and re-establish state via the same code
        # path as live grant_membership (consistency-by-construction).
        owner_key = gateway.authority.grant_membership(req.owner, req.valid_until_epoch)
        gateway.events.append(
            "membership_grant",
            {
                "tenant_id": owner_key,
                "owner": owner_key,
                "actor_hash": actor_hash,
                "valid_until_epoch": req.valid_until_epoch,
                "granted_at": now,
            },
        )
        return {"ok": True, "owner": owner_key, "valid_until_epoch": req.valid_until_epoch}

    @app.post("/admin/mint-invites", include_in_schema=False)
    async def mint_invites(
        request: Request,
        actor_hash: str = Depends(_check_admin),
    ) -> dict:
        """Operator-only (GA-CORE-1): mint N single-use invite codes for the beta.
        Same anti-enumeration posture as /admin/grant-membership — out of OpenAPI,
        auth BEFORE body parse (a malformed body from an unauthed probe gets 403,
        not 422). Returns the plaintext codes ONCE for the operator to distribute;
        they are not retrievable again (only their redemption state is)."""
        try:
            body = await request.json()
        except Exception as e:  # noqa: BLE001 — opaque boundary
            raise _opaque_error(422, f"invalid JSON body: {e!r}") from None
        try:
            req = MintInvitesRequest.model_validate(body)
        except Exception as e:  # noqa: BLE001 — opaque boundary
            raise _opaque_error(422, e) from None
        codes = gateway.mint_invites(req.count, actor_hash=actor_hash)
        return {"ok": True, "count": len(codes), "codes": codes, "stats": gateway.invites.stats()}

    @app.post("/enroll/request")
    async def enroll_request(req: EnrollRequest) -> dict:
        try:
            return gateway.enroll_request(req)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — opaque boundary
            raise _opaque_error(400, e) from None

    @app.post("/enroll/confirm/{code}")
    async def enroll_confirm(code: str) -> dict:
        return gateway.enroll_confirm(code)

    # ---------- account onboarding: GitHub device-flow (ADR-0013 D2) ----------
    #
    # `adx login` calls /auth/device/start, prints the user_code, then polls
    # /auth/device/poll until the human authorizes at github.com. On success the
    # arena mints a SESSION token (the human login, keyed by verified email) and
    # records the github_id<->owner link. Both endpoints 503 when session auth /
    # the GitHub OAuth app are unconfigured (optional-at-boot, like /badge/mint).
    # The broker is synchronous (network I/O) so it runs in a worker thread to
    # avoid blocking the event loop, mirroring the judge SDK off-loop pattern.

    @app.post("/auth/device/start")
    async def auth_device_start() -> dict:
        if gateway.device_flow is None:
            raise _opaque_error(503, "session auth not configured")
        try:
            start = await asyncio.to_thread(gateway.device_flow.start)
        except DeviceFlowError as e:
            raise _opaque_error(502, e) from None
        return start.to_public()

    @app.post("/auth/device/poll")
    async def auth_device_poll(req: DevicePollRequest) -> dict:
        if gateway.device_flow is None or gateway.session_auth is None:
            raise _opaque_error(503, "session auth not configured")
        try:
            result = await asyncio.to_thread(gateway.device_flow.poll, req.device_code)
        except DeviceFlowError as e:
            raise _opaque_error(502, e) from None
        if result.status == "authorized":
            # result.owner / result.github_id are non-None on the authorized
            # branch (the broker only returns authorized with both resolved).
            owner = result.owner or ""
            github_id = result.github_id or ""
            # Durable link BEFORE handing out the session, so a returning login
            # resolves to the same verified email across restarts (Class-A
            # write-then-publish: append, then mutate, then return).
            gateway.events.append("account_link", {"github_id": github_id, "owner": owner})
            gateway.accounts.link(github_id, owner)
            token = gateway.session_auth.mint_session(owner, github_id)
            claims = gateway.session_auth.verify_session(token)
            return {
                "session_token": token,
                "owner": claims.owner,
                "expires_at": claims.expires_at,
            }
        # pending / denied / expired — all 200 so the CLI switches on the field,
        # never on a status code (keeps the frozen pending→success shape intact).
        return {"status": result.status}

    @app.post("/enroll/account")
    async def enroll_account(
        req: EnrollAccountRequest, authorization: str | None = Header(default=None)
    ) -> dict:
        """Account-authed enroll (ADR-0013 D3): a logged-in human mints a
        per-agent consent token using the session token as proof (no email-OOB
        code). 503 when session auth is unconfigured; 401/403 on a missing/bad
        session; otherwise the same consent token the email-OOB path returns."""
        if gateway.session_auth is None:
            raise _opaque_error(503, "session auth not configured")
        if not authorization or not authorization.startswith("Bearer "):
            raise _opaque_error(401, "Bearer session token required")
        token = authorization[len("Bearer ") :]
        try:
            claims = gateway.session_auth.verify_session(token)
        except SessionError as e:
            raise _opaque_error(403, e) from None
        try:
            return gateway.enroll_account(claims, req.agent_name, req.agent_pubkey_hex)
        except HTTPException:
            raise
        except PermissionError as e:  # GA-CORE-1 beta gate: not invited
            raise _opaque_error(403, e) from None
        except Exception as e:  # noqa: BLE001 — opaque boundary
            raise _opaque_error(400, e) from None

    @app.post("/enroll/redeem-invite")
    async def redeem_invite(
        req: RedeemInviteRequest, authorization: str | None = Header(default=None)
    ) -> dict:
        """Session-authed (GA-CORE-1): a logged-in human redeems an invite code to
        join the beta. 503 when session auth is unconfigured; 401/403 on a
        missing/bad session; 403 (opaque) on an invalid/used code. Idempotent for an
        already-admitted owner (no code burned). The owner is the session's verified
        email — never client-supplied."""
        if gateway.session_auth is None:
            raise _opaque_error(503, "session auth not configured")
        if not authorization or not authorization.startswith("Bearer "):
            raise _opaque_error(401, "Bearer session token required")
        token = authorization[len("Bearer ") :]
        try:
            claims = gateway.session_auth.verify_session(token)
        except SessionError as e:
            raise _opaque_error(403, e) from None
        try:
            return gateway.redeem_invite(claims, req.invite_code)
        except InviteError as e:
            raise _opaque_error(403, e) from None

    @app.get("/account/quota")
    async def account_quota(authorization: str | None = Header(default=None)) -> dict:
        """Session-authed, read-only quota dashboard for `adx status` (ADR-0013
        D6): owner-pooled battle + per-agent evolve/badge_mint for today. 503 when
        session auth is unconfigured; 401/403 on a missing/bad session. Never
        debits, never feeds ladder recompute (anti-pay-to-rank unaffected)."""
        if gateway.session_auth is None:
            raise _opaque_error(503, "session auth not configured")
        if not authorization or not authorization.startswith("Bearer "):
            raise _opaque_error(401, "Bearer session token required")
        token = authorization[len("Bearer ") :]
        try:
            claims = gateway.session_auth.verify_session(token)
        except SessionError as e:
            raise _opaque_error(403, e) from None
        return gateway.account_quota(claims)

    @app.post("/team/draft")
    async def team_draft(body: dict) -> dict:
        """#2 authoring loop: stateless pack+validate against the pinned banlist.

        The visitor iterates export → per-slot errors → fix → revalidate until
        legal, then passes the packed team to /battle/begin (which re-validates —
        the gate, not this helper, is the enforcement). Errors are the server-side
        validator's own strings, never opponent-authored text (A6)."""
        try:
            gateway.authority.verify(str(body.get("token", "")), scope="battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        export = str(body.get("export", ""))[:20_000]
        packed = str(body.get("packed", ""))[:8_000]
        if not export and not packed:
            raise _opaque_error(422, "provide 'export' (showdown export text) or 'packed'")
        try:
            sidecar = await _sidecar()
            if export:
                packed = await pack_team(sidecar, export)
            valid, errors = await validate_team(sidecar, packed)
            return {"packed": packed, "valid": valid, "errors": errors}
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — opaque boundary
            raise _opaque_error(400, e) from None

    @app.post("/battle/start")
    async def battle_start(body: dict) -> dict:
        return gateway.battle_start(str(body.get("token", "")))

    @app.post("/battle/begin")
    async def battle_begin(req: BeginRequest) -> dict:
        try:
            return await gateway.battle_begin(req, sidecar=await _sidecar())
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise _opaque_error(400, e) from None

    @app.get("/battle/{battle_id}/state")
    async def battle_state(
        battle_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict:
        """Poll current battle state without choosing — re-renders from
        session.last_state. Mirrors the MCP get_battle_state tool so MCP-less
        clients can also observe mid-battle (closes the kit's proxy show_state gap).

        Auth: bearer token via Authorization header — NEVER as a query-string
        parameter (PR #93 review P2: query-string tokens leak into access logs,
        caches, browser history, and proxied diagnostics)."""
        # Belt-and-suspenders (PR #97 review P2): reject `?token=...` even
        # when a valid Authorization header is also present. Otherwise a
        # buggy client that sends BOTH still leaks the bearer into URL logs
        # while the request succeeds, silently masking the defect.
        if "token" in request.query_params:
            raise _opaque_error(
                400,
                "token query parameter is forbidden — pass via Authorization: Bearer header only",
            )
        if not authorization or not authorization.startswith("Bearer "):
            raise _opaque_error(401, "Bearer token required")
        token = authorization[len("Bearer ") :]
        gw = gateway
        # Auth BEFORE existence (D7 anti-enumeration): verify the token first so
        # an unauthenticated prober can never tell a live battle_id (would-be
        # 403) from an unknown one (would-be 404) — a bad token is 403 either
        # way. Then collapse "no such session" and "not your session" into the
        # SAME opaque 403 so a *valid*-token holder can't enumerate other
        # visitors' live battles by status code either. Live sessions aren't
        # public (unlike finished /replay), so this channel is real.
        try:
            claims = gw.authority.verify(token, scope="battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        session = gw.sessions.get(battle_id)
        if session is None:
            # HTTP pollers are explicitly supported to call /state before choosing;
            # after a restart give THIS owner the same 409 'interrupted' signal the
            # choose route gives, not an opaque 403 (others still 403, D7) (PR #246).
            if gw._interrupted.get(battle_id) == claims.token_id:
                raise HTTPException(status_code=409, detail=INTERRUPTED_RESTART_MSG) from None
            raise _opaque_error(403, "no such battle for this token") from None
        if claims.token_id != session.claims_token_id:
            raise _opaque_error(403, "no such battle for this token") from None
        # Mirror the choose/start path — expire stale sessions BEFORE returning
        # the state. Otherwise HTTP-only pollers see a live `your_move` payload
        # for a battle that should already be forfeited (PR #93 review P2).
        await gw._expire_if_stale(session)
        if session.ended is not None:
            return {"status": "ended", **session.ended}
        if session.pending is None or session.last_state is None:
            raise _opaque_error(409, "no pending state (battle not yet stepped)")
        return gw._render(session, session.last_state)

    @app.post("/battle/{battle_id}/choose")
    async def battle_choose(battle_id: str, req: ChooseRequest) -> dict:
        gw = gateway
        # Auth before existence + opaque not-found/not-yours collapse — see
        # battle_state (D7 anti-enumeration).
        try:
            claims = gw.authority.verify(req.token, scope="battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        session = gw.sessions.get(battle_id)
        if session is None:
            # In-memory sessions are wiped on restart. If THIS owner had begun this
            # battle in a prior process and it never ended, say so clearly (409)
            # instead of the opaque 403 — others still get 403 (D7 anti-enumeration).
            if gw._interrupted.get(battle_id) == claims.token_id:
                raise HTTPException(status_code=409, detail=INTERRUPTED_RESTART_MSG) from None
            raise _opaque_error(403, "no such battle for this token") from None
        if claims.token_id != session.claims_token_id:
            raise _opaque_error(403, "no such battle for this token") from None
        await gw._expire_if_stale(session)
        if session.ended is not None:
            return {"status": "ended", **session.ended}
        if session.pending is None:
            raise _opaque_error(409, "no pending request")
        choices = legal_choices(session.pending)
        if not 1 <= req.choice_index <= len(choices):
            raise _opaque_error(422, f"choice index out of range 1..{len(choices)}")
        choice = choices[req.choice_index - 1]
        session.visitor_choices.append(choice)
        label = _choice_label(choice, session.pending)
        recent_line = f"T{session.turns}: you → {label}"
        old_recent = list(session.recent)
        _push_recent(session, recent_line)
        old_pending = session.pending
        session.pending = None
        success = False
        try:
            sidecar = await _sidecar()
            resp = await sidecar.request(
                "step", battle=battle_id, choices={session.visitor_side: choice}
            )
            success = True
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise _opaque_error(400, e) from None
        finally:
            if not success:
                if len(session.visitor_choices) > 0:
                    session.visitor_choices.pop()
                session.recent = old_recent
                session.pending = old_pending

        # Class A (atomicity): the move executed above, so its audit row MUST be
        # durable before we advance/return — shared fail-closed append stops the
        # sidecar + marks the session ended-fatal + 500s if the write throws.
        await gw._append_or_fail_closed(
            "battle",
            {
                "tenant_id": session.claims_token_id,
                "battle_id": battle_id,
                "turn": session.turns,
                "choice": choice,
                "choice_label": label,
                "foe_hp_pct": session.foe_hp_pct if session.foe_species else None,
            },
            sidecar=sidecar,
            battle_id=battle_id,
            session=session,
        )
        session.pending = None
        session.last_touch = gw.now()
        try:
            return await gw._advance(session, resp["state"], visitor_choice=None)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise _opaque_error(400, e) from None

    @app.get("/replay/{battle_id}")
    async def replay(battle_id: str) -> dict:
        data = gateway.load_replay(battle_id)
        if data is None:
            raise _opaque_error(404, f"no replay {battle_id}")
        # Public view: omits the separate seed/teams/choices/tenant keys, but note
        # input_log is the FULL re-simulable Showdown log — it embeds the seed,
        # both packed teams, and every choice BY DESIGN (the outsider re-sim /
        # receipt guarantee; see ENROLLMENT.md "Replay publicity"). Only `tenant`
        # (the owning token_id) is truly server-side here; the rest is fork fuel
        # the server keeps as separate keys but is also derivable from input_log.
        res = {
            "input_log": data["input_log"],
            "winner": data["winner"],
            # Surface the opponent archetype (e.g. "gym-stall", "anchor-max_damage")
            # directly so an agent/human can diagnose a loss without re-parsing the
            # input_log. This leaks nothing new — input_log already embeds the
            # opponent's full team + every move; this is the same string the
            # sandbox /battle/begin discloses, just persisted on the receipt.
            "opponent": data.get("opponent"),
            "lane": data["lane"],
            "parent": data.get("parent"),
            "signatures": data.get("signatures") or [],
        }
        if "badge_awarded" in data:
            res["badge_awarded"] = data["badge_awarded"]
        return res

    @app.post("/battle/{battle_id}/fork")
    async def battle_fork(battle_id: str, body: dict) -> dict:
        """#6 remix-the-loss: branch a finished battle at turn N. SANDBOX ONLY —
        a rated log can never be forked (replay-derived rating laundering)."""
        try:
            claims = gateway.authority.verify(str(body.get("token", "")), scope="battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        data = gateway.load_replay(battle_id)
        # Collapse not-found and not-yours into one opaque 403 BEFORE any
        # battle-specific check (D7 anti-enumeration): a caller may only learn a
        # battle exists — or anything about it, e.g. its lane — if they own it.
        # (Ownership is checked first so a non-owner can't even probe the lane.)
        if data is None or data.get("tenant") != claims.token_id:
            raise _opaque_error(403, "fork denied: no such battle for this token") from None
        if data["lane"] != "sandbox":
            raise _opaque_error(403, "fork denied: sandbox battles only")
        turn = body.get("turn", 0)
        if not isinstance(turn, int) or not 0 <= turn <= 1000:
            raise _opaque_error(422, f"bad fork turn {turn!r}")
        try:
            return await gateway.battle_fork(
                battle_id, data, turn=turn, sidecar=await _sidecar(), owner=claims.owner
            )
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise _opaque_error(400, e) from None

    @app.post("/battle/{battle_id}/dispute")
    async def battle_dispute(battle_id: str, body: dict) -> dict:
        """Dispute a battle result. Re-runs the input log re-simulation.
        If the re-simulated winner does not match the reported winner,
        the battle is quarantined (rating quarantine) and marked as disputed.
        """
        try:
            claims = gateway.authority.verify(str(body.get("token", "")), scope="battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        data = gateway.load_replay(battle_id)
        # Collapse not-found and not-yours into one opaque 403 (D7
        # anti-enumeration): a caller may only learn a battle exists if they
        # own it.
        if data is None or claims.token_id != data.get("tenant"):
            raise _opaque_error(403, "dispute denied: no such battle for this token") from None

        # Idempotence (ADX-P1-006): this handler can 500 mid-flight (the resim /
        # sidecar can throw below) and be retried, and a battle can legitimately
        # be disputed more than once — so record the "dispute" (and any resulting
        # "quarantine") row AT MOST ONCE per battle. Without this guard each
        # retry appended another row, structurally duplicating the durable event
        # log. Disputes are rare so the O(events) scan is fine; resim itself is
        # deterministic and safe to repeat.
        #
        # Order matters (ADX-P1-006 residual): do NOT append the "dispute" row up
        # front. A failed audit — input log missing (404 below) or the resim
        # raising (500) — is not a durable dispute *outcome*; recording it before
        # the audit completes leaves a "dispute" row for work that never happened,
        # which a later retry then treats as already-logged and never re-audits.
        # The dispute (and any quarantine) are recorded ONLY after a successful
        # re-simulation, as one atomic group append.
        def _already_logged(event_type: str) -> bool:
            return any(
                ev.get("type") == event_type
                and (ev.get("payload") or {}).get("battle_id") == battle_id
                for ev in gateway.events.iter_events()
            )

        input_log = data.get("input_log")
        if not input_log:
            log_file = gateway.artifacts_dir / f"{battle_id}.inputlog.json"
            if log_file.is_file():
                try:
                    input_log = json.loads(log_file.read_text())
                except Exception:
                    pass
        if not input_log:
            raise _opaque_error(404, f"input log not found for {battle_id}")
        from adx_showdown.sim import replay_input_log

        try:
            sidecar = await _sidecar()
            res = await replay_input_log(
                sidecar, battle_id=f"{battle_id}-dispute", input_log=input_log
            )
            resim_winner = sanitize_name(res.winner)
            reported_winner = sanitize_name(data["winner"])
            match = resim_winner == reported_winner
            # Audit succeeded — now record the durable outcome. Build the group
            # under idempotence guards (a retry that already landed these rows
            # adds nothing) and land it as one atomic append so a dispute can
            # never be durably visible without its quarantine, or vice versa.
            event_items: list[tuple[str, dict[str, Any]]] = []
            if not _already_logged("dispute"):
                event_items.append(
                    (
                        "dispute",
                        {
                            "battle_id": battle_id,
                            "timestamp": gateway.now(),
                        },
                    )
                )
            if not match and not _already_logged("quarantine"):
                event_items.append(
                    (
                        "quarantine",
                        {
                            "battle_id": battle_id,
                            "reason": f"dispute successful: resim winner {resim_winner!r} != reported {reported_winner!r}",
                            "timestamp": gateway.now(),
                        },
                    )
                )
            if event_items:
                gateway.events.append_many(event_items)
            if not match:
                return {
                    "disputed": True,
                    "match": False,
                    "resim_winner": resim_winner,
                    "reported_winner": reported_winner,
                    "detail": "dispute successful: battle quarantined, ratings adjusted",
                }
            else:
                return {
                    "disputed": False,
                    "match": True,
                    "resim_winner": resim_winner,
                    "reported_winner": reported_winner,
                    "detail": "dispute rejected: re-simulation matches reported outcome",
                }
        except Exception as e:
            raise _opaque_error(500, f"re-simulation audit failed: {e!r}") from None

    @app.post("/my/events")
    async def my_events(body: dict) -> dict:
        """P4 client pull: a tenant's own chain rows, paged by chain seq — the
        feed `local_log.pull` materializes into ~/.adx/arena.sqlite.

        ADX-P1-002 (owner export completeness): the export now includes every
        chain row that belongs to this owner, not just rows with a top-level
        `tenant_id` match. Three cases:

          1. Top-level tenant_id match — battle_begin, battle_end, battle_fork,
             quarantine, badge (post-PR), membership_grant.
          2. `badge` events emitted before badge-tenant_id shipped — fall back
             to `agent_name == claims.agent_name` so a re-enrolled / pre-fix
             owner can still pull their own badge receipts (PASS 41).
          3. `period` events — top-level payload has no `tenant_id`, only a
             nested `events: [{battle_id, ...}, ...]` list. A period belongs to
             this owner if ANY nested rating_event's battle_id matches one of
             the owner's begin/end/fork rows. Two-pass scan: collect owned
             battle_ids in pass 1, filter rows in pass 2.

        The 1000-row cap is preserved.
        """
        try:
            claims = gateway.authority.verify(str(body.get("token", "")), scope="battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        since = body.get("since_seq", -1)
        if not isinstance(since, int):
            raise _opaque_error(422, "since_seq must be an int")

        # Pass 1: collect this owner's battle_ids by scanning top-level tenant_id
        # matches across the whole chain (cheap — chain rows are <1KB JSON each).
        owned_battle_ids: set[str] = set()
        for ev in gateway.events.iter_events():
            payload = ev.get("payload") or {}
            if payload.get("tenant_id") == claims.token_id:
                bid = payload.get("battle_id")
                if isinstance(bid, str):
                    owned_battle_ids.add(bid)

        def _belongs_to_owner(ev: dict[str, Any]) -> bool:
            payload = ev.get("payload") or {}
            # Case 1: top-level tenant_id match (the common path).
            if payload.get("tenant_id") == claims.token_id:
                return True
            etype = ev.get("type")
            # Case 2: legacy badge rows pre-PR (no tenant_id). Match by
            # agent_name — the agent_name → owner mapping is unforgeable
            # because `claims.agent_name` came from a verified consent token.
            if etype == "badge" and payload.get("agent_name") == claims.agent_name:
                return True
            # Case 3: period rows wrap rating_events that reference owned
            # battle_ids. The owner's rating delta is "their" period even
            # though the row itself has no tenant_id.
            if etype == "period":
                for nested in payload.get("events") or []:
                    nested_bid = nested.get("battle_id") if isinstance(nested, dict) else None
                    if isinstance(nested_bid, str) and nested_bid in owned_battle_ids:
                        return True
            return False

        # Pass 2: page the actual response by chain seq (post-`since`).
        rows: list[dict[str, Any]] = []
        for ev in gateway.events.iter_events():
            if ev["seq"] <= since:
                continue
            if _belongs_to_owner(ev):
                rows.append(ev)
                if len(rows) >= 1000:
                    break
        return {"events": rows, "next_since_seq": rows[-1]["seq"] if rows else since}

    @app.post("/badge/mint")
    async def badge_mint(body: dict) -> dict:
        """Mint a signed badge_token for the caller's agent (ADR-0011 11c.2,
        first paid feature). Class B (quota spend-after-success): verify +
        membership gate run up front (no slot spent on auth/membership 403),
        then sign_badge runs, and only AFTER the signer succeeds do we spend
        the daily mint slot. A 503 BadgeAuthError from sign_badge (signer
        outage) therefore never burns a quota slot.

        The SVG-render endpoint (`GET /badge/{agent}/{badge_token}.svg`) ships
        in 11c.3; this PR only stands up the mint surface so an owner can
        precompute a signed badge URL and paste it into their README.
        """
        if gateway.badge_auth is None:
            raise _opaque_error(503, "badge mint not configured")
        try:
            claims = gateway.authority.verify(str(body.get("token", "")), scope="badge_mint")
            gateway.authority.verify_membership(claims)
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        signed_at = gateway.now()
        valid_until = signed_at + BADGE_TOKEN_TTL_SEC
        try:
            badge_token = gateway.badge_auth.sign_badge(
                {
                    "agent_name": claims.agent_name,
                    "signed_at": signed_at,
                    "valid_until": valid_until,
                    "kid": "badge-v1",
                }
            )
        except BadgeAuthError as e:
            raise _opaque_error(503, e) from None
        try:
            _, spent_key = gateway.authority.spend_quota(claims, scope="badge_mint")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        # Durable so the daily mint cap survives a restart (ADX-P2-004).
        gateway._record_quota_spend(spent_key)
        # URL-encode the agent_name in the path so unicode / spaces /
        # gateway-reserved chars survive the README-paste-and-render
        # round-trip (PR #130 review #3410920009). `safe=''` URL-encodes
        # the slash too — agent_name comes from a validated single-segment
        # path param so this is shape-correct.
        agent_path = _url_quote(claims.agent_name, safe="")
        svg_path = f"/badge/{agent_path}/{badge_token}.svg"
        verify_path = f"/badge/{agent_path}/{badge_token}/verify"
        return {
            "badge_token": badge_token,
            "svg_url": f"{gateway.public_base_url}{svg_path}"
            if gateway.public_base_url
            else svg_path,
            "verify_url": f"{gateway.public_base_url}{verify_path}"
            if gateway.public_base_url
            else verify_path,
            "valid_until_epoch": valid_until,
        }

    def _resolve_badge(agent_name: str, badge_token: str) -> tuple[dict, dict]:
        """Shared anti-substitution + expiry + ladder-lookup path for both
        the SVG and verify endpoints. Returns (payload, ladder_entry) on
        success; raises 503 if badge_auth is missing, 404 (opaque) on every
        verify failure mode (bad sig, mismatched name, expired, unknown
        agent). 404 keeps the surface unreadable per spec D7 anti-
        enumeration posture."""
        if gateway.badge_auth is None:
            raise _opaque_error(503, "badge mint not configured")
        try:
            payload = gateway.badge_auth.verify_badge(badge_token)
        except BadgeAuthError as e:
            raise _opaque_error(404, e) from None
        if payload.get("agent_name") != agent_name:
            raise _opaque_error(404, "badge agent_name mismatch")
        valid_until = payload.get("valid_until")
        if not isinstance(valid_until, int | float) or gateway.now() > valid_until:
            raise _opaque_error(404, "badge expired")
        ladder = gateway.ladder_public()
        entry = ladder.get("entrants", {}).get(agent_name)
        if entry is None:
            raise _opaque_error(404, "agent not on ladder")
        return payload, entry

    @app.get("/badge/{agent_name}/{badge_token}.svg", response_model=None)
    async def badge_svg(agent_name: str, badge_token: str, request: Request):
        """Public SVG render of the signed badge. NO consent token, no
        membership lookup — the badge_token signature IS the auth. The SVG
        renders from /ladder data so the §3 anti-pay-to-rank invariant
        carries through (any rating tampering inside this endpoint would
        diverge from the ladder + fail the Q5 property test in 11c.4)."""
        from fastapi.responses import Response

        payload, entry = _resolve_badge(agent_name, badge_token)
        verify_url = f"/badge/{agent_name}/{badge_token}/verify"
        svg = _render_badge_svg(
            agent_name=agent_name,
            rating=float(entry["rating"]),
            rd=float(entry["rd"]),
            verify_url=verify_url,
        )
        # Q2 funnel instrumentation (per spec §270) — Referer host-only.
        # PR #132 review #3411007728 mandated structured fields because
        # agent_name MAY contain a space (sanitize_name allows it). PR
        # #139 emitted the fields ONLY via `extra={...}`, but the deployed
        # path (`Dockerfile` runs `python -m agentdex_arena`, and
        # __main__.main()'s logging.basicConfig formatter is
        # `%(asctime)s %(levelname)s %(name)s %(message)s` — does NOT
        # include extras). On Koyeb / Datadog / Loki that read stdout,
        # the deployed line collapsed to bare `badge_fetch` and the
        # values were lost entirely (PR #139 review #3411197007).
        # Restore the values to the message via a sort-keyed canonical-
        # JSON serialization. JSON quoting closes the space-in-agent-name
        # parse hole the previous `agent=%s ...` line had (a parser can
        # safely `json.loads(message.split(" ", 1)[1])`). The `extra={...}`
        # keyword is kept so structured handlers (JSON ingester, Datadog
        # parser) still get typed LogRecord attributes — no regression
        # against the V2 aggregation contract.
        _bf_fields = {
            "event": "badge_fetch",
            "agent_name": agent_name,
            "referer_host": _badge_referer_host(request.headers.get("Referer")),
            "badge_token_kid": payload.get("kid"),
        }
        log.info(
            "badge_fetch %s",
            json.dumps(_bf_fields, sort_keys=True),
            extra=_bf_fields,
        )
        return Response(
            content=svg,
            media_type="image/svg+xml",
            headers={"Cache-Control": f"public, max-age={BADGE_SVG_CACHE_SEC}"},
        )

    @app.get("/badge/{agent_name}/{badge_token}/verify")
    async def badge_verify(agent_name: str, badge_token: str) -> dict:
        """Public JSON verifier endpoint per spec D7. Returns the badge
        payload plus the LIVE ladder values so a third-party verifier can:
        (1) re-derive + verify the signature, (2) cross-check against
        /ladder for the "SVG lies about your rating" attack, (3) compare
        rendered SVG values to the JSON for renderer-cheats."""
        if gateway.badge_auth is None:
            raise _opaque_error(503, "badge mint not configured")
        payload, entry = _resolve_badge(agent_name, badge_token)
        return {
            "agent_name": agent_name,
            "rating": entry["rating"],
            "rd": entry["rd"],
            "games": entry["games"],
            "signed_at_epoch": payload["signed_at"],
            "valid_until_epoch": payload["valid_until"],
            "badge_public_key_hex": gateway.badge_auth.public_key_hex,
            "kid": payload.get("kid"),
            "ladder_url": BADGE_LADDER_URL,
            "issuer": BADGE_ISSUER,
        }

    @app.post("/evolution/request")
    async def evolution_request(body: dict) -> dict:
        from agentdex_arena.offered_seeds import offer_seeds

        try:
            claims = gateway.authority.verify(str(body.get("token", "")), scope="evolve")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        # Fast-fail: if the daily evolve cap is already hit, reject before
        # spinning up sidecar work (offer_seeds is expensive). check_quota is
        # read-only — the authoritative spend_quota debit still follows after
        # offer_seeds returns so a sidecar failure inside offer_seeds cannot
        # burn a slot (Class B spend-after-success is preserved).
        try:
            gateway.authority.check_quota(claims, scope="evolve")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        try:
            result = await offer_seeds(
                await _sidecar(),
                current_team=str(body.get("team", "")) or None,
                reasoning=sanitize_name(str(body.get("reasoning", "")), max_len=200),
            )
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            raise _opaque_error(400, e) from None
        # Class B (quota spend-after-success): spend the evolve slot AFTER
        # offer_seeds returns. A sidecar / infra failure inside offer_seeds
        # raised above and exited via the 400 path — no slot was burned.
        try:
            _, spent_key = gateway.authority.spend_quota(claims, scope="evolve")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        # Durable so the daily evolve cap survives a restart (ADX-P2-004).
        gateway._record_quota_spend(spent_key)
        return result

    from agentdex_arena.mcp_surface import init_mcp, mcp

    mcp._session_manager = None
    mcp_app = mcp.streamable_http_app()
    app.state.mcp_session_manager = mcp._session_manager
    init_mcp(gateway, _sidecar)
    app.mount("/mcp", mcp_app)

    # BENE landing + docs (static). Mounted only when the site/ tree was bundled
    # into the image — preserves local-dev runs that don't ship the site files.
    _bene_site = Path("site")
    if _bene_site.is_dir():
        # Bare /bene -> /bene/ with a ROOT-RELATIVE redirect. StaticFiles' own
        # auto slash-redirect builds an ABSOLUTE URL from the request host, which
        # behind the AI-Builders reverse proxy is the internal Koyeb host
        # (http://ai-builders-*.koyeb.app) — that host 404s, so the bare /bene URL
        # was broken for users. A root-relative Location lets the browser resolve
        # it against the public host (agentdex.ai-builders.space).
        from fastapi.responses import RedirectResponse

        @app.get("/bene", include_in_schema=False)
        async def _bene_trailing_slash() -> RedirectResponse:
            return RedirectResponse(url="/bene/", status_code=308)

        app.mount("/bene", StaticFiles(directory=str(_bene_site), html=True), name="bene")

    return app


def _format_log_line(line: str, visitor_side: str) -> str | None:
    if not line.startswith("|"):
        return None
    parts = line.split("|")
    if len(parts) < 2:
        return None
    op = parts[1]

    def clean_name(pokemon_str: str) -> str:
        side = pokemon_str[:2]
        name = pokemon_str.split(": ")[-1]
        if side in ("p1", "p2"):
            if side != visitor_side:
                return f"foe {name}"
        return name

    if op == "move":
        attacker = clean_name(parts[2])
        move = parts[3]
        if len(parts) >= 5 and parts[4]:
            target = clean_name(parts[4])
            return f"{attacker} used {move} (vs {target})"
        return f"{attacker} used {move}"
    elif op in ("switch", "drag"):
        pokemon = clean_name(parts[2])
        hp_str = parts[4].split(" ")[0] if len(parts) >= 5 else "100/100"
        return f"{pokemon} switched in ({hp_str})"
    elif op == "faint":
        pokemon = clean_name(parts[2])
        return f"{pokemon} fainted"
    elif op == "-supereffective":
        pokemon = clean_name(parts[2])
        return f"It's super effective on {pokemon}!"
    elif op == "-resisted":
        pokemon = clean_name(parts[2])
        return f"It's not very effective on {pokemon}."
    elif op == "-crit":
        pokemon = clean_name(parts[2])
        return f"A critical hit on {pokemon}!"
    elif op == "-immune":
        pokemon = clean_name(parts[2])
        return f"It doesn't affect {pokemon}."
    elif op == "-damage":
        pokemon = clean_name(parts[2])
        hp_str = parts[3].split(" ")[0] if len(parts) >= 4 else ""
        from_str = ""
        for p in parts[4:]:
            if p.startswith("[from]"):
                from_str = f" ({p[6:].strip()})"
                break
        return f"{pokemon} was damaged to {hp_str}{from_str}"
    elif op == "-heal":
        pokemon = clean_name(parts[2])
        hp_str = parts[3].split(" ")[0] if len(parts) >= 4 else ""
        from_str = ""
        for p in parts[4:]:
            if p.startswith("[from]"):
                from_str = f" ({p[6:].strip()})"
                break
        return f"{pokemon} was healed to {hp_str}{from_str}"
    elif op == "-status":
        pokemon = clean_name(parts[2])
        status = parts[3]
        return f"{pokemon} was inflicted with status {status}"
    elif op == "cant":
        pokemon = clean_name(parts[2])
        reason = parts[3] if len(parts) >= 4 else ""
        if reason:
            return f"{pokemon} can't move: {reason}"
        return f"{pokemon} can't move"
    elif op in ("detailschange", "-formechange"):
        pokemon = clean_name(parts[2])
        new_details = parts[3].split(",")[0]
        return f"{pokemon} changed form to {new_details}"

    return None
