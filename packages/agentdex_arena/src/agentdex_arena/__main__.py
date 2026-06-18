"""Runnable arena gateway — `python -m agentdex_arena` (phase 9 deploy entrypoint).

Single process, single `$PORT` (Spaces/Koyeb nano contract, see the arena deploy
go/no-go reference). The out-of-band owner channel (A1 — the confirmation code
must reach the OWNER, never the agent-visible response) is pluggable:

- production: set `ARENA_OWNER_WEBHOOK` and the notifier POSTs the code there.
- local / design-partner playtest: codes are written to per-owner files under
  `ARENA_OWNER_INBOX_DIR` (default `/tmp/arena-owner-inbox`). Driving one of our
  OWN agents as the visiting agent — which may read its owner's inbox — is the
  sanctioned phase-8 loop (no external human coordination needed).

The signing key comes from `ARENA_SIGNING_KEY_HEX`; for a local run with none set
the launcher mints an ephemeral key and prints a loud warning (tokens won't
survive a restart — fine for a playtest, never for a deploy).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from collections.abc import Callable
from pathlib import Path

import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agentdex_arena.admin_auth import AdminAuthority
from agentdex_arena.badge_auth import BadgeAuthError, BadgeAuthority
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app

log = logging.getLogger("agentdex_arena.serve")

_OWNER_SAFE = re.compile(r"[^a-z0-9._-]+")


def _owner_slug(owner: str) -> str:
    """A filesystem-safe, collision-resistant per-owner inbox filename."""
    base = _OWNER_SAFE.sub("-", owner.lower()).strip("-")[:48] or "owner"
    digest = hashlib.blake2b(owner.encode(), digest_size=4).hexdigest()
    return f"{base}.{digest}.code"


def _file_inbox_notifier(inbox_dir: Path) -> Callable[[str, str], None]:
    inbox_dir.mkdir(parents=True, exist_ok=True)

    def notify(owner: str, code: str) -> None:
        # Atomic write so a polling owner never reads a half-written code.
        target = inbox_dir / _owner_slug(owner)
        tmp = target.with_suffix(".code.tmp")
        tmp.write_text(code + "\n", encoding="utf-8")
        tmp.replace(target)
        log.info("owner notify: wrote confirmation code for %r to %s", owner, target.name)

    return notify


def _deliver_webhook(
    url: str,
    owner: str,
    code: str,
    *,
    timeout: float,
    fallback: Callable[[str, str], None] | None,
) -> bool:
    """POST the confirmation code to the owner webhook; fall back on any failure.

    Synchronous + directly testable (the threaded wrapper below calls it). Returns
    True iff the webhook accepted the code (2xx). On ANY failure — network error,
    non-2xx, or a raising fallback — a code is never silently dropped: we invoke
    ``fallback`` (the file inbox) so an operator can still recover the code, and
    return False. An email channel is served by pointing the webhook at an
    email-relay endpoint; we deliberately keep ONE delivery mechanism here.
    """
    import httpx  # local import — keeps server cold-start lean (mirrors local_log.py)

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json={"owner": owner, "code": code})
        resp.raise_for_status()
        log.info("owner notify: POSTed confirmation code for %r to webhook", owner)
        return True
    except Exception as exc:  # noqa: BLE001 — any delivery failure must fall back, never drop the code
        log.warning(
            "owner notify: webhook delivery failed for %r (%s); falling back to file inbox",
            owner,
            exc,
        )
        if fallback is not None:
            try:
                fallback(owner, code)
            except Exception:  # noqa: BLE001 — fallback failure is logged, not raised into the request
                log.exception("owner notify: file-inbox fallback ALSO failed for %r", owner)
        return False


def _webhook_notifier(
    url: str,
    *,
    fallback: Callable[[str, str], None] | None,
    timeout: float,
) -> Callable[[str, str], None]:
    """A `notify_owner` that POSTs the code to ``url`` off the event loop.

    ``enroll_request`` runs ON the asyncio event loop (the `/enroll/request`
    route is ``async def`` and calls it directly), so a blocking webhook POST
    would stall every in-flight battle turn under load. We therefore fire the
    delivery in a daemon thread and return immediately, preserving the synchronous
    ``Callable[[str, str], None]`` contract with zero gateway changes. Delivery
    (and the file-inbox fallback on failure) happens in the thread.
    """

    def notify(owner: str, code: str) -> None:
        threading.Thread(
            target=_deliver_webhook,
            args=(url, owner, code),
            kwargs={"timeout": timeout, "fallback": fallback},
            name="arena-owner-webhook",
            daemon=True,
        ).start()

    return notify


def build_gateway() -> ArenaGateway:
    key_hex = os.environ.get("ARENA_SIGNING_KEY_HEX", "").strip()
    if not key_hex:
        key_hex = Ed25519PrivateKey.generate().private_bytes_raw().hex()
        log.warning(
            "ARENA_SIGNING_KEY_HEX not set — minted an EPHEMERAL key. Tokens will not "
            "survive a restart. Set the env var for any persistent deploy."
        )

    runtime = Path(os.environ.get("ARENA_RUNTIME_DIR", "/tmp/arena-runtime"))
    inbox = Path(os.environ.get("ARENA_OWNER_INBOX_DIR", "/tmp/arena-owner-inbox"))
    authority = ConsentAuthority(signing_key_hex=key_hex)

    # Out-of-band owner channel (A1): the confirmation code must reach the OWNER,
    # never the agent-visible response. Production sets ARENA_OWNER_WEBHOOK and the
    # code is POSTed there (off the event loop); the file inbox is always built as
    # the fallback so a delivery failure never drops a code. Unset → file inbox only
    # (the local/playtest path). This makes the module docstring's webhook promise real.
    file_notifier = _file_inbox_notifier(inbox)
    webhook = os.environ.get("ARENA_OWNER_WEBHOOK", "").strip()
    if webhook:
        webhook_timeout = float(os.environ.get("ARENA_OWNER_WEBHOOK_TIMEOUT", "5"))
        notify_owner = _webhook_notifier(webhook, fallback=file_notifier, timeout=webhook_timeout)
        log.info("owner notify: webhook channel enabled (file inbox is the fallback)")
    else:
        notify_owner = file_notifier

    # Write-behind Postgres mirror (BENE-Supabase design): dev = local Postgres,
    # prod = the Supabase transaction-mode pooler DSN (port 6543). Unset = no
    # mirror; the local hash-chained NDJSON is always the source of truth.
    event_sync = None
    pg_dsn = os.environ.get("ARENA_PG_DSN", "").strip()
    if pg_dsn:
        from agentdex_arena.eventsync import WriteBehindSync

        event_sync = WriteBehindSync(
            pg_dsn, apply_ddl=os.environ.get("ARENA_PG_APPLY_DDL", "") == "1"
        )
        log.info("event mirror: write-behind to Postgres enabled")

    # Admin authority for operator-only routes (ADR-0011 11b). Fail-closed
    # boot: missing or malformed ARENA_ADMIN_TOKEN_HASH raises AdminAuthError
    # which kills the container at startup. No runtime degraded mode.
    admin = AdminAuthority()

    # Badge signing authority for ADR-0011 11c (first paid feature). Soft-fail
    # boot per PR #130 review #3410920013: if ARENA_BADGE_SIGNING_KEY_HEX is
    # missing or malformed, we log a warning, set badge_authority=None, and
    # let `POST /badge/mint` return 503 'badge mint not configured' (gateway.py
    # already supports this degraded path). The previous fail-closed boot was
    # too aggressive — it took down enrollment / ladder / battle / replay
    # routes even though only the paid badge feature is unconfigured. The
    # `adx deploy` forward-vars list does not yet propagate the new env;
    # routing operators to set ARENA_BADGE_SIGNING_KEY_HEX is in the
    # badge-admin runbook rather than a boot-time hard requirement.
    try:
        badge = BadgeAuthority()
    except BadgeAuthError as e:
        log.warning(
            "BadgeAuthority unconfigured (%s); /badge/mint will respond 503 "
            "until ARENA_BADGE_SIGNING_KEY_HEX is set. Other routes unaffected.",
            e,
        )
        badge = None

    # Absolute base URL for README-embeddable badge URLs (PR #130 review
    # #3410920009 / PR #136 follow-up review #3411158896). Default is the
    # EMPTY string — when unset, `/badge/mint` emits relative `svg_url` /
    # `verify_url` paths. Defaulting to the prod hostname would make every
    # non-prod deploy (staging, preview, fork, local Docker, integration
    # test) mint README URLs under `https://agentdex.ai-builders.space`
    # while the badge was signed by THAT deploy's badge key — following
    # the returned URL on prod would fail Ed25519 verification and show
    # the wrong ladder. The prod deploy MUST set ARENA_PUBLIC_BASE_URL
    # explicitly (documented in docs/runbooks/badge-admin.md §"Setting the
    # README-embed base URL").
    public_base_url = os.environ.get("ARENA_PUBLIC_BASE_URL", "")

    return ArenaGateway(
        authority=authority,
        events_path=runtime / "events.jsonl",
        artifacts_dir=runtime / "artifacts",
        notify_owner=notify_owner,
        rated_seed_secret=os.environ.get("ARENA_RATED_SEED_SECRET", ""),
        event_sync=event_sync,
        admin_authority=admin,
        badge_authority=badge,
        public_base_url=public_base_url,
    )


def _bootstrap_admin_token_hash() -> None:
    """Derive ARENA_ADMIN_TOKEN_HASH from AI_BUILDER_TOKEN when not explicitly set.

    Koyeb (via space.ai-builders.com) auto-injects AI_BUILDER_TOKEN into every
    container — the platform API key used to trigger the deploy. Treating that
    key as the admin bearer ties admin access to the same credential that owns
    the deploy: whoever holds the platform key already has deploy authority.

    Behavior:
      - ARENA_ADMIN_TOKEN_HASH explicitly set  → no-op (operator chose the token)
      - ARENA_ADMIN_TOKEN_HASH unset + AI_BUILDER_TOKEN present → derive hex sha256
      - Neither set → no-op; AdminAuthority will fail-closed at boot (preserved)
    """
    if os.environ.get("ARENA_ADMIN_TOKEN_HASH"):
        return
    builder_token = os.environ.get("AI_BUILDER_TOKEN", "").strip()
    if not builder_token:
        return
    derived = hashlib.sha256(builder_token.encode("utf-8")).hexdigest()
    os.environ["ARENA_ADMIN_TOKEN_HASH"] = derived
    log.info(
        "ARENA_ADMIN_TOKEN_HASH derived from AI_BUILDER_TOKEN (sha256, first 8 of hash = %s)",
        derived[:8],
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    _bootstrap_admin_token_hash()
    from adx_showdown.pool import SidecarPool
    from adx_showdown.sidecar import Sidecar

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8889"))
    # Concurrent visiting agents each hold a live battle; the sim defaults to only
    # 4 (~+7 MB RSS each). Size the ceiling for the 256 MB nano (idle ~55 MB) and
    # let the deploy tune it via env (playtest G-03 — multi-agent capacity).
    max_battles = int(os.environ.get("ARENA_MAX_BATTLES", "16"))
    # ADR-0012: partition battles across a SidecarPool (battle_id routing). Default
    # pool size 1 keeps the single-sidecar behavior byte-for-byte; on a multi-core
    # box raise ADX_SIDECAR_POOL_SIZE (and ADX_SIDECAR_MAX_OLD_SPACE_MB) to scale
    # the sim tier toward ~100 concurrent. Per-sidecar cap stays ARENA_MAX_BATTLES.
    pool_size = int(os.environ.get("ADX_SIDECAR_POOL_SIZE", "1"))
    if pool_size > 1:
        app = create_app(
            build_gateway(),
            sidecar_factory=lambda: SidecarPool(
                size=pool_size, max_battles_per_sidecar=max_battles
            ),
        )
    else:
        app = create_app(build_gateway(), sidecar_factory=lambda: Sidecar(max_battles=max_battles))
    log.info(
        "agentdex-arena serving on http://%s:%d (owner inbox: %s)",
        host,
        port,
        os.environ.get("ARENA_OWNER_INBOX_DIR", "/tmp/arena-owner-inbox"),
    )
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
