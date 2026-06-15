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

import hashlib
import json
import logging
import math
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

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
from adx_showdown.protocol import ParsedRequest, legal_choices, parse_request, sanitize_name
from adx_showdown.sidecar import Sidecar, SidecarError
from adx_showdown.sim import BattleContext, call_policy
from adx_showdown.teams import pack_team, starter_pack, validate_team
from agentdex_engine.modules.arena import (
    EventLog,
    Ladder,
    RatingEvent,
    extract_signatures,
    recompute_ladder,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentdex_arena.admin_auth import AdminAuthError, AdminAuthority
from agentdex_arena.badge_auth import BadgeAuthError, BadgeAuthority
from agentdex_arena.consent import (
    ConsentAuthority,
    ConsentClaims,
    ConsentError,
    _normalize_owner,
)

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
    "gym-trick-room": "04-trick-room",
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
    recent: list[str] = field(default_factory=list)
    foe_species: str | None = None
    foe_hp_pct: int | None = None
    # Fork support (#6): the exact inputs needed to re-create this battle from
    # its seed and branch at a turn. parent=(battle_id, fork_turn) on forks.
    p1_team: str | None = None
    p2_team: str | None = None
    visitor_choices: list[str] = field(default_factory=list)
    parent: tuple[str, int] | None = None
    scratchpad: str = ""
    last_state: dict[str, Any] | None = None


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
    ) -> None:
        self.authority = authority
        # Admin bearer for operator-only routes (ADR-0011 11b.3). None means
        # admin endpoints respond 403 'admin not configured' at request time —
        # the production __main__ constructs AdminAuthority eagerly so the
        # container fail-closed-boots if ARENA_ADMIN_TOKEN_HASH is missing.
        self.admin = admin_authority
        # Badge signing authority for ADR-0011 11c (first paid feature). None
        # means /badge/mint responds 503 'badge mint not configured' — the
        # production __main__ constructs BadgeAuthority eagerly so the
        # container fail-closed-boots if ARENA_BADGE_SIGNING_KEY_HEX is missing.
        self.badge_auth = badge_authority
        self.events = EventLog(events_path, sync=event_sync)
        self._registered: set[str] = set()
        for event in self.events.iter_events():
            etype = event.get("type")
            payload = event.get("payload") or {}
            try:
                if etype == "register":
                    self._registered.add(payload["name"])
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

    def enroll_request(self, req: EnrollRequest) -> dict[str, Any]:
        code = secrets.token_urlsafe(16)
        agent_name = sanitize_name(req.agent_name) or "visitor"
        # Reject reserved names case-insensitively (anchor- prefix, visitor, foe, _house, _ladder) (P2 PR #56 comment follow-up)
        name_lower = agent_name.lower()
        if name_lower.startswith("anchor-") or name_lower in (
            "visitor",
            "foe",
            "_house",
            "_ladder",
        ):
            raise _opaque_error(400, "reserved agent name")
        # Reject duplicate names
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
        req = self.pending_enrollments.pop(code, None)
        if req is None:
            raise _opaque_error(404, "unknown/expired enrollment code")
        if req.agent_name in self._registered:
            raise _opaque_error(409, "agent name already registered")

        # Record confirmed names before issuing tokens (P2 PR #56 comment follow-up)
        self.events.append("register", {"name": req.agent_name, "frozen": False})
        self._registered.add(req.agent_name)

        claims = ConsentClaims(
            token_id=uuid.uuid4().hex[:16],
            owner=req.owner,
            agent_name=req.agent_name,
            agent_pubkey_hex=req.agent_pubkey_hex,
            scopes=["enroll", "battle", "evolve", "badge_mint"],
            issued_at=self.now(),
            expires_at=self.now() + 7 * 86_400,
            confirmed_via=f"web-confirm:{code[:6]}…",
        )
        return {"token": self.authority.mint(claims), "expires_at": claims.expires_at}

    # ---------- battle flow ----------

    def battle_start(self, token: str) -> dict[str, Any]:
        try:
            claims = self.authority.verify(token, scope="battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        nonce = secrets.token_hex(12)
        self.battle_nonces[nonce] = claims.token_id
        return {"battle_nonce": nonce, "pop_challenge": f"arena-pop:{claims.token_id}:{nonce}"}

    async def battle_begin(self, req: BeginRequest, *, sidecar: Sidecar) -> dict[str, Any]:
        try:
            claims = self.authority.verify(req.token, scope="battle")
            if self.battle_nonces.pop(req.battle_nonce, None) != claims.token_id:
                raise ConsentError("unknown battle nonce")
            self.authority.verify_pop(claims, req.battle_nonce, req.pop_signature_hex)
            if req.lane == "rated":
                self.authority.spend_quota(claims, scope="battle")
                if not self.publication_allowed:
                    raise ConsentError("rated lane paused: instrument self-test red")
        except ConsentError as e:
            raise _opaque_error(403, e) from None

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
            visitor_name=visitor,
            lane=req.lane,
            opponent=opponent,
            seed=seed,
            sidecar=sidecar,
            opponent_policy=_opponent_policy(opponent, sidecar, seed[0] + 13),
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
                raise HTTPException(
                    status_code=503,
                    detail="arena at capacity — finish or forfeit an active battle, then retry",
                ) from None
            raise
        self.sessions[battle_id] = session
        # Chain event (mirrors to Postgres write-behind). NO seed in the payload:
        # mirror rows are tenant-readable and the rated seed stays secret until
        # the post-result disclosure (A3).
        self.events.append(
            "battle_begin",
            {
                "tenant_id": claims.token_id,
                "battle_id": battle_id,
                "lane": req.lane,
                "visitor": visitor,
                "opponent": opponent,
            },
        )
        state = await self._advance(session, resp["state"], visitor_choice=None)
        out = {"battle_id": battle_id, "lane": req.lane, **state}
        if gym_team_name is not None:
            # Disclosed signature team (#3): scouting it and drafting a counter IS
            # the sandbox game; this is what makes team_mutation a real lever.
            out["opponent_team_name"] = gym_team_name
            out["opponent_team"] = opp_team
        return out

    async def _expire_if_stale(self, session: BattleSession) -> None:
        if session.ended is None and self.now() - session.last_touch > self.turn_budget_s:
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
                return await self._finish(session, state["end"])

            choices: dict[str, str] = {}
            if visitor_choice is not None:
                choices[session.visitor_side] = visitor_choice
                visitor_choice = None
            raw_opp = (state.get("pending") or {}).get(other)
            if raw_opp is not None:
                opp_req = parse_request(raw_opp)
                ctx = BattleContext(
                    side=other,
                    my_species=(state.get("active") or {}).get(other),
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
            my_species=(state.get("active") or {}).get(session.visitor_side),
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

    def _check_collusion(self, session: BattleSession) -> str | None:
        """Run collusion forensics heuristics: win-transfer, low-entropy choices, early forfeits."""
        turns = session.ended.get("turns", 0) if session.ended else 0
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
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        (self.artifacts_dir / f"{session.battle_id}.inputlog.json").write_text(
            json.dumps(input_log, indent=1) + "\n"
        )
        session.ended = {"winner": winner, "turns": int(end.get("turns", 0))}

        # Check collusion forensics
        collusion_reason = self._check_collusion(session)
        if collusion_reason:
            session.ended["quarantined"] = True
            session.ended["quarantine_reason"] = collusion_reason

        # Check if they earned a gym badge in sandbox
        badge_awarded = None
        if (
            session.lane == "sandbox"
            and session.opponent in GYM_BADGES
            and winner == session.visitor_name
        ):
            badge_name = GYM_BADGES[session.opponent]
            badge_awarded = badge_name
            self.events.append(
                "badge",
                {
                    "agent_name": session.visitor_name,
                    "badge": badge_name,
                    "battle_id": session.battle_id,
                    "timestamp": self.now(),
                },
            )

        signatures = [
            s.model_dump()
            for s in extract_signatures(list(end.get("keyLines") or []), side=session.visitor_side)
        ]
        receipt: dict[str, Any] = {
            "status": "ended",
            "battle_id": session.battle_id,
            "lane": session.lane,
            "winner": winner,
            "you_won": winner == session.visitor_name,
            "turns": session.ended["turns"],
            "failure_signatures": signatures,
            "replay": f"/replay/{session.battle_id}",
            "input_log_blake2b16": log_digest,
            "recent_turns": list(session.recent),
        }
        if collusion_reason:
            receipt["quarantined"] = True
            receipt["quarantine_reason"] = collusion_reason
        if badge_awarded:
            receipt["badge_awarded"] = badge_awarded

        self.events.append(
            "battle_end",
            {
                "tenant_id": session.claims_token_id,
                "battle_id": session.battle_id,
                "lane": session.lane,
                "winner": winner,
                "turns": session.ended["turns"],
                "input_log_blake2b16": log_digest,
            },
        )
        if collusion_reason:
            self.events.append(
                "quarantine",
                {
                    "battle_id": session.battle_id,
                    "reason": collusion_reason,
                    "timestamp": self.now(),
                },
            )
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
            "teams": [session.p1_team, session.p2_team],
            "visitor_choices": list(session.visitor_choices),
            "parent": session.parent,
            "signatures": signatures,
        }
        if badge_awarded:
            self.replays[session.battle_id]["badge_awarded"] = badge_awarded
        if session.lane == "rated" and len(input_log) > 0:
            for name in (session.visitor_name, session.opponent):
                if name not in self._registered:
                    self.events.append(
                        "register", {"name": name, "frozen": name.startswith("anchor-")}
                    )
                    self._registered.add(name)
            before = recompute_ladder(self.events.path).rating(session.visitor_name)
            self.events.append(
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
            after = recompute_ladder(self.events.path).rating(session.visitor_name)
            delta = Ladder.published_delta(before, after)
            receipt["rating"] = {
                "rating": round(after.rating, 1),
                "rd": round(after.rd, 1),
                "published_delta": round(delta, 1) if delta is not None else "INCONCLUSIVE",
                "seed_disclosure": session.seed,  # revealed post-result (A3)
                "opponent_team_disclosure": session.p2_team,  # i.i.d. team revealed post-result (#8)
            }
        session.ended = receipt
        return receipt

    # ---------- fork (#6 remix-the-loss, sandbox-only) ----------

    async def battle_fork(
        self, src_battle_id: str, src: dict[str, Any], *, turn: int, sidecar: Sidecar
    ) -> dict[str, Any]:
        """Branch a finished SANDBOX battle at `turn`: same seed, same teams, same
        fresh-seeded opponent policy; the visitor's recorded choices replay through
        the live step protocol up to the fork point, then control returns to the
        agent. Deterministic anchors make the same-choice suffix reproduce; the
        only free variable is the decision at the fork."""
        battle_id = f"sandbox-fork-{uuid.uuid4().hex[:8]}"
        session = BattleSession(
            battle_id=battle_id,
            claims_token_id=str(src["tenant"]),
            visitor_name=str(src["visitor"]),
            lane="sandbox",
            opponent=str(src["opponent"]),
            seed=list(src["seed"]),
            sidecar=sidecar,
            opponent_policy=_anchor_policy(str(src["opponent"]), sidecar, src["seed"][0] + 13),
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
        self.sessions[battle_id] = session
        state = await self._advance(session, resp["state"], visitor_choice=None)
        for ch in src.get("visitor_choices", []):
            if session.ended is not None or session.turns >= turn:
                break
            if session.pending is None:
                break
            session.pending = None
            step = await sidecar.request(
                "step", battle=battle_id, choices={session.visitor_side: ch}
            )
            state = await self._advance(session, step["state"], visitor_choice=None)
        self.events.append(
            "battle_fork",
            {
                "tenant_id": session.claims_token_id,
                "battle_id": battle_id,
                "parent_battle_id": src_battle_id,
                "fork_turn": turn,
            },
        )
        return {
            "battle_id": battle_id,
            "lane": "sandbox",
            "parent_battle_id": src_battle_id,
            "fork_turn": turn,
            **state,
        }

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


def create_app(gateway: ArenaGateway, *, sidecar_factory: Callable[[], Sidecar]) -> FastAPI:
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
        if app.state.sidecar is None:
            app.state.sidecar = sidecar_factory()
            await app.state.sidecar.start()
        return app.state.sidecar

    @app.get("/")
    async def health() -> dict:
        return {"ok": True, "service": "agentdex-arena", "lanes": ["sandbox", "rated"]}

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
        """FastAPI dependency: verifies the admin header BEFORE pydantic body
        parse so a malformed body cannot leak schema via 422 to an unauthed
        probe. Returns the opaque actor_hash (first 8 hex of the stored hash)
        for audit. Uniform _opaque_error(403, ...) on every failure mode."""
        if gateway.admin is None:
            raise _opaque_error(403, "admin not configured")
        try:
            return gateway.admin.verify_bearer(x_admin_token)
        except AdminAuthError as e:
            log.warning("admin auth rejected: %s", e)
            raise _opaque_error(403, e) from None

    @app.post("/admin/grant-membership")
    async def grant_membership(
        req: GrantMembershipRequest,
        actor_hash: str = Depends(_check_admin),
    ) -> dict:
        """Grant a per-owner monthly membership (ADR-0011 11b). V1 manual
        flip-the-bit; Stripe deferred to V2. Last-write-wins on owner so this
        endpoint is idempotent on intent; revocation is a grant with
        valid_until_epoch <= now (single code path; audit trail preserved)."""
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
        session = gw.sessions.get(battle_id)
        if session is None:
            raise _opaque_error(404, f"no session {battle_id}")
        try:
            claims = gw.authority.verify(token, scope="battle")
            if claims.token_id != session.claims_token_id:
                raise ConsentError("token does not own this battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
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
        session = gw.sessions.get(battle_id)
        if session is None:
            raise _opaque_error(404, f"no session {battle_id}")
        try:
            claims = gw.authority.verify(req.token, scope="battle")
            if claims.token_id != session.claims_token_id:
                raise ConsentError("token does not own this battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
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

        try:
            gw.events.append(
                "battle",
                {
                    "tenant_id": session.claims_token_id,
                    "battle_id": battle_id,
                    "turn": session.turns,
                    "choice": choice,
                    "choice_label": label,
                    "foe_hp_pct": session.foe_hp_pct if session.foe_species else None,
                },
            )
        except Exception as e:
            session.ended = {
                "winner": "",
                "turns": session.turns,
                "reason": f"fatal: event log write failed: {e!r}",
            }
            try:
                await sidecar.request("stop", battle=battle_id)
            except Exception:
                pass
            raise _opaque_error(500, f"event log write failed: {e!r}") from None
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
        data = gateway.replays.get(battle_id)
        if data is None:
            raise _opaque_error(404, f"no replay {battle_id}")
        # public view only — seed/teams/choices/tenant stay server-side (fork fuel)
        res = {
            "input_log": data["input_log"],
            "winner": data["winner"],
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
        data = gateway.replays.get(battle_id)
        if data is None:
            raise _opaque_error(404, f"no replay {battle_id}")
        if data["lane"] != "sandbox":
            raise _opaque_error(403, "fork denied: sandbox battles only")
        if data.get("tenant") != claims.token_id:
            raise _opaque_error(403, "fork denied: not your battle")
        turn = body.get("turn", 0)
        if not isinstance(turn, int) or not 0 <= turn <= 1000:
            raise _opaque_error(422, f"bad fork turn {turn!r}")
        try:
            return await gateway.battle_fork(battle_id, data, turn=turn, sidecar=await _sidecar())
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
        data = gateway.replays.get(battle_id)
        if data is None:
            raise _opaque_error(404, f"no replay {battle_id}")
        if claims.token_id != data.get("tenant"):
            raise _opaque_error(403, "Forbidden: token does not own this battle")
        gateway.events.append(
            "dispute",
            {
                "battle_id": battle_id,
                "timestamp": gateway.now(),
            },
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
            if not match:
                gateway.events.append(
                    "quarantine",
                    {
                        "battle_id": battle_id,
                        "reason": f"dispute successful: resim winner {resim_winner!r} != reported {reported_winner!r}",
                        "timestamp": gateway.now(),
                    },
                )
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
        """P4 client pull: a tenant's own chain rows (battle events only), paged by
        chain seq — the feed `local_log.pull` materializes into ~/.adx/arena.sqlite."""
        try:
            claims = gateway.authority.verify(str(body.get("token", "")), scope="battle")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        since = body.get("since_seq", -1)
        if not isinstance(since, int):
            raise _opaque_error(422, "since_seq must be an int")
        rows = []
        for ev in gateway.events.iter_events():
            if ev["seq"] <= since:
                continue
            payload = ev.get("payload") or {}
            if payload.get("tenant_id") != claims.token_id:
                continue
            rows.append(ev)
            if len(rows) >= 1000:
                break
        return {"events": rows, "next_since_seq": rows[-1]["seq"] if rows else since}

    @app.post("/badge/mint")
    async def badge_mint(body: dict) -> dict:
        """Mint a signed badge_token for the caller's agent (ADR-0011 11c.2,
        first paid feature). Call order locked in CLAUDE.md doctrine:
        verify(scope=badge_mint) → verify_membership → spend_quota → mint.

        The SVG-render endpoint (`GET /badge/{agent}/{badge_token}.svg`) ships
        in 11c.3; this PR only stands up the mint surface so an owner can
        precompute a signed badge URL and paste it into their README.
        """
        if gateway.badge_auth is None:
            raise _opaque_error(503, "badge mint not configured")
        try:
            claims = gateway.authority.verify(str(body.get("token", "")), scope="badge_mint")
            gateway.authority.verify_membership(claims)
            gateway.authority.spend_quota(claims, scope="badge_mint")
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
        return {
            "badge_token": badge_token,
            "svg_url": f"/badge/{claims.agent_name}/{badge_token}.svg",
            "verify_url": f"/badge/{claims.agent_name}/{badge_token}/verify",
            "valid_until_epoch": valid_until,
        }

    @app.post("/evolution/request")
    async def evolution_request(body: dict) -> dict:
        from agentdex_arena.offered_seeds import offer_seeds

        try:
            claims = gateway.authority.verify(str(body.get("token", "")), scope="evolve")
            gateway.authority.spend_quota(claims, scope="evolve")
        except ConsentError as e:
            raise _opaque_error(403, e) from None
        try:
            return await offer_seeds(
                await _sidecar(),
                current_team=str(body.get("team", "")) or None,
                reasoning=sanitize_name(str(body.get("reasoning", "")), max_len=200),
            )
        except Exception as e:  # noqa: BLE001
            raise _opaque_error(400, e) from None

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
