"""Codex battle-harness move adapter for self-play meta-harness evolution.

The arena MCP surface currently returns a compact rendered state for human and
agent clients. Lane A self-play can pass richer structured choices. This module
accepts both forms and returns a deterministic 1-based choice index suitable for
``choose_action``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BattleHarness:
    """JSON-serializable genome fragment bene mutates for battle policy."""

    harness_id: str
    system_prompt: str = ""
    move_selection_strategy: str = "max_damage"
    tool_policy: Mapping[str, Any] = field(default_factory=dict)
    params: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> BattleHarness:
        return cls(
            harness_id=str(raw.get("harness_id") or "codex-seed"),
            system_prompt=str(raw.get("system_prompt") or ""),
            move_selection_strategy=str(raw.get("move_selection_strategy") or "max_damage"),
            tool_policy=dict(raw.get("tool_policy") or {}),
            params=dict(raw.get("params") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "harness_id": self.harness_id,
            "system_prompt": self.system_prompt,
            "move_selection_strategy": self.move_selection_strategy,
            "tool_policy": dict(self.tool_policy),
            "params": dict(self.params),
        }


@dataclass(frozen=True)
class MoveOption:
    choice_index: int
    choice: str
    kind: str
    name: str = ""
    move_id: str = ""
    move_type: str = ""
    base_power: float | None = None
    accuracy: float | None = None
    effectiveness: float | None = None
    stab: bool | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MoveSelection:
    choice_index: int
    choice: str
    strategy: str
    score: float
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "choice_index": self.choice_index,
            "choice": self.choice,
            "strategy": self.strategy,
            "score": self.score,
            "rationale": self.rationale,
        }


def seed_battle_harness(strategy: str = "max_damage") -> BattleHarness:
    """Return a deterministic seed harness for bene mutation."""

    if strategy not in {"max_damage", "type_aware"}:
        raise ValueError(f"unknown seed strategy: {strategy}")
    prompt = (
        "Pick legal Pokemon Showdown moves deterministically. Prefer immediate "
        "damage; when type information is available, exploit super-effective "
        "coverage without forfeiting or stalling."
    )
    params: dict[str, Any] = {
        "stab_multiplier": 1.5,
        "switch_penalty": -25.0,
        "accuracy_weight": 0.0,
    }
    if strategy == "type_aware":
        params["type_multiplier_weight"] = 1.0
    return BattleHarness(
        harness_id=f"codex-seed-{strategy}",
        system_prompt=prompt,
        move_selection_strategy=strategy,
        tool_policy={"allow_switch": True, "lookahead_depth": 1},
        params=params,
    )


def select_codex_move(
    harness: BattleHarness | Mapping[str, Any], battle_state: Mapping[str, Any]
) -> MoveSelection:
    """Select a legal move from a harness and MCP/self-play battle state.

    Tie-breaking is stable: highest score, then lower 1-based choice index.
    """

    h = harness if isinstance(harness, BattleHarness) else BattleHarness.from_mapping(harness)
    n_choices = _n_choices(battle_state)
    if n_choices < 1:
        raise ValueError("battle state has no legal choices")

    options = _extract_options(battle_state, n_choices)
    if not options:
        options = [MoveOption(i, str(i), "unknown") for i in range(1, n_choices + 1)]

    strategy = _normalize_strategy(h.move_selection_strategy)
    scored = [(option, _score_option(strategy, option, battle_state, h)) for option in options]

    allow_switch = bool(h.tool_policy.get("allow_switch", True))
    is_force_switch = bool(
        battle_state.get("force_switch") or battle_state.get("forceSwitch", False)
    )
    if not allow_switch and not is_force_switch:
        scored = [(option, score) for option, score in scored if option.kind != "switch"]

    if not scored:
        raise ValueError("no legal choices")

    # If any damaging move exists, avoid voluntary switches unless the harness
    # explicitly biases them above moves through params.
    if any(option.kind == "move" for option, _ in scored):
        default_switch_penalty = _coerce_param(h.params, "switch_penalty", -25.0)
        scored = [
            (option, score + (default_switch_penalty if option.kind == "switch" else 0.0))
            for option, score in scored
        ]

    best, score = max(scored, key=lambda item: (item[1], -item[0].choice_index))
    return MoveSelection(
        choice_index=best.choice_index,
        choice=best.choice,
        strategy=strategy,
        score=round(score, 6),
        rationale=_rationale(strategy, best, battle_state),
    )


def _normalize_strategy(raw: str) -> str:
    strategy = raw.strip().lower().replace("-", "_")
    if strategy in {"max_damage", "type_aware"}:
        return strategy
    # Unknown evolved strings fail soft into the seed rail instead of throwing
    # away a battle; the harness_id/rationale still show what was executed.
    return "max_damage"


def _n_choices(state: Mapping[str, Any]) -> int:
    try:
        return int(state.get("n_choices") or 0)
    except (TypeError, ValueError):
        return 0


def _extract_options(state: Mapping[str, Any], n_choices: int) -> list[MoveOption]:
    for key in ("choices", "legal_choices", "available_choices", "options"):
        raw = state.get(key)
        if isinstance(raw, list) and raw:
            return [_option_from_any(item, idx + 1) for idx, item in enumerate(raw)]

    raw_moves = state.get("moves")
    if isinstance(raw_moves, list) and raw_moves:
        return [_option_from_any(item, idx + 1) for idx, item in enumerate(raw_moves)]

    rendered = state.get("state")
    if isinstance(rendered, str):
        parsed = _parse_rendered_options(rendered)
        if parsed:
            return parsed

    return [MoveOption(i, str(i), "unknown") for i in range(1, n_choices + 1)]


def _option_from_any(raw: Any, fallback_index: int) -> MoveOption:
    if isinstance(raw, str):
        return _option_from_text(fallback_index, raw)
    if not isinstance(raw, Mapping):
        return MoveOption(fallback_index, str(raw), "unknown")

    choice_idx = _first_int(raw, "choice_index") or fallback_index
    slot_or_val = _first_int(raw, "index", "slot", "choice", "choice_index") or fallback_index
    choice = str(raw.get("choice") or raw.get("command") or "")
    name = str(raw.get("name") or raw.get("move") or raw.get("move_name") or "")
    move_id = str(raw.get("id") or raw.get("move_id") or _normalize_move_id(name))
    kind = str(raw.get("kind") or raw.get("type_of_choice") or "").lower()
    if not kind:
        kind = _infer_kind(choice, name, raw)
    if not choice:
        choice = (
            f"move {slot_or_val}"
            if kind == "move"
            else f"{kind} {slot_or_val}"
            if kind
            else str(slot_or_val)
        )

    return MoveOption(
        choice_index=choice_idx,
        choice=choice,
        kind=kind,
        name=name,
        move_id=move_id,
        move_type=str(raw.get("move_type") or raw.get("type") or "").lower(),
        base_power=_first_float(raw, "base_power", "basePower", "power"),
        accuracy=_first_float(raw, "accuracy"),
        effectiveness=_first_float(raw, "effectiveness", "type_multiplier", "typeMultiplier"),
        stab=_first_bool(raw, "stab", "same_type_attack_bonus"),
        raw=raw,
    )


def _option_from_text(index: int, text: str) -> MoveOption:
    stripped = text.strip()
    kind = _infer_kind(stripped, "", {})
    name = ""
    if "—" in stripped:
        name = stripped.split("—", 1)[1].split("(", 1)[0].strip()
    elif "-" in stripped:
        name = stripped.split("-", 1)[1].split("(", 1)[0].strip()
    elif kind == "move":
        bits = stripped.split()
        if len(bits) > 2:
            name = " ".join(bits[2:])
    return MoveOption(
        choice_index=index,
        choice=_choice_token(stripped) or stripped,
        kind=kind,
        name=name,
        move_id=_normalize_move_id(name),
    )


def _parse_rendered_options(rendered: str) -> list[MoveOption]:
    options: list[MoveOption] = []
    for line in rendered.splitlines():
        match = re.match(r"^\s*(\d+)\.\s+(.+?)\s*$", line)
        if match is None:
            continue
        idx = int(match.group(1))
        options.append(_option_from_text(idx, match.group(2)))
    return options


def _score_option(
    strategy: str,
    option: MoveOption,
    state: Mapping[str, Any],
    harness: BattleHarness,
) -> float:
    if option.kind == "team":
        return 0.0
    if option.kind == "switch":
        return 0.0
    if option.kind != "move":
        return -1.0

    base_power = option.base_power if option.base_power is not None else 0.0
    if strategy == "max_damage":
        return _with_accuracy(base_power, option, harness)

    multiplier = option.effectiveness
    if multiplier is None:
        multiplier = _type_multiplier(option.move_type, _opponent_types(state))
    stab_multiplier = _coerce_param(harness.params, "stab_multiplier", 1.5, min_val=0.0)
    stab = option.stab if option.stab is not None else option.move_type in _own_types(state)
    score = base_power * multiplier * (stab_multiplier if stab and option.move_type else 1.0)
    return _with_accuracy(score, option, harness)


def _with_accuracy(score: float, option: MoveOption, harness: BattleHarness) -> float:
    weight = _coerce_param(harness.params, "accuracy_weight", 0.0, min_val=0.0, max_val=1.0)
    if weight <= 0.0 or option.accuracy is None:
        return score
    accuracy = max(0.0, min(100.0, option.accuracy)) / 100.0
    return score * ((1.0 - weight) + (weight * accuracy))


def _rationale(strategy: str, option: MoveOption, state: Mapping[str, Any]) -> str:
    if option.kind != "move":
        return f"{strategy}: selected first legal {option.kind or 'choice'}"
    if strategy == "type_aware":
        types = "/".join(_opponent_types(state)) or "unknown"
        return f"type_aware: highest deterministic damage score into {types}"
    return "max_damage: highest deterministic base-power score"


def _type_multiplier(move_type: str, defender_types: tuple[str, ...]) -> float:
    if not move_type or not defender_types:
        return 1.0
    multiplier = 1.0
    chart = _TYPE_CHART.get(move_type.lower(), {})
    for defender in defender_types:
        multiplier *= chart.get(defender.lower(), 1.0)
    return multiplier


def _opponent_types(state: Mapping[str, Any]) -> tuple[str, ...]:
    return _types_from_state(
        state,
        "opponent_types",
        "foe_types",
        "defender_types",
        nested_keys=("opponent", "foe", "defender"),
    )


def _own_types(state: Mapping[str, Any]) -> tuple[str, ...]:
    return _types_from_state(
        state, "own_types", "my_types", "attacker_types", nested_keys=("active", "self")
    )


def _types_from_state(
    state: Mapping[str, Any], *keys: str, nested_keys: tuple[str, ...] = ()
) -> tuple[str, ...]:
    for key in keys:
        value = state.get(key)
        found = _coerce_types(value)
        if found:
            return found
    for key in nested_keys:
        nested = state.get(key)
        if isinstance(nested, Mapping):
            found = _coerce_types(nested.get("types") or nested.get("type"))
            if found:
                return found
    return ()


def _coerce_types(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip().lower() for part in re.split(r"[,/ ]+", value) if part.strip())
    if isinstance(value, list | tuple):
        return tuple(str(part).strip().lower() for part in value if str(part).strip())
    return ()


def _infer_kind(choice: str, name: str, raw: Mapping[str, Any]) -> str:
    lowered = choice.lower().strip()
    if lowered.startswith("move"):
        return "move"
    if lowered.startswith("switch"):
        return "switch"
    if lowered.startswith("team"):
        return "team"
    if raw.get("base_power") is not None or raw.get("basePower") is not None or name:
        return "move"
    return "unknown"


def _choice_token(text: str) -> str:
    match = re.match(r"^(move|switch|team)\s+\d+", text.strip(), flags=re.IGNORECASE)
    return match.group(0).lower() if match else ""


def _normalize_move_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _first_int(raw: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key not in raw:
            continue
        try:
            return int(raw[key])
        except (TypeError, ValueError):
            continue
    return None


def _first_float(raw: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in raw:
            continue
        try:
            return float(raw[key])
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def _first_bool(raw: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
    return None


def _coerce_param(
    params: Mapping[str, Any],
    key: str,
    default: float,
    min_val: float | None = None,
    max_val: float | None = None,
) -> float:
    value = params.get(key)
    if value is None:
        return default
    try:
        val = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    import math

    if math.isnan(val) or math.isinf(val):
        return default
    if min_val is not None and val < min_val:
        return min_val
    if max_val is not None and val > max_val:
        return max_val
    return val


_TYPE_CHART: dict[str, dict[str, float]] = {
    "normal": {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fire": {
        "fire": 0.5,
        "water": 0.5,
        "grass": 2.0,
        "ice": 2.0,
        "bug": 2.0,
        "rock": 0.5,
        "dragon": 0.5,
        "steel": 2.0,
    },
    "water": {"fire": 2.0, "water": 0.5, "grass": 0.5, "ground": 2.0, "rock": 2.0, "dragon": 0.5},
    "electric": {
        "water": 2.0,
        "electric": 0.5,
        "grass": 0.5,
        "ground": 0.0,
        "flying": 2.0,
        "dragon": 0.5,
    },
    "grass": {
        "fire": 0.5,
        "water": 2.0,
        "grass": 0.5,
        "poison": 0.5,
        "ground": 2.0,
        "flying": 0.5,
        "bug": 0.5,
        "rock": 2.0,
        "dragon": 0.5,
        "steel": 0.5,
    },
    "ice": {
        "fire": 0.5,
        "water": 0.5,
        "grass": 2.0,
        "ice": 0.5,
        "ground": 2.0,
        "flying": 2.0,
        "dragon": 2.0,
        "steel": 0.5,
    },
    "fighting": {
        "normal": 2.0,
        "ice": 2.0,
        "poison": 0.5,
        "flying": 0.5,
        "psychic": 0.5,
        "bug": 0.5,
        "rock": 2.0,
        "ghost": 0.0,
        "dark": 2.0,
        "steel": 2.0,
        "fairy": 0.5,
    },
    "poison": {
        "grass": 2.0,
        "poison": 0.5,
        "ground": 0.5,
        "rock": 0.5,
        "ghost": 0.5,
        "steel": 0.0,
        "fairy": 2.0,
    },
    "ground": {
        "fire": 2.0,
        "electric": 2.0,
        "grass": 0.5,
        "poison": 2.0,
        "flying": 0.0,
        "bug": 0.5,
        "rock": 2.0,
        "steel": 2.0,
    },
    "flying": {
        "electric": 0.5,
        "grass": 2.0,
        "fighting": 2.0,
        "bug": 2.0,
        "rock": 0.5,
        "steel": 0.5,
    },
    "psychic": {"fighting": 2.0, "poison": 2.0, "psychic": 0.5, "dark": 0.0, "steel": 0.5},
    "bug": {
        "fire": 0.5,
        "grass": 2.0,
        "fighting": 0.5,
        "poison": 0.5,
        "flying": 0.5,
        "psychic": 2.0,
        "ghost": 0.5,
        "dark": 2.0,
        "steel": 0.5,
        "fairy": 0.5,
    },
    "rock": {
        "fire": 2.0,
        "ice": 2.0,
        "fighting": 0.5,
        "ground": 0.5,
        "flying": 2.0,
        "bug": 2.0,
        "steel": 0.5,
    },
    "ghost": {"normal": 0.0, "psychic": 2.0, "ghost": 2.0, "dark": 0.5},
    "dragon": {"dragon": 2.0, "steel": 0.5, "fairy": 0.0},
    "dark": {"fighting": 0.5, "psychic": 2.0, "ghost": 2.0, "dark": 0.5, "fairy": 0.5},
    "steel": {
        "fire": 0.5,
        "water": 0.5,
        "electric": 0.5,
        "ice": 2.0,
        "rock": 2.0,
        "steel": 0.5,
        "fairy": 2.0,
    },
    "fairy": {
        "fire": 0.5,
        "fighting": 2.0,
        "poison": 0.5,
        "dragon": 2.0,
        "dark": 2.0,
        "steel": 0.5,
    },
}
