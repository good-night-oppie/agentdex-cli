"""adx assist — Hermes-style natural-language research-assistant entrypoint.

Per user direction 2026-06-08 "i want to provide experience of using adx-cli
like using a hermes agent evolution assistant. we only need to choose
workflows, skills or natural language prompt, hermes take care of the rest
hussle. she is our agent evolution research assistant".

The assistant resolves user intent into one of:
- **workflow**  — a named, parametric pipeline (e.g. ``expedition.nvidia``)
- **skill**     — a single-shot capability (e.g. ``bridge.probe``)
- **freeform**  — escalate to Anthropic-as-router to translate NL into the
  closest workflow/skill + args

Returns a :class:`AssistDecision` describing the chosen action; the CLI
executes it after a single confirm prompt (interactive) or immediately
(``--yes``).
"""

from agentdex_cli.assist.registry import (
    AssistAction,
    AssistDecision,
    AssistRegistry,
    Skill,
    Workflow,
    load_registry,
)
from agentdex_cli.assist.router import RouterResult, route

__all__ = [
    "AssistAction",
    "AssistDecision",
    "AssistRegistry",
    "RouterResult",
    "Skill",
    "Workflow",
    "load_registry",
    "route",
]
