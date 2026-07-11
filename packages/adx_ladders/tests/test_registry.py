"""Unit tests for the curated market registry."""

from __future__ import annotations

from adx_frontier.candidate import KNOWN_LADDERS
from adx_ladders.base import LadderClass
from adx_ladders.registry import LadderEntry, SubstrateEntry, load_registry


def test_registry_loads() -> None:
    registry = load_registry()
    assert len(registry.ladders) == 6
    assert len(registry.substrates) == 1


def test_six_ladders_plus_one_substrate() -> None:
    registry = load_registry()
    ladder_ids = [ladder.id for ladder in registry.ladders]
    substrate_ids = [substrate.id for substrate in registry.substrates]
    assert ladder_ids == [
        "kaggle",
        "arc-agi-3",
        "pokeagent-gen1ou",
        "swe-bench-pro",
        "tb2",
        "webarena",
    ]
    assert substrate_ids == ["huggingface"]


def test_class_assignments_match_adr_d4() -> None:
    """ADR D4: live-adversarial vs static taxonomy exactly."""
    registry = load_registry()
    by_id = {ladder.id: ladder for ladder in registry.ladders}

    live = {"kaggle", "arc-agi-3", "pokeagent-gen1ou"}
    static = {"swe-bench-pro", "tb2", "webarena"}

    for ladder_id in live:
        assert by_id[ladder_id].ladder_class is LadderClass.LIVE_ADVERSARIAL
    for ladder_id in static:
        assert by_id[ladder_id].ladder_class is LadderClass.STATIC

    # HuggingFace is a substrate, not a ladder lane.
    assert all(ladder.id != "huggingface" for ladder in registry.ladders)
    assert registry.substrates[0].id == "huggingface"
    assert isinstance(registry.substrates[0], SubstrateEntry)


def test_v1_run_adapters() -> None:
    """ADR D5: only tb2, arc-agi-3, pokeagent-gen1ou have run_adapter=true."""
    registry = load_registry()
    enabled = {ladder.id for ladder in registry.ladders if ladder.run_adapter}
    assert enabled == {"tb2", "arc-agi-3", "pokeagent-gen1ou"}


def test_known_ladders_consistency() -> None:
    """Registry ladder ids MUST be a superset of adx_frontier KNOWN_LADDERS."""
    registry = load_registry()
    registry_ids = {ladder.id for ladder in registry.ladders}
    missing = KNOWN_LADDERS - registry_ids
    assert not missing, f"KNOWN_LADDERS missing from registry: {sorted(missing)}"


def test_lookup_by_id() -> None:
    registry = load_registry()
    ladder = registry.get("tb2")
    assert isinstance(ladder, LadderEntry)
    assert ladder.ladder_class is LadderClass.STATIC
    assert ladder.run_adapter is True

    substrate = registry.get("huggingface")
    assert isinstance(substrate, SubstrateEntry)
    assert substrate.url.startswith("https://")

    # Substrates have no leaderboard_url / ladder_class / run_adapter fields.
    assert not hasattr(substrate, "leaderboard_url")
    assert not hasattr(substrate, "ladder_class")
    assert not hasattr(substrate, "run_adapter")
