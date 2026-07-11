"""Curated market registry — link-out metadata only (ADR-0015 D4/D5)."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Any

import yaml

from adx_ladders.base import LadderClass


@dataclass(frozen=True)
class LadderEntry:
    """One curated ladder in the market registry."""

    id: str
    title: str
    ladder_class: LadderClass
    operator: str
    url: str
    leaderboard_url: str
    access: str
    run_adapter: bool
    notes: str


@dataclass(frozen=True)
class SubstrateEntry:
    """Non-ladder substrate (datasets / distribution / model-hosting)."""

    id: str
    title: str
    operator: str
    url: str
    access: str
    notes: str


@dataclass(frozen=True)
class Registry:
    """Loaded market registry with ladder/substrate views and id lookup."""

    ladders: tuple[LadderEntry, ...]
    substrates: tuple[SubstrateEntry, ...]

    def get(self, entry_id: str) -> LadderEntry | SubstrateEntry:
        """Look up a ladder or substrate by id. Raises KeyError if missing."""
        for ladder in self.ladders:
            if ladder.id == entry_id:
                return ladder
        for substrate in self.substrates:
            if substrate.id == entry_id:
                return substrate
        raise KeyError(f"unknown registry id: {entry_id!r}")

    def get_ladder(self, ladder_id: str) -> LadderEntry:
        for ladder in self.ladders:
            if ladder.id == ladder_id:
                return ladder
        raise KeyError(f"unknown ladder id: {ladder_id!r}")


def load_registry() -> Registry:
    """Load the packaged ``registry.yaml`` curated market."""
    raw_text = (
        resources.files("adx_ladders")
        .joinpath("registry.yaml")
        .read_text(encoding="utf-8")
    )
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise ValueError("registry.yaml must be a mapping")
    return _from_mapping(raw)


def _from_mapping(raw: dict[str, Any]) -> Registry:
    ladders_raw = raw.get("ladders") or []
    substrates_raw = raw.get("substrates") or []
    if not isinstance(ladders_raw, list):
        raise ValueError("registry.yaml 'ladders' must be a list")
    if not isinstance(substrates_raw, list):
        raise ValueError("registry.yaml 'substrates' must be a list")

    ladders = tuple(_parse_ladder(item) for item in ladders_raw)
    substrates = tuple(_parse_substrate(item) for item in substrates_raw)
    return Registry(ladders=ladders, substrates=substrates)


def _parse_ladder(item: Any) -> LadderEntry:
    if not isinstance(item, dict):
        raise ValueError("each ladder entry must be a mapping")
    class_raw = item["ladder_class"]
    try:
        ladder_class = LadderClass(class_raw)
    except ValueError as exc:
        raise ValueError(
            f"unknown ladder_class {class_raw!r}; "
            f"expected {[c.value for c in LadderClass]}"
        ) from exc
    return LadderEntry(
        id=str(item["id"]),
        title=str(item["title"]),
        ladder_class=ladder_class,
        operator=str(item["operator"]),
        url=str(item["url"]),
        leaderboard_url=str(item["leaderboard_url"]),
        access=str(item["access"]),
        run_adapter=bool(item["run_adapter"]),
        notes=str(item.get("notes") or "").strip(),
    )


def _parse_substrate(item: Any) -> SubstrateEntry:
    if not isinstance(item, dict):
        raise ValueError("each substrate entry must be a mapping")
    return SubstrateEntry(
        id=str(item["id"]),
        title=str(item["title"]),
        operator=str(item["operator"]),
        url=str(item["url"]),
        access=str(item["access"]),
        notes=str(item.get("notes") or "").strip(),
    )
