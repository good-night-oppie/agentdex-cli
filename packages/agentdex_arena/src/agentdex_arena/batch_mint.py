"""Batch-mint consent tokens for a CURATED launch — `python -m agentdex_arena.batch_mint`.

The self-serve `/enroll/request` → out-of-band code → `/enroll/confirm` flow is the
right path for anonymous users, but for a curated launch (hand N pre-configured
LLM agents a working token each) it is friction. This one-shot tool mints tokens
directly from a roster, replicating `gateway.enroll_confirm`'s exact contract:

  - it appends a durable ``register`` event per agent (same shape the gateway
    writes) so names are reserved and survive a restart, AND
  - it mints with the SAME ``ConsentAuthority`` (so the live gateway, which loads
    ``ARENA_SIGNING_KEY_HEX``, verifies the token), with the standard 7-day expiry
    and ``enroll/battle/evolve/badge_mint`` scopes.

Run it against the deploy's signing key + events log (the gateway reads the same
``ARENA_RUNTIME_DIR/events.jsonl`` on boot). Tokens are SECRETS: they are written
to an output file with ``0600`` perms and NEVER printed to stdout — only a
non-secret summary (agent name + owner + expiry) is shown.

Roster JSON: ``[{"owner": "...", "agent_name": "...", "agent_pubkey_hex": "<64 hex>"}]``
(the agent generates its own Ed25519 keypair and supplies the public half so
per-battle proof-of-possession works; the private key never touches this tool).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import re
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from adx_showdown.protocol import sanitize_name
from agentdex_engine.modules.arena import EventLog

from agentdex_arena.consent import ConsentAuthority, ConsentClaims

log = logging.getLogger("agentdex_arena.batch_mint")

# Mirror gateway.enroll_request's reserved-name guard so batch-minted names cannot
# collide with the arena's structural identities.
_RESERVED_EXACT = frozenset({"visitor", "foe", "_house", "_ladder"})
_TOKEN_TTL_SEC = 7 * 86_400
_DEFAULT_SCOPES = ["enroll", "battle", "evolve", "badge_mint"]

# Mirror the self-serve enrollment contract so the curated path can't mint
# tokens the live gateway would reject. EnrollRequest enforces a contact-shaped
# owner (3..120 chars, no placeholders/whitespace, an @ + a dotted domain) and
# a 64-hex Ed25519 pubkey (ConsentClaims.agent_pubkey_hex); validating both here
# — BEFORE the durable register — keeps a bad roster row from orphaning a name
# or producing a token that 500s inside rated /battle/begin (PR #232 review).
_PUBKEY_RE = re.compile(r"[0-9a-f]{64}")
_OWNER_MIN_LEN = 3
_OWNER_MAX_LEN = 120


class BatchMintError(ValueError):
    """A roster entry that cannot be minted (reserved/duplicate/invalid)."""


def _is_reserved(agent_name: str) -> bool:
    low = agent_name.lower()
    return low.startswith("anchor-") or low in _RESERVED_EXACT


def _validate_owner_like_enrollment(owner: str) -> None:
    """Reject owners the self-serve ``EnrollRequest`` intentionally rejects.

    Mirrors ``gateway.EnrollRequest._owner_is_a_contact`` + its length bounds:
    a placeholder like ``{OWNER}``, whitespace, a non-address, or an oversize
    value would otherwise mint a token that later fails inside rated
    ``/battle/begin`` or paid-feature gates when the owner is normalized outside
    the ``ConsentError`` path — an unusable token or a 500, not a caught bad row.
    """
    if not (_OWNER_MIN_LEN <= len(owner) <= _OWNER_MAX_LEN):
        raise BatchMintError(f"owner must be {_OWNER_MIN_LEN}-{_OWNER_MAX_LEN} chars: {owner!r}")
    if any(c in owner for c in "{}<>") or any(c.isspace() for c in owner):
        raise BatchMintError(f"owner must be a contact address, not a placeholder: {owner!r}")
    if "@" not in owner or "." not in owner.rsplit("@", 1)[-1]:
        raise BatchMintError(f"owner must be a reachable contact, e.g. name@example.com: {owner!r}")


def load_registered(events: EventLog) -> set[str]:
    """The set of agent names already registered (so we never double-register)."""
    names: set[str] = set()
    for event in events.iter_events():
        if event.get("type") == "register":
            name = (event.get("payload") or {}).get("name")
            if isinstance(name, str):
                names.add(name)
    return names


def build_claims(
    owner: str,
    agent_name: str,
    agent_pubkey_hex: str,
    *,
    now: float,
    confirmed_via: str,
) -> ConsentClaims:
    """Build the same ConsentClaims shape gateway.enroll_confirm issues."""
    return ConsentClaims(
        token_id=uuid.uuid4().hex[:16],
        owner=owner,
        agent_name=agent_name,
        agent_pubkey_hex=agent_pubkey_hex,
        scopes=list(_DEFAULT_SCOPES),  # type: ignore[arg-type]
        issued_at=now,
        expires_at=now + _TOKEN_TTL_SEC,
        confirmed_via=confirmed_via,
    )


def mint_one(
    entry: dict[str, Any],
    *,
    authority: ConsentAuthority,
    events: EventLog,
    registered: set[str],
    now: float,
    confirmed_via: str,
) -> dict[str, Any]:
    """Validate one roster entry, append its register event, mint its token.

    Mutates ``registered`` so duplicates within the same run are caught too.
    Raises BatchMintError on a reserved/duplicate/invalid entry (the caller
    decides whether to skip or abort).
    """
    owner = entry.get("owner")
    raw_name = entry.get("agent_name")
    pubkey = entry.get("agent_pubkey_hex")
    if not isinstance(owner, str) or not owner.strip():
        raise BatchMintError("entry missing 'owner'")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise BatchMintError("entry missing 'agent_name'")
    if not isinstance(pubkey, str):
        raise BatchMintError(f"{raw_name!r}: missing 'agent_pubkey_hex'")

    # Validate owner + pubkey to the self-serve contract BEFORE the durable
    # register — the gateway validates both at enroll_request, well before
    # enroll_confirm appends. A malformed pubkey otherwise raised only at
    # build_claims (AFTER the append), orphaning the reserved name so a corrected
    # rerun could not mint it without manual event-log surgery (PR #232 review).
    _validate_owner_like_enrollment(owner)
    if not _PUBKEY_RE.fullmatch(pubkey):
        raise BatchMintError(f"{raw_name!r}: agent_pubkey_hex must be 64 lowercase hex chars")

    agent_name = sanitize_name(raw_name) or "visitor"
    if _is_reserved(agent_name):
        raise BatchMintError(f"{agent_name!r}: reserved agent name")
    if agent_name in registered:
        raise BatchMintError(f"{agent_name!r}: agent name already registered")

    # Durable register BEFORE minting — same order + shape as enroll_confirm, so a
    # crash mid-run never mints a token for an unregistered name.
    events.append("register", {"name": agent_name, "frozen": False})
    registered.add(agent_name)

    claims = build_claims(owner, agent_name, pubkey, now=now, confirmed_via=confirmed_via)
    token = authority.mint(claims)  # raises pydantic ValidationError on a bad pubkey
    return {
        "agent_name": agent_name,
        "owner": owner,
        "token": token,
        "expires_at": claims.expires_at,
    }


def batch_mint(
    roster: list[dict[str, Any]],
    *,
    authority: ConsentAuthority,
    events: EventLog,
    confirmed_via: str,
    now_fn: Callable[[], float] = time.time,
    skip_errors: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Mint a token per roster entry. Returns (results, errors)."""
    registered = load_registered(events)
    now = now_fn()
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for entry in roster:
        try:
            results.append(
                mint_one(
                    entry,
                    authority=authority,
                    events=events,
                    registered=registered,
                    now=now,
                    confirmed_via=confirmed_via,
                )
            )
        except (BatchMintError, ValueError) as exc:
            msg = f"{entry.get('agent_name', '?')}: {exc}"
            if not skip_errors:
                raise BatchMintError(msg) from exc
            errors.append(msg)
            log.warning("batch-mint skipped %s", msg)
    return results, errors


