#!/usr/bin/env python3
"""Regenerate web/arena2d/data.js from an explain-mode capture JSON.

Single source of truth for the arena2d static fixture: it loads the capture, validates
it through :class:`adx_showdown.reasoning_trace.ReasoningTrace`, and writes the
``data.js`` projection (LOG + RATIONALES) — so the file:// fixture is, by construction, a
strict subset of the same document a ``GET …/trace`` endpoint would serve.

    uv run --package adx-showdown python tools/build_arena2d_data.py \
        /tmp/arena2d_explain_battle.json web/arena2d/data.js
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from adx_showdown.reasoning_trace import ReasoningTrace


def render(trace: ReasoningTrace) -> str:
    proj = trace.to_data_js_projection()
    n_fan = sum(1 for r in proj["RATIONALES"] if r.get("considered"))
    header = (
        "/* data.js — GENERATED from a REAL live-codex EXPLAIN-mode battle "
        f"(winner={trace.result.winner}, {n_fan}/{len(proj['RATIONALES'])} decisions carry an\n"
        " * attested candidate fan). LOG = raw Showdown protocol; RATIONALES = the agent's\n"
        " * real per-decision words (codex_decide_explain) — each with the ATTESTED set of\n"
        " * other moves it weighed + why it rejected them. This file is the file://-safe\n"
        " * projection of a ReasoningTrace (adx_showdown.reasoning_trace). Do not hand-edit;\n"
        " * regenerate via tools/build_arena2d_data.py. */\n"
    )
    body = (
        "window.__ARENA2D_DATA = {\n"
        f"  LOG: {json.dumps(proj['LOG'], ensure_ascii=False)},\n"
        f"  RATIONALES: {json.dumps(proj['RATIONALES'], ensure_ascii=False)}\n"
        "};\n"
    )
    return header + body


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    src, out = Path(argv[1]), Path(argv[2])
    trace = ReasoningTrace.from_capture(json.loads(src.read_text()))
    out.write_text(render(trace))
    n_fan = sum(1 for d in trace.decisions if d.considered)
    print(
        f"wrote {out}: {len(trace.log)} log lines, {len(trace.decisions)} decisions, "
        f"{n_fan} with an attested fan (winner={trace.result.winner})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
