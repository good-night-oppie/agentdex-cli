"""Submit tool -- signal task completion and capture the patch."""
from __future__ import annotations

import subprocess

from strands import tool

_container_name: str | None = None
_submitted: bool = False
_submit_patch: str | None = None


def reset(**kwargs) -> None:
    global _container_name, _submitted, _submit_patch
    _container_name = kwargs.get("container_name")
    _submitted = False
    _submit_patch = None


def was_submitted() -> bool:
    return _submitted


def get_submitted_patch() -> str | None:
    return _submit_patch


@tool
def submit(confirmation: str = "done") -> str:
    """Submit your solution and end the task.

    Call this tool when you have finished fixing the issue and verified your
    changes (e.g. by running relevant tests or reviewing git diff).
    After calling submit, do NOT call any more tools.

    Args:
        confirmation: A short summary of what you changed and why.
    """
    global _submitted, _submit_patch
    _submitted = True
    try:
        if _container_name:
            result = subprocess.run(
                ["docker", "exec", "-w", "/testbed", _container_name,
                 "bash", "-c", "git diff"],
                capture_output=True, text=True, timeout=30,
            )
            _submit_patch = result.stdout or ""
    except Exception:
        _submit_patch = None
    return (
        f"Solution submitted: {confirmation}\n"
        "You are done. Do NOT call any more tools."
    )
