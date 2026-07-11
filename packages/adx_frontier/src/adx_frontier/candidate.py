"""AgentCandidate manifest load + pre-run validation gate (ADR-0015 D1).

The frontier must be ungameable by proxy-winners: reject before any run starts
when weco --sources limits, declared budget, or axes-partition keys fail.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

KNOWN_LADDERS: frozenset[str] = frozenset(
    {
        "tb2",
        "arc-agi-3",
        "pokeagent-gen1ou",
        "kaggle",
        "swe-bench-pro",
        "webarena",
    }
)

FRONTIER_AXES: tuple[str, ...] = ("quality", "cost_dollar", "wall_clock_sec")

_MAX_MUTABLE_FILES = 10
_MAX_BYTES_PER_FILE = 200 * 1024  # 200 KiB
_MAX_BYTES_TOTAL = 500 * 1024  # 500 KiB


class CandidateValidationError(ValueError):
    """Raised when an AgentCandidate fails the pre-run validation gate."""


@dataclass(frozen=True)
class Budget:
    usd: float
    wall_clock_min: float


@dataclass(frozen=True)
class AgentCandidate:
    """Directory-backed agent manifest (DESIGN.md AgentCandidate schema)."""

    name: str
    entrypoint: str
    mutable: tuple[str, ...]
    base_model: str
    budget: Budget
    ladders: tuple[str, ...]
    root: Path

    def expand_mutable(self) -> list[Path]:
        """Expand ``mutable`` globs against ``root`` to concrete files.

        Absolute patterns and paths that resolve outside ``root`` (symlink
        escapes, ``../`` traversal) raise ``CandidateValidationError``.
        """
        found: set[Path] = set()
        root_resolved = self.root.resolve()
        for pattern in self.mutable:
            if not isinstance(pattern, str) or not pattern.strip():
                raise CandidateValidationError(
                    f"mutable glob must be a non-empty relative string (got {pattern!r})"
                )
            # Absolute patterns raise NotImplementedError from Path.glob on
            # some Python versions; reject them explicitly for a clean gate.
            if pattern.startswith(("/", "\\")) or Path(pattern).is_absolute():
                raise CandidateValidationError(
                    f"mutable glob must be relative to candidate root "
                    f"(got absolute pattern {pattern!r})"
                )
            try:
                matches = list(self.root.glob(pattern))
            except (NotImplementedError, ValueError, OSError) as exc:
                raise CandidateValidationError(
                    f"invalid mutable glob {pattern!r}: {exc}"
                ) from exc
            matched_files = 0
            for path in matches:
                # Follow symlinks via resolve(); reject anything outside root.
                if not path.is_file():
                    continue
                try:
                    resolved = path.resolve()
                except OSError as exc:
                    raise CandidateValidationError(
                        f"mutable path could not be resolved: {path}: {exc}"
                    ) from exc
                if not _is_under_root(resolved, root_resolved):
                    raise CandidateValidationError(
                        f"mutable path escapes candidate root: {resolved} "
                        f"(pattern {pattern!r})"
                    )
                found.add(resolved)
                matched_files += 1
            if matched_files == 0:
                raise CandidateValidationError(
                    f"mutable glob {pattern!r} matched zero files under candidate root"
                )
        return sorted(found)

    def validate(self) -> None:
        """Pre-run gate. Raises ``CandidateValidationError`` on any violation."""
        if not self.name or not str(self.name).strip():
            raise CandidateValidationError("name must be a non-empty string")
        if _has_invisible_format_chars(str(self.name)):
            raise CandidateValidationError(
                "name must not contain invisible Unicode format characters "
                "(e.g. zero-width space)"
            )
        if not self.entrypoint or not str(self.entrypoint).strip():
            raise CandidateValidationError("entrypoint must be a non-empty string")
        if not self.base_model or not str(self.base_model).strip():
            raise CandidateValidationError("base_model must be a non-empty string")
        if not self.mutable:
            raise CandidateValidationError(
                "mutable must be a non-empty list of glob patterns"
            )
        if not self.ladders:
            raise CandidateValidationError("ladders must be a non-empty list")
        unknown = [ladder for ladder in self.ladders if ladder not in KNOWN_LADDERS]
        if unknown:
            raise CandidateValidationError(
                f"unknown ladder(s): {unknown}; known={sorted(KNOWN_LADDERS)}"
            )
        if (
            not math.isfinite(self.budget.usd)
            or not math.isfinite(self.budget.wall_clock_min)
            or self.budget.usd <= 0
            or self.budget.wall_clock_min <= 0
        ):
            raise CandidateValidationError(
                "budget.usd and budget.wall_clock_min must both be finite and > 0 "
                f"(got usd={self.budget.usd}, wall_clock_min={self.budget.wall_clock_min})"
            )
        self._validate_weco_mutable_limits()

    def _validate_weco_mutable_limits(self) -> None:
        files = self.expand_mutable()
        n_files = len(files)
        sizes = [path.stat().st_size for path in files]
        total = sum(sizes)
        root_resolved = self.root.resolve()
        oversized = [
            (_safe_relpath(path, root_resolved), size)
            for path, size in zip(files, sizes, strict=True)
            if size > _MAX_BYTES_PER_FILE
        ]

        violations: list[str] = []
        if n_files > _MAX_MUTABLE_FILES:
            violations.append(f"file_count={n_files} (max {_MAX_MUTABLE_FILES})")
        if oversized:
            detail = ", ".join(f"{name}={size}B" for name, size in oversized)
            violations.append(
                f"per-file size > {_MAX_BYTES_PER_FILE}B: {detail}"
            )
        if total > _MAX_BYTES_TOTAL:
            violations.append(f"total_bytes={total} (max {_MAX_BYTES_TOTAL})")

        if violations:
            raise CandidateValidationError(
                "narrow your weco-mutable subset: "
                + "; ".join(violations)
                + f" (expanded {n_files} files, {total} bytes total)"
            )


def _has_invisible_format_chars(value: str) -> bool:
    """True if ``value`` contains Unicode format (Cf) chars such as U+200B."""
    return any(unicodedata.category(ch) == "Cf" for ch in value)


def _is_under_root(path: Path, root: Path) -> bool:
    """Return True iff ``path`` is ``root`` or a descendant (after resolve)."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_relpath(path: Path, root: Path) -> str:
    """Display path relative to root without raising on out-of-root paths."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def load_candidate(dir_path: str | Path) -> AgentCandidate:
    """Parse ``candidate.yaml`` under ``dir_path`` into an ``AgentCandidate``."""
    root = Path(dir_path).resolve()
    manifest_path = root / "candidate.yaml"
    if not manifest_path.is_file():
        raise CandidateValidationError(f"missing candidate.yaml in {root}")

    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CandidateValidationError("candidate.yaml must be a mapping")

    return _from_mapping(raw, root)


def _from_mapping(raw: dict[str, Any], root: Path) -> AgentCandidate:
    name = raw.get("name", "")
    entrypoint = raw.get("entrypoint", "")
    base_model = raw.get("base_model", "")
    mutable_raw = raw.get("mutable") or []
    ladders_raw = raw.get("ladders") or []

    if not isinstance(mutable_raw, list):
        raise CandidateValidationError("mutable must be a list of glob strings")
    if not isinstance(ladders_raw, list):
        raise CandidateValidationError("ladders must be a list of ladder ids")

    budget_raw = raw.get("budget")
    if budget_raw is None:
        raise CandidateValidationError("budget is required (usd, wall_clock_min)")
    if not isinstance(budget_raw, dict):
        raise CandidateValidationError("budget must be a mapping with usd and wall_clock_min")
    if "usd" not in budget_raw or "wall_clock_min" not in budget_raw:
        raise CandidateValidationError(
            "budget must include both usd and wall_clock_min"
        )

    try:
        usd = float(budget_raw["usd"])
        wall_clock_min = float(budget_raw["wall_clock_min"])
    except (TypeError, ValueError) as exc:
        raise CandidateValidationError(
            f"budget.usd and budget.wall_clock_min must be numbers: {exc}"
        ) from exc

    return AgentCandidate(
        name=str(name) if name is not None else "",
        entrypoint=str(entrypoint) if entrypoint is not None else "",
        mutable=tuple(str(p) for p in mutable_raw),
        base_model=str(base_model) if base_model is not None else "",
        budget=Budget(usd=usd, wall_clock_min=wall_clock_min),
        ladders=tuple(str(ladder) for ladder in ladders_raw),
        root=root,
    )
