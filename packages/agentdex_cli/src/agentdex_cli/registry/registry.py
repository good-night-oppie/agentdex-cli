"""AgentsRegistry — wraps ~/.hermes/agents_registry.json.

Reads on construction, persists on `upsert`/`remove`/`flush`. Atomic write
via temp file + rename so concurrent Hermes processes never see a partial.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

SCHEMA_VERSION = 1
DEFAULT_PATH = (
    Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "agents_registry.json"
)


@dataclass
class AgentStats:
    calls: int = 0
    last_called: float = 0.0
    avg_latency_ms: float = 0.0
    success_rate: float = 1.0


@dataclass
class SubAgent:
    name: str
    kind: Literal["hermes-agent", "cli"]
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    # hermes-agent fields
    base_url: str | None = None
    session_token: str | None = None
    # cli fields
    bridge_host: str = "127.0.0.1"
    bridge_port: int | None = None
    workdir: str | None = None
    stats: AgentStats = field(default_factory=AgentStats)

    def to_dict(self) -> dict:
        d = asdict(self)
        # never serialize the bearer in list responses; caller re-masks if needed
        return d

    @classmethod
    def from_dict(cls, data: dict) -> SubAgent:
        stats_raw = data.pop("stats", None) or {}
        return cls(stats=AgentStats(**stats_raw), **data)


class AgentsRegistry:
    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._agents: dict[str, SubAgent] = {}
        self._dirty = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self.path.exists():
                self._agents = {}
                return
            try:
                doc = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._agents = {}
                return
            agents = doc.get("agents") or []
            self._agents = {}
            for raw in agents:
                try:
                    a = SubAgent.from_dict(dict(raw))
                except (TypeError, KeyError):
                    continue
                self._agents[a.name] = a

    def _write_atomic(self) -> None:
        doc = {
            "version": SCHEMA_VERSION,
            "agents": [a.to_dict() for a in self._agents.values()],
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    # ---- public API ----

    def list_all(self) -> list[SubAgent]:
        with self._lock:
            return list(self._agents.values())

    def get(self, name: str) -> SubAgent | None:
        with self._lock:
            return self._agents.get(name)

    def upsert(self, agent: SubAgent) -> None:
        with self._lock:
            self._agents[agent.name] = agent
            self._write_atomic()

    def remove(self, name: str) -> bool:
        with self._lock:
            if name not in self._agents:
                return False
            del self._agents[name]
            self._write_atomic()
            return True

    def record_call(self, name: str, *, latency_ms: float, ok: bool) -> None:
        with self._lock:
            a = self._agents.get(name)
            if not a:
                return
            s = a.stats
            n = s.calls
            s.avg_latency_ms = (s.avg_latency_ms * n + latency_ms) / (n + 1) if n else latency_ms
            s.success_rate = (
                (s.success_rate * n + (1.0 if ok else 0.0)) / (n + 1) if n else (1.0 if ok else 0.0)
            )
            s.calls = n + 1
            s.last_called = time.time()
            self._dirty = True

    def flush(self) -> None:
        with self._lock:
            if self._dirty:
                self._write_atomic()
                self._dirty = False

    def filter_by_capability(self, tags: Iterable[str]) -> list[SubAgent]:
        tagset = {t.lower() for t in tags}
        with self._lock:
            return [
                a for a in self._agents.values() if tagset & {c.lower() for c in a.capabilities}
            ]


def load_default_registry() -> AgentsRegistry:
    return AgentsRegistry(DEFAULT_PATH)