def _write_tokens(out_path: Path, results: list[dict[str, Any]]) -> None:
    """Atomically write tokens to a 0600 file (secrets — never stdout).

    Write to a private temp file in the same directory then ``os.replace`` it
    into place, so the final inode ALWAYS carries 0600 — even when ``out_path``
    already exists with a looser mode. The earlier ``os.open(out_path, O_CREAT,
    0o600)`` ignored the mode for an *existing* file, so a rerun against a
    touched/checked-in 0644 placeholder leaked the secret tokens under the old
    permissions (PR #232 review). The atomic rename also guarantees a crash
    mid-write never leaves a partial — or world-readable — token file behind.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp creates the file 0600 and owned by us; we never widen it.
    fd, tmp = tempfile.mkstemp(dir=out_path.parent, prefix=f".{out_path.name}.", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)  # explicit + future-proof against a permissive umask
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, out_path)  # atomic; the 0600 temp inode becomes out_path
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def _preflight_output(out_path: Path) -> None:
    """Fail BEFORE any durable register if the token file can't be written.

    ``batch_mint`` appends a durable ``register`` event per entry; if the later
    ``_write_tokens`` then fails (bad path, unwritable dir, read-only fs), the
    names are reserved but the bearer tokens are lost — and a corrected rerun
    rejects them as duplicates, forcing manual event-log surgery (PR #232
    review). Probe the destination up front — create the parent dir and a
    throwaway temp file in it — so those failures abort the run with ZERO
    durable side effects, leaving the roster safe to rerun verbatim. (The
    atomic ``_write_tokens`` covers a crash mid-write; this covers the bad
    destination, which is the common operator mistake.)
    """
    # A directory target passes the parent-writable probe but later fails the
    # os.replace in _write_tokens — AFTER the durable registers. Reject it here
    # so the run aborts with zero durable side effects (PR #245 review).
    if out_path.is_dir():
        raise IsADirectoryError(f"--out {out_path} is a directory, not a file path")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, probe = tempfile.mkstemp(dir=out_path.parent, prefix=f".{out_path.name}.probe.")
    os.close(fd)
    os.unlink(probe)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--roster",
        required=True,
        help="roster JSON file (list of {owner,agent_name,agent_pubkey_hex})",
    )
    ap.add_argument(
        "--out", required=True, help="output JSON path for minted tokens (written 0600)"
    )
    ap.add_argument(
        "--confirmed-via", default="batch-mint", help="confirmed_via label recorded in each token"
    )
    ap.add_argument(
        "--skip-errors",
        action="store_true",
        help="skip reserved/duplicate/invalid entries instead of aborting",
    )
    ap.add_argument(
        "--runtime-dir",
        default=os.environ.get("ARENA_RUNTIME_DIR", "/tmp/arena-runtime"),
        help="arena runtime dir (events.jsonl lives here) — MUST match the deploy",
    )
    args = ap.parse_args(argv)

    key_hex = os.environ.get("ARENA_SIGNING_KEY_HEX", "").strip()
    if not key_hex:
        # Fail-closed: an ephemeral key would mint tokens the live gateway rejects.
        print(
            "ERROR: ARENA_SIGNING_KEY_HEX not set — refusing (tokens would not verify).",
            file=sys.stderr,
        )
        return 2

    roster = json.loads(Path(args.roster).read_text(encoding="utf-8"))
    if not isinstance(roster, list):
        print("ERROR: roster must be a JSON list", file=sys.stderr)
        return 2

    # Probe the output destination BEFORE batch_mint appends any durable register
    # events — a bad --out must not leave reserved names with no delivered tokens.
    out_path = Path(args.out)
    try:
        _preflight_output(out_path)
    except OSError as exc:
        print(
            f"ERROR: --out {args.out} is not writable ({exc}) — refusing before minting.",
            file=sys.stderr,
        )
        return 2

    authority = ConsentAuthority(signing_key_hex=key_hex)
    events = EventLog(Path(args.runtime_dir) / "events.jsonl")
    results, errors = batch_mint(
        roster,
        authority=authority,
        events=events,
        confirmed_via=args.confirmed_via,
        skip_errors=args.skip_errors,
    )
    _write_tokens(out_path, results)

    # Summary only — NEVER echo token values (secrets discipline).
    print(f"batch-mint: {len(results)} token(s) written to {args.out} (0600)")
    for r in results:
        print(f"  - {r['agent_name']}  owner={r['owner']}  expires_at={int(r['expires_at'])}")
    if errors:
        print(f"skipped {len(errors)} entr(y/ies):", file=sys.stderr)
        for e in errors:
            print(f"  ! {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
