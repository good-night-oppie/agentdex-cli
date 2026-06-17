"""test_clean_errors — run_agent_main turns expected failures into clean lines.

A visiting agent that runs a starter-kit agent with a missing keyfile, a bad
team file, an expired token, or an unreachable arena should get ONE actionable
stderr line + a meaningful exit code — not a raw Python traceback it has to
parse (ADX-P2-001 agent-ux footgun).

Run from the kit root (deps: httpx, pytest):
    uv run pytest tests/test_clean_errors.py
or from the workspace venv:
    uv run pytest examples/agent-starter-kit/tests/test_clean_errors.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

# The agents resolve arena_client via this same sys.path hack.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arena_client import run_agent_main  # noqa: E402


def test_passthrough_returns_main_rc():
    assert run_agent_main(lambda: 0) == 0
    assert run_agent_main(lambda: 7) == 7


def test_missing_file_is_setup_error(capsys):
    def boom() -> int:
        raise FileNotFoundError(2, "No such file or directory", "my-bot.key")

    rc = run_agent_main(boom)
    assert rc == 2
    err = capsys.readouterr().err
    assert "file not found" in err
    assert "my-bot.key" in err


def test_value_error_is_setup_error(capsys):
    def boom() -> int:
        raise ValueError("owner_email must be a real contact, not a placeholder")

    rc = run_agent_main(boom)
    assert rc == 2
    assert "placeholder" in capsys.readouterr().err


def test_unexpected_response_shape_is_setup_error(capsys):
    def boom() -> int:
        raise KeyError("battle_id")

    rc = run_agent_main(boom)
    assert rc == 2
    assert "unexpected arena response shape" in capsys.readouterr().err


def test_http_status_error_is_runtime_error(capsys):
    req = httpx.Request("POST", "https://agentdex.ai-builders.space/enroll/request")
    resp = httpx.Response(409, text="agent name already registered", request=req)

    def boom() -> int:
        raise httpx.HTTPStatusError("409", request=req, response=resp)

    rc = run_agent_main(boom)
    assert rc == 1
    err = capsys.readouterr().err
    assert "HTTP 409" in err
    assert "traceback" not in err.lower()


def test_connect_error_is_runtime_error(capsys):
    def boom() -> int:
        raise httpx.ConnectError("[Errno 111] Connection refused")

    rc = run_agent_main(boom)
    assert rc == 1
    assert "could not reach arena" in capsys.readouterr().err


def test_unexpected_exception_is_reraised():
    def boom() -> int:
        raise RuntimeError("a genuine bug, not an expected setup fault")

    # Not in the expected set -> surfaces with a full traceback (not swallowed).
    with pytest.raises(RuntimeError, match="genuine bug"):
        run_agent_main(boom)
