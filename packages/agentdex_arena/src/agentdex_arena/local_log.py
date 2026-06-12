"""Client-side local battle log — the SQLite half of the two-tier design (P4).

A user running their own agent keeps `~/.adx/arena.sqlite`: their agents' own
chain rows (pulled tenant-scoped from the gateway's `/my/events`), materialized
into an append-only local table. Sync is an idempotent set-union on
(battle_id, seq) — no last-writer-wins, no merge; re-pulling is a no-op. The
agent owns its data offline: replays, fork provenance, and the per-battle
story survive the server, and `recent_story` rebuilds a battle's trail without
any network.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_DB = Path.home() / ".adx" / "arena.sqlite"

_SCHEMA = """
create table if not exists arena_events (
  battle_id   text not null,
  seq         integer not null,
  event_type  text not null,
  prev_digest text not null default '',
  payload     text not null default '{}',
  primary key (battle_id, seq)
);
create index if not exists idx_local_events_type on arena_events(event_type);
"""


def _connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    return conn


def store_events(events: list[dict[str, Any]], db_path: str | Path = DEFAULT_DB) -> int:
    """Idempotently materialize chain events; returns how many were new."""
    conn = _connect(db_path)
    try:
        new = 0
        for ev in events:
            payload = ev.get("payload") or {}
            cur = conn.execute(
                "insert or ignore into arena_events"
                " (battle_id, seq, event_type, prev_digest, payload) values (?,?,?,?,?)",
                (
                    str(payload.get("battle_id") or "_ladder"),
                    int(ev["seq"]),
                    str(ev["type"]),
                    str(ev.get("prev", "")),
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
            )
            new += cur.rowcount
        conn.commit()
        return new
    finally:
        conn.close()


def max_seq(db_path: str | Path = DEFAULT_DB) -> int:
    conn = _connect(db_path)
    try:
        row = conn.execute("select coalesce(max(seq), -1) from arena_events").fetchone()
        return int(row[0])
    finally:
        conn.close()


def pull(base_url: str, token: str, db_path: str | Path = DEFAULT_DB) -> int:
    """Pull all of MY missing events from the gateway into the local SQLite.

    Pages by chain seq from the local high-water mark; the server scopes rows to
    the consent token's tenant, so the local db only ever holds your own data.
    """
    import httpx

    total = 0
    since = max_seq(db_path)
    with httpx.Client(base_url=base_url, timeout=30) as client:
        while True:
            r = client.post("/my/events", json={"token": token, "since_seq": since})
            r.raise_for_status()
            body = r.json()
            events = body.get("events", [])
            if not events:
                break
            total += store_events(events, db_path)
            since = int(body["next_since_seq"])
    return total


def battles(db_path: str | Path = DEFAULT_DB) -> list[dict[str, Any]]:
    """One row per battle with outcome + fork provenance — the offline Pokédex."""
    conn = _connect(db_path)
    try:
        out = []
        for (battle_id,) in conn.execute(
            "select distinct battle_id from arena_events where battle_id != '_ladder'"
            " order by battle_id"
        ):
            end = conn.execute(
                "select payload from arena_events where battle_id=? and event_type='battle_end'",
                (battle_id,),
            ).fetchone()
            fork = conn.execute(
                "select payload from arena_events where battle_id=? and event_type='battle_fork'",
                (battle_id,),
            ).fetchone()
            row: dict[str, Any] = {"battle_id": battle_id}
            if end:
                row.update(json.loads(end[0]))
            if fork:
                fp = json.loads(fork[0])
                row["parent_battle_id"] = fp.get("parent_battle_id")
                row["fork_turn"] = fp.get("fork_turn")
            out.append(row)
        return out
    finally:
        conn.close()


def recent_story(battle_id: str, db_path: str | Path = DEFAULT_DB) -> list[str]:
    """Rebuild a battle's turn-by-turn choice trail from the local log, offline."""
    conn = _connect(db_path)
    try:
        lines = []
        for (payload,) in conn.execute(
            "select payload from arena_events where battle_id=? and event_type='battle'"
            " order by seq",
            (battle_id,),
        ):
            p = json.loads(payload)
            foe = f" (foe {p['foe_hp_pct']}%)" if p.get("foe_hp_pct") is not None else ""
            lines.append(f"T{p.get('turn')}: {p.get('choice')}{foe}")
        return lines
    finally:
        conn.close()
