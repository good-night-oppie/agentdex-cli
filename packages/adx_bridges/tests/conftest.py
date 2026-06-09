"""Shared pytest fixtures for adx_bridges live + mocked tests.

Subscription-CLI auth is detected at collection time; tests that need live
``claude`` or ``codex`` are skipped (not failed) when their CLI is missing or
auth has not been configured.
"""

from __future__ import annotations

import os
import shutil

import pytest


def _has_cli(bin_env: str, default: str) -> bool:
    return shutil.which(os.environ.get(bin_env, default)) is not None


@pytest.fixture(scope="session")
def has_claude_cli() -> bool:
    return _has_cli("CLAUDE_BIN", "claude")


@pytest.fixture(scope="session")
def has_codex_cli() -> bool:
    return _has_cli("CODEX_BIN", "codex")


@pytest.fixture(scope="session")
def live_bridges_enabled() -> bool:
    """Live subscription-CLI calls only when ADX_LIVE_BRIDGES=1."""
    return os.environ.get("ADX_LIVE_BRIDGES") == "1"
