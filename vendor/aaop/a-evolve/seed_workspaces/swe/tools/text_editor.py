"""Text editor tool for SWE-bench solver.

Provides structured file editing operations instead of error-prone sed/cat commands.
Supports: view, create, str_replace, insert, undo_edit.

Modeled after inspect_ai's text_editor tool.
"""

from __future__ import annotations

import subprocess
from typing import Literal

from strands import tool

_container_name: str | None = None
_edit_history: dict[str, list[str]] = {}  # file_path -> list of previous contents


def reset(container_name: str | None = None, **kwargs) -> None:
    """Reset state for a new task."""
    global _container_name, _edit_history
    _container_name = container_name
    _edit_history = {}


def _exec(command: str, timeout: int = 180) -> str:
    """Execute a command in the Docker container."""
    if not _container_name:
        return "Error: container not initialized"
    result = subprocess.run(
        ["docker", "exec", "-w", "/testbed", _container_name, "bash", "-c", command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return output.strip()


@tool
def text_editor(
    command: str,
    path: str,
    file_text: str = "",
    old_str: str = "",
    new_str: str = "",
    insert_line: int = 0,
    view_range: str = "",
) -> str:
    """Edit files with structured commands instead of raw bash.

    Commands:
    - view: Show file contents. Use view_range="1-50" to show specific lines.
    - create: Create a new file with file_text content.
    - str_replace: Replace old_str with new_str in the file. old_str must match EXACTLY one location.
    - insert: Insert new_str after line insert_line (0 = beginning of file).
    - undo_edit: Revert the last edit to this file.

    Args:
        command: One of "view", "create", "str_replace", "insert", "undo_edit"
        path: Absolute file path (e.g. "/testbed/django/db/models/base.py")
        file_text: Content for "create" command
        old_str: Text to find for "str_replace" (must be unique in file)
        new_str: Replacement text for "str_replace", or text to insert for "insert"
        insert_line: Line number after which to insert (for "insert" command)
        view_range: Line range for "view" command (e.g. "1-50", "100-150")
    """
    if not path.startswith("/"):
        path = f"/testbed/{path}"

    if command == "view":
        if view_range:
            parts = view_range.split("-")
            if len(parts) == 2:
                start, end = parts[0].strip(), parts[1].strip()
                return _exec(f"sed -n '{start},{end}p' '{path}' | cat -n")
            else:
                return _exec(f"cat -n '{path}'")
        else:
            return _exec(f"cat -n '{path}'")

    elif command == "create":
        if not file_text:
            return "Error: file_text is required for create command"
        # Save for undo
        existing = _exec(f"cat '{path}' 2>/dev/null")
        _edit_history.setdefault(path, []).append(existing)
        # Write file using heredoc
        escaped = file_text.replace("'", "'\\''")
        result = _exec(f"cat > '{path}' << 'HEREDOC_EOF'\n{file_text}\nHEREDOC_EOF")
        if result:
            return f"Error creating file: {result}"
        return f"File created: {path}"

    elif command == "str_replace":
        if not old_str:
            return "Error: old_str is required for str_replace command"
        # Read current content
        content = _exec(f"cat '{path}'")
        if not content:
            return f"Error: could not read {path}"

        # Check old_str exists and is unique
        count = content.count(old_str)
        if count == 0:
            return f"Error: old_str not found in {path}. Make sure it matches exactly (including whitespace and indentation)."
        if count > 1:
            return f"Error: old_str found {count} times in {path}. It must be unique. Add more context to make it unique."

        # Save for undo
        _edit_history.setdefault(path, []).append(content)

        # Apply replacement
        new_content = content.replace(old_str, new_str, 1)
        escaped = new_content.replace("'", "'\\''")
        _exec(f"cat > '{path}' << 'HEREDOC_EOF'\n{new_content}\nHEREDOC_EOF")

        # Verify
        verify = _exec(f"cat '{path}'")
        if new_str in verify:
            # Show the edited region with context
            lines = new_content.split("\n")
            new_str_lines = new_str.split("\n")
            for i, line in enumerate(lines):
                if new_str_lines[0] in line:
                    start = max(0, i - 2)
                    end = min(len(lines), i + len(new_str_lines) + 2)
                    snippet = "\n".join(f"{start+j+1:>4} | {lines[start+j]}" for j in range(end - start))
                    return f"Replacement successful. Here's the result around the edit:\n{snippet}"
            return "Replacement successful."
        else:
            return "Warning: replacement may have failed. Please verify with view command."

    elif command == "insert":
        if not new_str:
            return "Error: new_str is required for insert command"
        # Read current content
        content = _exec(f"cat '{path}'")
        if not content and insert_line > 0:
            return f"Error: could not read {path}"

        # Save for undo
        _edit_history.setdefault(path, []).append(content)

        lines = content.split("\n")
        insert_idx = min(insert_line, len(lines))
        new_lines = new_str.split("\n")
        lines[insert_idx:insert_idx] = new_lines

        new_content = "\n".join(lines)
        _exec(f"cat > '{path}' << 'HEREDOC_EOF'\n{new_content}\nHEREDOC_EOF")
        return f"Inserted {len(new_lines)} line(s) after line {insert_line} in {path}"

    elif command == "undo_edit":
        history = _edit_history.get(path, [])
        if not history:
            return f"Error: no edit history for {path}"
        previous = history.pop()
        _exec(f"cat > '{path}' << 'HEREDOC_EOF'\n{previous}\nHEREDOC_EOF")
        return f"Reverted {path} to previous version"

    else:
        return f"Error: unknown command '{command}'. Use: view, create, str_replace, insert, undo_edit"
