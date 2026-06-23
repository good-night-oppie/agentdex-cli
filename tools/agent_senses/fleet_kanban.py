#!/usr/bin/env python3
"""Repo-local fleet kanban for ADX dogfood feedback.

This is intentionally smaller than Hermes Kanban. It keeps the core mechanics
ADX needs now: one durable board, explicit priorities, per-agent assignees,
status moves, comments, and a deterministic markdown render.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]  # repo root (restart/CWD robustness)
DEFAULT_BOARD_PATH = _REPO_ROOT / "sweeps/adx-cli-fleet-kanban.json"
DEFAULT_MARKDOWN_PATH = _REPO_ROOT / "sweeps/2026-06-16-adx-cli-fleet-kanban.md"
DEFAULT_ACTOR = os.environ.get("HARNESS_A2A_AGENT") or os.environ.get("USER") or "agent"

STATUSES = ("triage", "todo", "ready", "running", "blocked", "review", "done", "archived")
PRIORITIES = ("P0", "P1", "P2")
PRIORITY_SORT = {priority: index for index, priority in enumerate(PRIORITIES)}
STATUS_SORT = {status: index for index, status in enumerate(STATUSES)}


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_slug() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def load_board(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"board not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _try_mirror_to_ktui(board: dict[str, Any]) -> None:
    """Best-effort mirror to ktui SQLite via the harness-engineering kanban_store
    adapter (Phase A; per migration design Workflow wf_e45ce0be-1eb). The
    canonical JSON write is the contract; this is a derived view that lags JSON
    by one write. Any failure — adapter absent (CI checkouts that don't include
    harness-engineering), ktui binary missing, board create failure, config
    rollback (backend=json-only) — is SILENT. The JSON path is unaffected.

    Rollback (R1, <60s): `echo "backend=json-only" > ~/.config/fleet/kanban.conf`
    and the next write skips the mirror.
    """
    try:
        import os
        import sys

        store_path = os.path.expanduser("~/gh/harness-engineering/scripts")
        if store_path not in sys.path:
            sys.path.insert(0, store_path)
        from kanban_store import mirror_to_ktui  # type: ignore[import-not-found]

        mirror_to_ktui(board)
    except Exception:  # noqa: BLE001 — mirror is best-effort by contract
        pass


def write_board(path: Path, board: dict[str, Any]) -> None:
    validate_board(board)
    board["updated_at"] = now_utc()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(board, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    # Phase A v0.1: best-effort ktui mirror (after the canonical JSON write
    # succeeds; never blocks the write contract). See _try_mirror_to_ktui above.
    _try_mirror_to_ktui(board)


def backup_existing_board(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.bak.{timestamp_slug()}")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak.{timestamp_slug()}.{counter}")
        counter += 1
    shutil.copy2(path, backup)
    return backup


def is_default_board_path(path: Path) -> bool:
    try:
        return path.resolve() == DEFAULT_BOARD_PATH.resolve()
    except OSError:
        return path == DEFAULT_BOARD_PATH


@contextlib.contextmanager
def board_lock(path: Path):
    """Exclusive process lock for read-modify-write board updates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a", encoding="utf-8") as lock_file:
        try:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        except ImportError:
            fcntl = None  # type: ignore[assignment]
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def maybe_render_after_write(path: Path, board: dict[str, Any], markdown: str | None) -> None:
    """Refresh the markdown view for the default board or an explicit path."""
    output = Path(markdown) if markdown else None
    if output is None and is_default_board_path(path):
        output = DEFAULT_MARKDOWN_PATH
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(board), encoding="utf-8")


def validate_board(board: dict[str, Any]) -> None:
    if board.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    seen: set[str] = set()
    for card in board.get("cards", []):
        card_id = card.get("id")
        if not card_id or card_id in seen:
            raise ValueError(f"duplicate or missing card id: {card_id!r}")
        seen.add(card_id)
        if card.get("priority") not in PRIORITIES:
            raise ValueError(f"{card_id}: invalid priority {card.get('priority')!r}")
        if card.get("status") not in STATUSES:
            raise ValueError(f"{card_id}: invalid status {card.get('status')!r}")
        if not card.get("assignee"):
            raise ValueError(f"{card_id}: assignee is required")


