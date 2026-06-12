"""Deterministic, no-LLM failure-signature extraction from battle key lines.

The phase-7 Distiller consumes ONLY these structured bullets — never raw
visitor text (IDEAL §Arena A6: the evolution surface reads server-rendered
fields, not opponent-controlled strings). Pattern ids live in patterns.yaml
beside this module; adding a pattern = data change, not code change.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

_PATTERNS_PATH = Path(__file__).resolve().parent / "patterns.yaml"


class Signature(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)
    signature: str
    count: int
    description: str
    evidence: str  # first matching line, sanitized upstream


def load_patterns() -> dict[str, str]:
    data = yaml.safe_load(_PATTERNS_PATH.read_text())
    return {str(k): str(v) for k, v in data["signatures"].items()}


def extract_signatures(key_lines: list[str], *, side: str) -> list[Signature]:
    """`key_lines` = sidecar end-block battle lines; `side` = 'p1'|'p2'.

    Pure line-prefix counting — same lines in, same signatures out.
    """
    patterns = load_patterns()
    mine = f"{side}a"
    other = "p2a" if side == "p1" else "p1a"
    counts: dict[str, tuple[int, str]] = {}

    def bump(sig: str, line: str) -> None:
        n, first = counts.get(sig, (0, line))
        counts[sig] = (n + 1, first)

    last_mover: str | None = None
    for line in key_lines:
        parts = line.split("|")
        if len(parts) < 2:
            continue
        tag = parts[1]
        if tag == "move" and len(parts) > 2:
            last_mover = "me" if parts[2].startswith(mine) else "other"
        elif tag == "-immune" and len(parts) > 2:
            # |-immune|TARGET — the MOVER clicked into an immunity
            if parts[2].startswith(other) and last_mover == "me":
                bump("immune_move_clicked", line)
        elif tag == "-resisted" and len(parts) > 2:
            if parts[2].startswith(other) and last_mover == "me":
                bump("resisted_move_clicked", line)
        elif tag == "-supereffective" and len(parts) > 2:
            if parts[2].startswith(mine):
                bump("supereffective_taken", line)
        elif tag == "faint" and len(parts) > 2:
            if parts[2].startswith(mine):
                bump("mon_fainted", line)
        elif tag == "-crit" and len(parts) > 2 and parts[2].startswith(mine):
            bump("crit_taken", line)

    return [
        Signature(
            signature=sig,
            count=n,
            description=patterns.get(sig, "(undescribed pattern)"),
            evidence=first[:120],
        )
        for sig, (n, first) in sorted(counts.items())
    ]
