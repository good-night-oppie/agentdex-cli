"""Soft Oracle — LLM-as-judge narrative coherence scorer.

Per phase-6 spec + ADR-0008 §Amendment-2026-06-08 §judge-as-profile DOWNGRADE:
``judge_llm`` is a **model id string** (e.g. ``"claude-haiku-4.5"``), NOT a
Hermes profile name. The judge is invoked through
:func:`agentdex_observe.anthropic_client` so Langfuse auto-instrumentation
captures the call as a span (parent = current Expedition trace).

Bypassing ``agentdex_observe`` (e.g. direct ``from anthropic import Anthropic``)
is forbidden — that breaks the trace tree (judge call invisible). A unit test
asserts that the judge invocation flows through ``anthropic_client``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agentdex_engine.cards import TaskCard
from agentdex_engine.oracle.base import OracleVerdict, OracleVerdictMap


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class LlmJudgeOracle:
    """Calls an LLM judge with the rubric + response; parses verdict JSON."""

    SYSTEM_PROMPT = (
        "You are an evaluation judge. Read the user's RESPONSE and RUBRIC. "
        "Return a single JSON object: "
        '{"score": <float 0..1>, "uncertainty": <float 0..1>, '
        '"pass": <bool>, "rationale": <string>}. '
        "score=1 means perfect rubric satisfaction; uncertainty=0 means highly "
        "confident; pass=true iff score >= rubric pass threshold (default 0.7). "
        "Return ONLY the JSON object, no surrounding prose."
    )

    def __init__(
        self,
        judge_llm: str,
        rubric_path: str | Path | None = None,
        pass_threshold: float = 0.7,
        *,
        client_factory=None,  # injectable for tests
    ):
        self.judge_llm = judge_llm
        self.rubric_path = Path(rubric_path) if rubric_path else None
        self.pass_threshold = pass_threshold
        self._client_factory = client_factory

    def _resolve_client(self):
        if self._client_factory is not None:
            return self._client_factory()
        from agentdex_observe import anthropic_client

        return anthropic_client()

    def _load_rubric(self, task_card: TaskCard) -> str:
        if self.rubric_path and self.rubric_path.is_file():
            return self.rubric_path.read_text(encoding="utf-8")
        return (
            "Default rubric: response coherence, factual presentation, "
            "narrative flow. Score 0..1."
        )

    def _build_user_prompt(self, response: str, rubric: str) -> str:
        excerpt = response if len(response) <= 6000 else response[:6000] + "\n…[truncated]"
        return (
            f"=== RUBRIC ===\n{rubric}\n\n"
            f"=== RESPONSE ===\n{excerpt}\n\n"
            "Return the verdict JSON now."
        )

    def _parse_verdict_json(self, raw: str) -> dict[str, Any]:
        m = _JSON_OBJECT_RE.search(raw)
        if not m:
            raise ValueError(f"judge did not return JSON; got: {raw[:200]!r}")
        return json.loads(m.group(0))

    def evaluate(self, response: str, task_card: TaskCard) -> OracleVerdictMap:
        rubric = self._load_rubric(task_card)
        client = self._resolve_client()
        message = client.messages.create(
            model=self.judge_llm,
            max_tokens=500,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._build_user_prompt(response, rubric)}],
        )
        raw_text = self._extract_text(message)
        try:
            data = self._parse_verdict_json(raw_text)
        except (ValueError, json.JSONDecodeError) as e:
            return {
                "soft.narrative_coherence": OracleVerdict(
                    kind="soft",
                    **{"pass": False},
                    score=0.0,
                    evidence=f"judge returned unparseable verdict: {e!r}; raw={raw_text[:200]!r}",
                    uncertainty=1.0,
                )
            }
        score = float(data.get("score", 0.0))
        uncertainty = float(data.get("uncertainty", 0.0))
        passed = bool(data.get("pass", score >= self.pass_threshold))
        rationale = str(data.get("rationale", ""))
        return {
            "soft.narrative_coherence": OracleVerdict(
                kind="soft",
                **{"pass": passed},
                score=max(0.0, min(score, 1.0)),
                evidence=f"judge={self.judge_llm}; rationale={rationale[:300]}",
                uncertainty=max(0.0, min(uncertainty, 1.0)),
            )
        }

    @staticmethod
    def _extract_text(message: Any) -> str:
        # Anthropic SDK message: ``.content`` is list of blocks with ``.text``.
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                t = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else None)
                if t:
                    parts.append(t)
            return "\n".join(parts)
        if isinstance(content, str):
            return content
        return str(message)
