"""Import-direction guard (digest §2 architecture: engine → client → view).

The single-source-of-truth fold (digest §7) only holds if the layers can't reach
"up": ``lineproto`` (protocol types) and ``client`` (state reducer) must NOT
import the engine (``sidecar``/``sim``), the view, or the TUI. This is an
AST-level scan of the actual import statements, so it catches a bad import the
moment it lands — not just at runtime.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "adx_showdown"

# module → modules it must never import (substring match on the dotted name)
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "lineproto": ("sidecar", "sim", "view", "tui", "client"),
    "client": ("sidecar", "sim", "view", "tui"),
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_lower_layers_never_import_upward():
    for module, forbidden in FORBIDDEN.items():
        path = _SRC / f"{module}.py"
        assert path.exists(), f"missing {path}"
        imported = _imports(path)
        for imp in imported:
            tail = imp.split(".")[-1]
            assert tail not in forbidden, (
                f"{module}.py imports '{imp}' — forbidden upward import "
                f"(layer must stay below {forbidden})"
            )