def append_event(
    board: dict[str, Any],
    *,
    action: str,
    actor: str,
    card_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    board.setdefault("events", []).append(
        {
            "created_at": now_utc(),
            "action": action,
            "actor": actor,
            "card_id": card_id,
            "detail": detail or {},
        }
    )


def find_card(board: dict[str, Any], card_id: str) -> dict[str, Any]:
    for card in board.get("cards", []):
        if card.get("id") == card_id:
            return card
    raise KeyError(f"card not found: {card_id}")


def next_card_id(board: dict[str, Any], priority: str) -> str:
    prefix = f"ADX-{priority}-"
    highest = 0
    for card in board.get("cards", []):
        card_id = str(card.get("id", ""))
        if not card_id.startswith(prefix):
            continue
        try:
            highest = max(highest, int(card_id.removeprefix(prefix)))
        except ValueError:
            continue
    return f"{prefix}{highest + 1:03d}"


def filtered_cards(
    board: dict[str, Any],
    *,
    agent: str | None = None,
    status: str | None = None,
    priority: str | None = None,
) -> list[dict[str, Any]]:
    cards = list(board.get("cards", []))
    if agent:
        cards = [card for card in cards if card.get("assignee") == agent]
    if status:
        cards = [card for card in cards if card.get("status") == status]
    if priority:
        cards = [card for card in cards if card.get("priority") == priority]
    return sorted(
        cards,
        key=lambda card: (
            PRIORITY_SORT.get(str(card.get("priority")), 99),
            STATUS_SORT.get(str(card.get("status")), 99),
            str(card.get("id", "")),
        ),
    )


def render_markdown(board: dict[str, Any]) -> str:
    validate_board(board)
    lines: list[str] = [
        "---",
        'title: "ADX CLI fleet kanban"',
        "status: active",
        "owner: etang",
        "created: 2026-06-16",
        "updated: 2026-06-16",
        "type: reference",
        "scope: monorepo",
        "layer: cross-cutting",
        "cross_cutting: true",
        "---",
        "",
        "# ADX CLI fleet kanban",
        "",
        "This board is the shared intake for ADX CLI dogfood feedback. It replaces",
        "cascading verdict pushes with prioritized cards that each fleet agent can",
        "claim, move, and comment on.",
        "",
        "## Operating rules",
        "",
        "- A2A inbox remains the per-agent message demux; this board is the durable work queue.",
        "- New findings land as `triage`; harness promotes only the next focused card to `ready`.",
        "- `adx-cli` should normally have one `running` card at a time to avoid context drift.",
        "- Evidence stays on the card as pass IDs, commands, paths, traces, or replay IDs.",
        "- Mutating commands append JSON events so board changes are attributable.",
        "- Mutating commands take a file lock; do not hand-edit JSON during active fleet use.",
        "- `init --force` writes a timestamped JSON backup before replacing an existing board.",
        "- A2A/tmux updates should summarize board deltas, not resend every raw verdict.",
        "- When a fix lands, move the card to `review`; verifier moves it to `done` or `blocked`.",
        "",
        "## Commands",
        "",
        "```bash",
        "uv run --project ~/gh/bene-main python /home/admin/gh/harness-engineering/scripts/a2a_inbox.py --base adx-cli --count",
        "python3 tools/agent_senses/fleet_kanban.py list --agent adx-cli",
        "python3 tools/agent_senses/fleet_kanban.py move ADX-P0-001 --status running --agent adx-cli --author adx-cli",
        "python3 tools/agent_senses/fleet_kanban.py comment ADX-P0-001 --author codex --body 'repro refreshed'",
        "# Default-board mutations auto-refresh the markdown view.",
        "```",
        "",
        "## By Status",
        "",
    ]

    for status in STATUSES:
        cards = filtered_cards(board, status=status)
        if not cards:
            continue
        lines.append(f"### {status}")
        lines.append("")
        lines.append("| ID | Pri | Assignee | Lane | Title | Evidence |")
        lines.append("|---|---|---|---|---|---|")
        for card in cards:
            evidence = ", ".join(card.get("evidence", []))
            lines.append(
                "| {id} | {priority} | {assignee} | {lane} | {title} | {evidence} |".format(
                    id=card["id"],
                    priority=card["priority"],
                    assignee=card["assignee"],
                    lane=card.get("lane", ""),
                    title=card["title"].replace("|", "\\|"),
                    evidence=evidence.replace("|", "\\|"),
                )
            )
        lines.append("")

    lines.extend(["## Card Detail", ""])
    for card in filtered_cards(board):
        lines.extend(
            [
                f"### {card['id']} - {card['title']}",
                "",
                f"- Priority: `{card['priority']}`",
                f"- Status: `{card['status']}`",
                f"- Assignee: `{card['assignee']}`",
                f"- Lane: `{card.get('lane', '')}`",
                f"- Impact: {card.get('impact', '')}",
                f"- Suggested fix: {card.get('fix', '')}",
                f"- Evidence: {', '.join(card.get('evidence', []))}",
            ]
        )
        comments = card.get("comments", [])
        if comments:
            lines.append(
                "- Recent comments: "
                + " / ".join(
                    (
                        f"{comment.get('author')}: {comment.get('body')}"
                        if isinstance(comment, dict)
                        else str(comment)
                    )
                    for comment in comments[-3:]
                )
            )
        lines.append("")

    events = board.get("events", [])[-12:]
    if events:
        lines.extend(["## Recent Events", ""])
        lines.append("| Time | Action | Actor | Card | Detail |")
        lines.append("|---|---|---|---|---|")
        for event in events:
            detail = json.dumps(event.get("detail", {}), sort_keys=True)
            lines.append(
                "| {created_at} | {action} | {actor} | {card_id} | {detail} |".format(
                    created_at=str(event.get("created_at", "")),
                    action=str(event.get("action", "")),
                    actor=str(event.get("actor", "")),
                    card_id=str(event.get("card_id") or ""),
                    detail=detail.replace("|", "\\|"),
                )
            )
        lines.append("")

    lines.extend(
        [
            "## Source Pattern",
            "",
            "Adapted from Hermes Kanban's useful primitives: durable board slugs,",
            "explicit statuses, priorities, assignees, comments/events, and per-profile",
            "worker isolation. ADX keeps v1 file-backed so every fleet agent can use it",
            "from the shared repo without a new daemon.",
            "",
        ]
    )
    return "\n".join(lines)


def make_seed_board() -> dict[str, Any]:
    ts = now_utc()
    base = {
        "schema_version": 1,
        "board": "adx-cli-global-feedback",
        "updated_at": ts,
        "agents": ["harness", "adx-cli", "codex", "bene", "bene-core", "shellfish", "eddie-agi-kb"],
        "events": [],
        "cards": [],
    }
    cards = [
        {
            "id": "ADX-P0-001",
            "title": "Make arena receipts atomic before claiming honesty",
            "priority": "P0",
            "status": "ready",
            "lane": "integrity",
            "assignee": "adx-cli",
            "impact": "Human owner and agent both receive durable receipts that can be false or partial when EventLog, sidecar, or rating writes fail.",
            "fix": "Group side effects behind an atomic write plan: validate and reserve first, then commit event/replay/rating/badge together or compensate visibly.",
            "evidence": ["pass27", "pass28", "pass37", "pass38", "pass39", "pass40"],
        },
        {
            "id": "ADX-P1-001",
            "title": "Stop spending rated/evolution/badge quota before work is accepted",
            "priority": "P1",
            "status": "todo",
            "lane": "fairness",
            "assignee": "adx-cli",
            "impact": "Owner pays scarce monthly quota for invalid teams, capacity failures, sidecar failures, and signer failures.",
            "fix": "Move quota debit after validation and successful durable acceptance, or add explicit refund records on retryable failures.",
            "evidence": ["pass26", "pass33", "pass34", "pass35", "pass36"],
        },
        {
            "id": "ADX-P1-002",
            "title": "Make owner export include replay, badge, and rating lineage",
            "priority": "P1",
            "status": "todo",
            "lane": "owner-data",
            "assignee": "adx-cli",
            "impact": "Human owner and agent cannot reconstruct paid/rated history from `/my/events` or local SQLite.",
            "fix": "Select events by canonical agent/battle joins and nested period payloads, not only top-level tenant_id.",
            "evidence": ["pass17", "pass19", "pass20", "pass21", "pass41", "pass42-candidate"],
        },
        {
            "id": "ADX-P1-003",
            "title": "Make observability acceptance fail when traces are absent",
            "priority": "P1",
            "status": "todo",
            "lane": "observability",
            "assignee": "harness",
            "impact": "The platform can pass trace-propagation tests while producing no usable trace/span link.",
            "fix": "Require actual trace context/link presence in acceptance tests; document fallback mode separately.",
            "evidence": ["pass31", "pass32"],
        },
        {
            "id": "ADX-P1-004",
            "title": "Tighten admin surface and auth-before-parse contract",
            "priority": "P1",
            "status": "todo",
            "lane": "security",
            "assignee": "adx-cli",
            "impact": "Operator-only endpoints are exposed in public OpenAPI and one documented auth ordering claim is false for malformed JSON.",
            "fix": "Hide or split admin OpenAPI, then test auth rejection before body validation for protected routes.",
            "evidence": ["pass24", "pass25"],
        },
        {
            "id": "ADX-P2-001",
            "title": "Reduce starter and CLI footguns for visiting agents",
            "priority": "P2",
            "status": "triage",
            "lane": "agent-ux",
            "assignee": "codex",
            "impact": "Agents hit stale docs, missing `adx` arena commands, traceback setup errors, and asymmetric MCP proxy behavior.",
            "fix": "Update `/skill.md`, add or explicitly defer `adx arena` commands, normalize starter-kit errors, and test missing battle IDs.",
            "evidence": ["pass14", "pass15", "pass16", "pass29"],
        },
        {
            "id": "ADX-P2-002",
            "title": "Make arena gameplay feedback more legible and less first-legal",
            "priority": "P2",
            "status": "triage",
            "lane": "gameplay",
            "assignee": "codex",
            "impact": "Agents can win or lose for shallow reasons and cannot always understand losses from state/replay alone.",
            "fix": "Repair gym mapping, expose opponent HP/recent turns, enrich replay metadata, and test anchor/gym coverage.",
            "evidence": ["pass2", "pass3", "pass4", "pass6", "pass7", "pass8", "pass12", "pass13"],
        },
        {
            "id": "ADX-P2-003",
            "title": "Preserve verified strengths while fixing gaps",
            "priority": "P2",
            "status": "done",
            "lane": "regression-guard",
            "assignee": "harness",
            "impact": "Known-good surfaces are easy to break while fixing adjacent defects.",
            "fix": "Keep recompute ladder, anti-pay-to-rank property tests, `/whoami` redaction, team validation, and local log idempotence in the regression suite.",
            "evidence": ["pass5", "pass11", "pass22", "pass23", "pass30"],
        },
    ]
    for card in cards:
        card["created_by"] = "codex"
        card["updated_at"] = ts
        card["comments"] = []
    base["cards"] = cards
    append_event(base, action="seed", actor="codex", detail={"cards": len(cards)})
    return base


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    with board_lock(path):
        if path.exists() and not args.force:
            print(f"board exists: {path}", file=sys.stderr)
            return 2
        backup = backup_existing_board(path) if args.force else None
        board = make_seed_board()
        append_event(
            board,
            action="init",
            actor=args.author,
            detail={"force": args.force, "backup": str(backup) if backup else None},
        )
        write_board(path, board)
        if args.render:
            Path(args.markdown).write_text(render_markdown(board), encoding="utf-8")
    print(f"initialized {path}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    board = load_board(Path(args.path))
    cards = filtered_cards(board, agent=args.agent, status=args.status, priority=args.priority)
    if args.json:
        print(json.dumps(cards, indent=2, sort_keys=True))
        return 0
    for card in cards:
        print(
            f"{card['id']} {card['priority']} {card['status']} "
            f"{card['assignee']} {card.get('lane', '')}: {card['title']}"
        )
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    path = Path(args.path)
    with board_lock(path):
        board = load_board(path)
        card_id = args.id or next_card_id(board, args.priority)
        board.setdefault("cards", []).append(
            {
                "id": card_id,
                "title": args.title,
                "priority": args.priority,
                "status": args.status,
                "lane": args.lane,
                "assignee": args.agent,
                "impact": args.impact,
                "fix": args.fix,
                "evidence": [item.strip() for item in args.evidence.split(",") if item.strip()],
                "created_by": args.author,
                "updated_at": now_utc(),
                "comments": [],
            }
        )
        append_event(board, action="add", actor=args.author, card_id=card_id)
        write_board(path, board)
        maybe_render_after_write(path, board, args.markdown)
    print(card_id)
    return 0


def _probe_gate_allows_done(card: dict[str, Any], card_id: str, board_path: Path) -> str | None:
    """Return an error message if a probe-gated card may NOT move to ``done``, else ``None``.

    A card carrying an authored probe (``card['probes']['probe']``) may only reach
    ``done`` through ``kanban_probe_gate.py`` (probe ACCEPT + dual approval). This
    closes the bypass where an agent flips ``status=done`` directly via this mover,
    skipping the gate entirely. Cards with no authored probe are unaffected (legacy
    behaviour). Fail-closed: a probe-gated card whose gate cannot be located or run
    is refused, never waved through.
    """
    if not (card.get("probes") or {}).get("probe"):
        return None  # ungated legacy card — no probe authored
    override = os.environ.get("KANBAN_PROBE_GATE")
    candidates = [override] if override else []
    candidates += [
        str(Path.home() / "gh/harness-engineering/scripts/kanban_probe_gate.py"),
        str(Path.home() / "gh/eddie-agi-kb/scripts/kanban_probe_gate.py"),
    ]
    gate_path = next((c for c in candidates if c and Path(c).is_file()), None)
    if not gate_path:
        return (
            f"{card_id} carries an authored probe but kanban_probe_gate.py was not "
            "found; refusing un-gated done. Set KANBAN_PROBE_GATE to the gate path."
        )
    runner = os.environ.get(
        "KANBAN_PROBE_GATE_RUN", "uv run --no-project --with bene==0.2.1 python"
    )
    proc = subprocess.run(
        [*shlex.split(runner), gate_path, "gate-done", card_id],
        env={**os.environ, "KANBAN_BOARD": str(board_path)},
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        lines = (proc.stdout or proc.stderr or "").strip().splitlines()
        return f"{card_id} blocked by card-DONE gate: {lines[-1] if lines else f'rc={proc.returncode}'}"
    return None


def cmd_move(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if args.status == "done":
        block = _probe_gate_allows_done(
            find_card(load_board(path), args.card_id), args.card_id, path
        )
        if block:
            print(f"REFUSED: {block}", file=sys.stderr)
            return 13
    with board_lock(path):
        board = load_board(path)
        card = find_card(board, args.card_id)
        before = {"status": card["status"], "assignee": card["assignee"]}
        card["status"] = args.status
        if args.agent:
            card["assignee"] = args.agent
        card["updated_at"] = now_utc()
        append_event(
            board,
            action="move",
            actor=args.author,
            card_id=card["id"],
            detail={
                "before": before,
                "after": {"status": card["status"], "assignee": card["assignee"]},
            },
        )
        write_board(path, board)
        maybe_render_after_write(path, board, args.markdown)
    print(f"{card['id']} -> {card['status']} ({card['assignee']})")
    return 0


def cmd_comment(args: argparse.Namespace) -> int:
    path = Path(args.path)
    with board_lock(path):
        board = load_board(path)
        card = find_card(board, args.card_id)
        card.setdefault("comments", []).append(
            {"author": args.author, "body": args.body, "created_at": now_utc()}
        )
        card["updated_at"] = now_utc()
        append_event(board, action="comment", actor=args.author, card_id=card["id"])
        write_board(path, board)
        maybe_render_after_write(path, board, args.markdown)
    print(f"commented {card['id']}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    board = load_board(Path(args.path))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(board), encoding="utf-8")
    print(f"rendered {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repo-local fleet kanban for ADX CLI")
    parser.add_argument("--path", default=str(DEFAULT_BOARD_PATH), help="board JSON path")
    parser.add_argument(
        "--markdown",
        help=(
            "markdown output to refresh after add/move/comment; defaults to the "
            "canonical sweeps markdown when --path is the canonical board"
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="initialize the seeded board")
    init.add_argument("--force", action="store_true")
    init.add_argument("--render", action="store_true")
    init.add_argument("--markdown", default=str(DEFAULT_MARKDOWN_PATH))
    init.add_argument("--author", default=DEFAULT_ACTOR)
    init.set_defaults(func=cmd_init)

    list_cmd = sub.add_parser("list", help="list cards")
    list_cmd.add_argument("--agent")
    list_cmd.add_argument("--status", choices=STATUSES)
    list_cmd.add_argument("--priority", choices=PRIORITIES)
    list_cmd.add_argument("--json", action="store_true")
    list_cmd.set_defaults(func=cmd_list)

    add = sub.add_parser("add", help="add a card")
    add.add_argument("--id")
    add.add_argument("--title", required=True)
    add.add_argument("--priority", required=True, choices=PRIORITIES)
    add.add_argument("--status", default="triage", choices=STATUSES)
    add.add_argument("--lane", required=True)
    add.add_argument("--agent", required=True)
    add.add_argument("--impact", required=True)
    add.add_argument("--fix", required=True)
    add.add_argument("--evidence", default="")
    add.add_argument("--author", default=DEFAULT_ACTOR)
    add.set_defaults(func=cmd_add)

    move = sub.add_parser("move", help="move or reassign a card")
    move.add_argument("card_id")
    move.add_argument("--status", required=True, choices=STATUSES)
    move.add_argument("--agent")
    move.add_argument("--author", default=DEFAULT_ACTOR)
    move.set_defaults(func=cmd_move)

    comment = sub.add_parser("comment", help="append a card comment")
    comment.add_argument("card_id")
    comment.add_argument("--author", required=True)
    comment.add_argument("--body", required=True)
    comment.set_defaults(func=cmd_comment)

    render = sub.add_parser("render", help="render markdown from the board")
    render.add_argument("--output", default=str(DEFAULT_MARKDOWN_PATH))
    render.set_defaults(func=cmd_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"fleet-kanban: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
