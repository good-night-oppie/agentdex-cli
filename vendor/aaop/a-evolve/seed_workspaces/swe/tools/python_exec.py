"""Python execution tool — run Python code inside the SWE-bench Docker container.

Executes Python code via stdin (python3 -). Each execution is independent —
no state persists between calls. Use print() to see output.
"""

from __future__ import annotations

import subprocess

from strands import tool

_container_name: str | None = None


def reset(**kwargs) -> None:
    global _container_name
    _container_name = kwargs.get("container_name")


@tool
def python_exec(code: str) -> str:
    """Execute Python code inside the Docker container.

    Runs the code with python3. Each execution is independent — no state persists
    between calls. Use print() statements to see output.

    Args:
        code: Python code to execute.
    """
    if not _container_name:
        return "Error: container not initialized"
    try:
        result = subprocess.run(
            ["docker", "exec", "-w", "/testbed", _container_name, "python3", "-"],
            input=code,
            capture_output=True,
            text=True,
            timeout=180,
        )
        output = ""
        if result.stderr:
            output += result.stderr
        if result.stdout:
            if output:
                output += "\n"
            output += result.stdout
        if not output.strip():
            output = "(no output — use print() to see results)"
        if len(output) > 15000:
            output = output[:7000] + "\n\n... [truncated] ...\n\n" + output[-7000:]
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output
    except subprocess.TimeoutExpired:
        return "ERROR: Python execution timed out after 180 seconds."
    except Exception as e:
        return f"ERROR: {e}"
