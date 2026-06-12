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
from pathlib import Path

import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app

log = logging.getLogger("agentdex_arena.serve")

_OWNER_SAFE = re.compile(r"[^a-z0-9._-]+")


def _owner_slug(owner: str) -> str:
    """A filesystem-safe, collision-resistant per-owner inbox filename."""
    base = _OWNER_SAFE.sub("-", owner.lower()).strip("-")[:48] or "owner"
    digest = hashlib.blake2b(owner.encode(), digest_size=4).hexdigest()
    return f"{base}.{digest}.code"


def _file_inbox_notifier(inbox_dir: Path):
    inbox_dir.mkdir(parents=True, exist_ok=True)

    def notify(owner: str, code: str) -> None:
        # Atomic write so a polling owner never reads a half-written code.
        target = inbox_dir / _owner_slug(owner)
        tmp = target.with_suffix(".code.tmp")
        tmp.write_text(code + "\n", encoding="utf-8")
        tmp.replace(target)
        log.info("owner notify: wrote confirmation code for %r to %s", owner, target.name)

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
    return ArenaGateway(
        authority=authority,
        events_path=runtime / "events.jsonl",
        artifacts_dir=runtime / "artifacts",
        notify_owner=_file_inbox_notifier(inbox),
        rated_seed_secret=os.environ.get("ARENA_RATED_SEED_SECRET", ""),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from adx_showdown.sidecar import Sidecar

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8889"))
    # Concurrent visiting agents each hold a live battle; the sim defaults to only
    # 4 (~+7 MB RSS each). Size the ceiling for the 256 MB nano (idle ~55 MB) and
    # let the deploy tune it via env (playtest G-03 — multi-agent capacity).
    max_battles = int(os.environ.get("ARENA_MAX_BATTLES", "16"))
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
