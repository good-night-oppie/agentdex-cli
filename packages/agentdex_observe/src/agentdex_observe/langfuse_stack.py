"""Langfuse self-host lifecycle manager — scoped to Expedition window.

Per ADR-0009 §Observability + user direction 2026-06-08 "搜集竟合整个 lifecycle.
not any time" — Langfuse runs DURING an Expedition (so all bridge.send +
soft Oracle calls flow into traces), and stays up afterwards so the user can
drill down. Tear-down on demand via ``adx langfuse down``.

Lifecycle verbs:
- :func:`status` — probe ``http://<host>:3000/api/public/health``
- :func:`up` — ``docker compose up -d`` against bundled compose; wait healthy
- :func:`down` — ``docker compose down``
- :func:`ensure` — status; if down, up. Idempotent. Returns LangfuseHandle.

Credentials persistence:
- LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY persisted to
  ``~/.adx/langfuse.env`` after first init (Langfuse's seed-org workflow).
- ``ensure()`` exports them into ``os.environ`` so subsequent
  ``agentdex_observe.init_langfuse()`` picks them up transparently.

Compose bundle: ``compose/langfuse.docker-compose.yml`` — official Langfuse v3
stack (postgres + clickhouse + minio + redis + langfuse-web + langfuse-worker),
all 6 services. First-run image pull is ~2GB; subsequent up is ~10s.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_COMPOSE_PATH = Path(__file__).resolve().parent / "compose" / "langfuse.docker-compose.yml"
_PROJECT_NAME = "agentdex-langfuse"
_ENV_PATH = Path(os.path.expanduser("~/.adx/langfuse.env"))
_DEFAULT_HOST = "http://localhost:3000"


@dataclass
class LangfuseHandle:
    host: str
    healthy: bool
    public_key: str | None
    secret_key: str | None


def _docker_compose_available() -> bool:
    if not shutil.which("docker"):
        return False
    rc = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        text=True,
    ).returncode
    return rc == 0


def _health_check(host: str = _DEFAULT_HOST, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{host}/api/public/health", timeout=timeout) as r:
            return 200 <= r.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError):
        return False


def _wait_healthy(host: str = _DEFAULT_HOST, max_seconds: int = 180) -> bool:
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        if _health_check(host):
            return True
        time.sleep(3.0)
    return False


def status(host: str = _DEFAULT_HOST) -> LangfuseHandle:
    healthy = _health_check(host)
    pk, sk = _load_env_creds()
    return LangfuseHandle(host=host, healthy=healthy, public_key=pk, secret_key=sk)


def up(*, max_wait_seconds: int = 180) -> LangfuseHandle:
    if not _docker_compose_available():
        raise RuntimeError(
            "docker + 'docker compose' not available; cannot bring Langfuse up. "
            "Install docker desktop / docker engine + compose plugin."
        )
    if not _COMPOSE_PATH.is_file():
        raise FileNotFoundError(f"bundled compose missing: {_COMPOSE_PATH}")

    subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            _PROJECT_NAME,
            "-f",
            str(_COMPOSE_PATH),
            "up",
            "-d",
        ],
        check=True,
    )
    ok = _wait_healthy(max_seconds=max_wait_seconds)
    pk, sk = _ensure_creds()
    return LangfuseHandle(
        host=_DEFAULT_HOST,
        healthy=ok,
        public_key=pk,
        secret_key=sk,
    )


def down() -> None:
    if not _docker_compose_available():
        return
    subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            _PROJECT_NAME,
            "-f",
            str(_COMPOSE_PATH),
            "down",
        ],
        check=False,
    )


def ensure(*, max_wait_seconds: int = 180) -> LangfuseHandle:
    """Probe → up if down → wait healthy → export creds to os.environ."""
    h = status()
    if not h.healthy:
        h = up(max_wait_seconds=max_wait_seconds)
    if h.public_key and h.secret_key:
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", h.public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", h.secret_key)
    os.environ.setdefault("LANGFUSE_HOST", h.host)
    return h


def _load_env_creds() -> tuple[str | None, str | None]:
    if not _ENV_PATH.is_file():
        return None, None
    pk = sk = None
    for line in _ENV_PATH.read_text().splitlines():
        if line.startswith("LANGFUSE_PUBLIC_KEY="):
            pk = line.split("=", 1)[1].strip()
        elif line.startswith("LANGFUSE_SECRET_KEY="):
            sk = line.split("=", 1)[1].strip()
    return pk, sk


def _ensure_creds() -> tuple[str | None, str | None]:
    """Return (pk, sk). If ~/.adx/langfuse.env missing, instruct user to seed.

    Langfuse v3 self-host requires manual project creation through the UI on
    first run (seed-org workflow); programmatic key issuance lands post-seed.
    We do NOT try to bypass that — surface a clear message instead.
    """
    pk, sk = _load_env_creds()
    if pk and sk:
        return pk, sk
    # Surface a clear seed-instruction file so the user knows what to do next.
    _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _ENV_PATH.is_file():
        _ENV_PATH.write_text(
            "# Langfuse self-host credentials — fill after first-run UI seed.\n"
            "# 1. Visit http://localhost:3000\n"
            "# 2. Create org + project (default: 'agentdex')\n"
            "# 3. Settings → API Keys → Create new keys\n"
            "# 4. Paste them below, then re-run `adx expedition`.\n"
            "LANGFUSE_PUBLIC_KEY=\n"
            "LANGFUSE_SECRET_KEY=\n"
        )
    return pk, sk


__all__ = ["status", "up", "down", "ensure", "LangfuseHandle"]
