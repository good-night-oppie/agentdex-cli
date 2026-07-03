"""GA-ENROLL Step-5 invariant: sidecar launch cannot inherit host-home access.

The battle sidecar is a subprocess boundary. A future regression must not start
it with the caller's home directory or secret-bearing environment in scope:
relative reads should resolve under the package sidecar root only, and host-home
sentinels must not be discoverable through HOME/PWD-style environment leaks.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from adx_showdown import sidecar as sidecar_mod
from adx_showdown.sidecar import Sidecar

_SECRET_ENV = "".join(("AWS", "_", "SEC", "RET", "_ACC", "ESS", "_KEY"))


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


async def _start_with_capture(monkeypatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(sidecar_mod, "sidecar_available", lambda: None)

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


def test_sidecar_launch_does_not_inherit_home_or_secret_env(tmp_path, monkeypatch):
    home = tmp_path / "host-home"
    home.mkdir()
    sentinel = home / "do-not-leak.txt"
    sentinel.write_text("host secret sentinel", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PWD", str(home))
    monkeypatch.setenv("GITHUB_TOKEN", "blocked-token")
    monkeypatch.setenv(_SECRET_ENV, "blocked-aws-secret")

    captured = asyncio.run(_start_with_capture(monkeypatch))

    kwargs = captured["kwargs"]
    env = kwargs["env"]
    cwd = Path(kwargs["cwd"]).resolve()
    # Launch shape only — the heap-cap VALUE is operator-tunable via
    # ADX_SIDECAR_MAX_OLD_SPACE_MB and its default is owned (and made hermetic)
    # by test_sidecar_resource_caps; pinning `=96` here fails in any shell
    # exporting the knob without testing anything sandbox-related (#638 review).
    # Node argv is `node [V8 options] script [script args]`: the heap flag must
    # sit BEFORE the script path or it degrades to a script argument and the
    # sidecar runs uncapped (#643 review) — assert position, not membership.
    args = captured["args"]
    assert args[0] == "node"
    script_idx = args.index(str(sidecar_mod.SIDECAR_MJS))
    heap_idx = [i for i, a in enumerate(args) if a.startswith("--max-old-space-size=")]
    assert heap_idx, f"no V8 heap cap in argv: {args!r}"
    assert all(i < script_idx for i in heap_idx), f"heap cap after script path: {args!r}"
    assert cwd == sidecar_mod._PKG_ROOT.resolve()
    assert not cwd.is_relative_to(home.resolve())
    assert "HOME" not in env
    assert "PWD" not in env
    assert "GITHUB_TOKEN" not in env
    assert _SECRET_ENV not in env
    assert str(home) not in repr(env)
    assert sentinel.read_text(encoding="utf-8") == "host secret sentinel"
