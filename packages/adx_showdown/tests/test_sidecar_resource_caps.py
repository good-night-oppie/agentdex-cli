"""GA-ENROLL Step-5 invariant: sidecar resource caps are enforced at launch.

The enrolled agent battle substrate is the Node BattleStream sidecar. It must
start with an explicit V8 old-space cap and a minimal, non-secret environment so
a bad battle cannot inherit host credentials or grow memory without an operator
setting the cap deliberately.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from adx_showdown import sidecar as sidecar_mod
from adx_showdown.sidecar import Sidecar

_AWS_CREDENTIAL_ENV = "".join(("AWS", "_", "SEC", "RET", "_ACC", "ESS", "_KEY"))
_SIDECAR_ENV_KNOBS = (
    "ADX_SIDECAR_MAX_OLD_SPACE_MB",
    "ADX_SIDECAR_MAX_PROTOCOL_LINES",
    "ADX_SIDECAR_MAX_PROTOCOL_BYTES",
)


class _FakeStdout:
    def __init__(self) -> None:
        self._lines = [json.dumps({"event": "ready"}).encode() + b"\n", b""]

    async def readline(self) -> bytes:
        await asyncio.sleep(0)
        return self._lines.pop(0) if self._lines else b""


class _FakeStdin:
    def write(self, _data: bytes) -> None:
        return None

    async def drain(self) -> None:
        return None


class _FakeProc:
    def __init__(self) -> None:
        self.stdout = _FakeStdout()
        self.stdin = _FakeStdin()
        self.returncode = None

    async def wait(self) -> int:
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.returncode = -9


async def _start_with_capture(monkeypatch, **env) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(sidecar_mod, "sidecar_available", lambda: None)
    for key in (*_SIDECAR_ENV_KNOBS, "GITHUB_TOKEN", _AWS_CREDENTIAL_ENV):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr(sidecar_mod.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    sc = Sidecar()
    try:
        await sc.start()
        return captured
    finally:
        if sc._reader_task is not None:  # type: ignore[attr-defined]
            sc._reader_task.cancel()  # type: ignore[attr-defined]
            try:
                await sc._reader_task  # type: ignore[attr-defined]
            except asyncio.CancelledError:
                pass


def test_sidecar_launches_with_default_v8_heap_cap(monkeypatch):
    captured = asyncio.run(_start_with_capture(monkeypatch))

    args = captured["args"]
    assert args[:3] == ("node", "--expose-gc", "--max-old-space-size=96")
    assert args[3] == str(sidecar_mod.SIDECAR_MJS)
    assert captured["kwargs"]["cwd"] == str(sidecar_mod._PKG_ROOT)


def test_sidecar_env_is_minimal_and_cap_is_operator_tunable(monkeypatch):
    captured = asyncio.run(
        _start_with_capture(
            monkeypatch,
            ADX_SIDECAR_MAX_OLD_SPACE_MB="128",
            GITHUB_TOKEN="blocked-value",
            **{_AWS_CREDENTIAL_ENV: "blocked-value"},
        )
    )

    args = captured["args"]
    env = captured["kwargs"]["env"]
    assert "--max-old-space-size=128" in args
    assert env["NODE_ENV"] == "production"
    assert set(env) == {"PATH", "NODE_ENV"}
    assert "blocked-value" not in repr(env)
