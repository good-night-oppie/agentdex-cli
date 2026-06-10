"""Bash tool -- execute commands inside the SWE-bench Docker container."""
from __future__ import annotations

import subprocess

from strands import tool

_container_name: str | None = None


def reset(**kwargs) -> None:
    global _container_name
    _container_name = kwargs.get("container_name")


def _get_container() -> str:
    if _container_name is None:
        raise RuntimeError("Container name not set. Call reset(container_name=...) first.")
    return _container_name


@tool
def bash(command: str, workdir: str = "/testbed") -> str:
    """Execute a bash command inside the SWE-bench Docker container.

    Use this to explore the codebase, edit files, run tests, and generate patches.
    The repository is located at /testbed.

    Args:
        command: The bash command to execute.
        workdir: Working directory for the command. Defaults to /testbed.
    """
    try:
        result = subprocess.run(
            ["docker", "exec", "-w", workdir, _get_container(), "bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if not output.strip():
            output = "(no output)"
        if len(output) > 15000:
            output = output[:7000] + "\n\n... [truncated] ...\n\n" + output[-7000:]
        # Append exit code so the model knows if the command succeeded
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out after 300 seconds."
    except Exception as e:
        return f"ERROR: {e}"
