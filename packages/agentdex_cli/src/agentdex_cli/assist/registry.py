"""Workflow + Skill registry — loaded from yaml at package data dir.

Each yaml file describes one workflow or skill. Pydantic-strict schemas
catch shape drift early. Discoverable by Hermes via the plugin entry-points
group (``hermes_agent.plugins``) so other Hermes hosts can route to the same
catalogue.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


AssistAction = Literal["workflow", "skill", "freeform"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Workflow(_Base):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    when_to_use: str = Field(min_length=1)
    args_schema: dict[str, Any] = Field(default_factory=dict)
    command: list[str] = Field(min_length=1)


class Skill(_Base):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    when_to_use: str = Field(min_length=1)
    args_schema: dict[str, Any] = Field(default_factory=dict)
    command: list[str] = Field(min_length=1)


class AssistDecision(_Base):
    action: AssistAction
    id: str
    args: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=1)
    resolved_command: list[str] = Field(default_factory=list)


class AssistRegistry:
    """In-memory index of workflows + skills loaded from yaml."""

    def __init__(self, workflows: list[Workflow], skills: list[Skill]):
        self.workflows = {w.id: w for w in workflows}
        self.skills = {s.id: s for s in skills}

    def list_workflows(self) -> list[Workflow]:
        return list(self.workflows.values())

    def list_skills(self) -> list[Skill]:
        return list(self.skills.values())

    def get(self, kind: AssistAction, id_: str) -> Workflow | Skill | None:
        if kind == "workflow":
            return self.workflows.get(id_)
        if kind == "skill":
            return self.skills.get(id_)
        return None

    def render_catalogue(self) -> str:
        lines = ["# Workflows"]
        for w in self.list_workflows():
            lines.append(f"- **{w.id}** — {w.description}\n  *when:* {w.when_to_use}")
        lines.append("\n# Skills")
        for s in self.list_skills():
            lines.append(f"- **{s.id}** — {s.description}\n  *when:* {s.when_to_use}")
        return "\n".join(lines)


def _load_yaml_dir(directory: Path, model: type) -> list[Any]:
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.yaml")):
        body = yaml.safe_load(path.read_text(encoding="utf-8"))
        if body is None:
            continue
        out.append(model.model_validate(body))
    return out


def load_registry(base_dir: Path | None = None) -> AssistRegistry:
    """Load workflows + skills from packaged yaml under ``assist/``."""
    base = base_dir or (Path(__file__).resolve().parent)
    workflows = _load_yaml_dir(base / "workflows", Workflow)
    skills = _load_yaml_dir(base / "skills", Skill)
    return AssistRegistry(workflows, skills)


__all__ = [
    "AssistAction",
    "AssistDecision",
    "AssistRegistry",
    "Skill",
    "Workflow",
    "load_registry",
]
