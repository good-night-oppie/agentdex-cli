"""NL → workflow/skill router for ``adx assist``.

Two routing modes:
- **deterministic** — exact id match (e.g. ``adx assist run expedition.nvidia``)
- **llm**           — Anthropic-as-router using the registry catalogue +
                       NL prompt; returns structured :class:`AssistDecision`.

LLM path:
- Uses ``agentdex_observe.anthropic_client()`` (Langfuse-wrapped if enabled)
- Requires ``ANTHROPIC_API_KEY`` set; falls back to deterministic top-match
  by keyword overlap when key missing.

Per Hermes-style "she" UX: when the user gives a fuzzy prompt the assistant
makes the best call AND surfaces its rationale before the CLI executes.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from agentdex_cli.assist.registry import (
    AssistDecision,
    AssistRegistry,
    Skill,
    Workflow,
)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


_SYSTEM = (
    "You are the agentdex-cli evolution-research assistant. Map the user's "
    "natural-language request to ONE concrete action from the catalogue. "
    "Reply ONLY with a JSON object of the shape "
    '{"action":"workflow"|"skill","id":"<id>","args":{...},'
    '"rationale":"<one sentence>"}. '
    "Pick the workflow / skill whose `when_to_use` best matches the user's "
    "intent. If the request is ambiguous, prefer the safest action (probe / "
    "status > mocked > live). Do not invent ids that are not in the catalogue."
)


@dataclass
class RouterResult:
    decision: AssistDecision
    used_llm: bool


def _expand_command(template: list[str], args: dict[str, Any]) -> list[str]:
    import time

    expanded = []
    for token in template:
        if "{" in token and "}" in token:
            for k, v in args.items():
                token = token.replace("{" + k + "}", str(v))
            token = token.replace("{ts}", str(int(time.time())))
        expanded.append(token)
    return expanded


def _resolve(
    registry: AssistRegistry,
    kind: str,
    id_: str,
    args: dict[str, Any],
    rationale: str,
) -> AssistDecision:
    item = registry.get(kind, id_)  # type: ignore[arg-type]
    if item is None:
        raise ValueError(f"unknown {kind} id={id_!r}")
    merged_args: dict[str, Any] = {}
    for field, spec in (item.args_schema or {}).items():
        if isinstance(spec, dict) and "default" in spec:
            merged_args[field] = spec["default"]
    merged_args.update(args or {})
    return AssistDecision(
        action=kind,  # type: ignore[arg-type]
        id=item.id,
        args=merged_args,
        rationale=rationale,
        resolved_command=_expand_command(item.command, merged_args),
    )


def _llm_route(
    registry: AssistRegistry,
    prompt: str,
    *,
    model: str = "claude-haiku-4.5",
) -> AssistDecision | None:
    try:
        from agentdex_observe import anthropic_client
    except ImportError:
        return None

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    try:
        client = anthropic_client()
        message = client.messages.create(
            model=model,
            max_tokens=600,
            system=_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Catalogue:\n"
                        f"{registry.render_catalogue()}\n\n"
                        f"User request: {prompt}\n\nReturn the JSON now."
                    ),
                }
            ],
        )
        raw = _extract_text(message)
        m = _JSON_RE.search(raw)
        if not m:
            return None
        data = json.loads(m.group(0))
        return _resolve(
            registry,
            kind=str(data.get("action")),
            id_=str(data.get("id")),
            args=dict(data.get("args") or {}),
            rationale=str(data.get("rationale") or "(no rationale returned)"),
        )
    except Exception as e:
        # llm router is best-effort; fall through to keyword.
        return None


def _keyword_route(
    registry: AssistRegistry, prompt: str
) -> AssistDecision | None:
    """Fallback: keyword overlap scoring against when_to_use + description."""
    if not prompt.strip():
        return None
    lower = prompt.lower()
    tokens = {t for t in re.split(r"\W+", lower) if len(t) >= 3}
    if not tokens:
        return None

    def score(item: Workflow | Skill) -> int:
        target = (item.when_to_use + " " + item.description + " " + item.name).lower()
        return sum(1 for t in tokens if t in target)

    best: tuple[int, str, str] | None = None  # (score, kind, id)
    for w in registry.list_workflows():
        s = score(w)
        if s and (best is None or s > best[0]):
            best = (s, "workflow", w.id)
    for sk in registry.list_skills():
        s = score(sk)
        if s and (best is None or s > best[0]):
            best = (s, "skill", sk.id)
    if best is None:
        return None
    s, kind, id_ = best
    return _resolve(
        registry,
        kind=kind,
        id_=id_,
        args={},
        rationale=f"keyword-overlap top match (score={s}); LLM router unavailable or fell through.",
    )


def route(
    registry: AssistRegistry,
    prompt: str | None,
    *,
    explicit: tuple[str, str] | None = None,
    explicit_args: dict[str, Any] | None = None,
    model: str = "claude-haiku-4.5",
) -> RouterResult:
    """Resolve a user request to a concrete :class:`AssistDecision`.

    Priority:
    1. explicit (kind, id) tuple from CLI (`adx assist run workflow expedition.nvidia`)
    2. NL prompt → LLM router
    3. NL prompt → keyword fallback
    """
    if explicit is not None:
        kind, id_ = explicit
        return RouterResult(
            decision=_resolve(
                registry,
                kind=kind,
                id_=id_,
                args=dict(explicit_args or {}),
                rationale=f"explicit cli selection: {kind}={id_}",
            ),
            used_llm=False,
        )

    if prompt is None or not prompt.strip():
        raise ValueError(
            "no prompt provided; pass a NL request or an explicit (kind,id) selection"
        )

    decision = _llm_route(registry, prompt, model=model)
    if decision is not None:
        return RouterResult(decision=decision, used_llm=True)

    fallback = _keyword_route(registry, prompt)
    if fallback is not None:
        return RouterResult(decision=fallback, used_llm=False)

    raise ValueError(
        f"could not route prompt {prompt!r}; LLM unavailable and no keyword match. "
        "Try `adx assist list` to inspect the catalogue."
    )


def _extract_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            t = getattr(block, "text", None) or (
                block.get("text") if isinstance(block, dict) else None
            )
            if t:
                parts.append(t)
        return "\n".join(parts)
    if isinstance(content, str):
        return content
    return str(message)


__all__ = ["RouterResult", "route"]
