"""Soft Oracle — LLM-as-judge narrative coherence scorer.

Per phase-6 spec + ADR-0008 §Amendment-2026-06-08 §judge-as-profile DOWNGRADE:
``judge_llm`` is a **model id string** (e.g. ``"claude-haiku-4.5"``), NOT a
Hermes profile name.

Trace tree contract (codereview H2 fix, 2026-06-08):
- :meth:`LlmJudgeOracle._invoke_judge` opens an explicit Langfuse observation
  (``judge.<model_id>``) around every backend call so the judge child appears
  under the orchestrator's Expedition trace regardless of whether the client
  is the auto-instrumented Anthropic SDK, a pooled OpenAI-shape proxy, or a
  subprocess-backed subscription wrapper. The span is a no-op when Langfuse
  is disabled (``init_langfuse()`` not called / public key missing).
- The client is resolved through :func:`agentdex_observe.llm_pool.client_for`
  whose backend ladder is documented in :mod:`agentdex_observe.llm_pool`. SDK
  auto-instrument adds a generation span as a child of the judge span; the
  pooled OpenAI proxy + subscription subprocess backends emit only the judge
  span (no per-token generation child) — that's the accepted MVP shape.
"""
from __future__ import annotations

import contextlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from agentdex_engine.cards import TaskCard
from agentdex_engine.oracle.base import OracleVerdict, OracleVerdictMap


log = logging.getLogger(__name__)


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

# SF1 (harness-praxis tracer follow-up): first-failure-only flag so the agent
# is NOT blind to Langfuse plumbing breakage but ALSO does not spam logs from
# every judge call once tracing is busted. Cleared per-process; not async-safe
# by design (logging.warning is the cheap signal, not a metric).
_judge_observation_failed_once = False


@contextlib.contextmanager
def _judge_observation(name: str, metadata: dict[str, Any] | None = None):
    """Open a Langfuse ``generation``-typed observation around a judge call.

    No-op when Langfuse is not initialized. Always yields so callers can
    use a single ``with`` statement regardless of tracing state. SF1 fix:
    first failure of the import / get_client / start_as_current_observation
    path emits a WARNING so the operator notices trace-orphan drift.
    """
    global _judge_observation_failed_once
    try:
        from agentdex_observe import is_enabled

        if not is_enabled():
            yield None
            return
        from langfuse import get_client
    except Exception as exc:
        if not _judge_observation_failed_once:
            _judge_observation_failed_once = True
            log.warning(
                "judge observation tracing disabled (import failure: %r). "
                "Langfuse spans will NOT parent under the Expedition trace "
                "until init_langfuse + the langfuse SDK are both importable.",
                exc,
            )
        yield None
        return
    try:
        client = get_client()
        with client.start_as_current_observation(
            name=name, as_type="generation"
        ) as obs:
            if metadata:
                try:
                    obs.update(metadata=metadata)
                except Exception:
                    pass
            yield obs
    except Exception as exc:
        if not _judge_observation_failed_once:
            _judge_observation_failed_once = True
            log.warning(
                "judge observation tracing failed mid-context (%r). "
                "Subsequent judge calls will silently no-op to avoid log "
                "spam; check init_langfuse() / langfuse server connectivity.",
                exc,
            )
        # Tracing must never break the judge call itself.
        yield None


def _budget_for(level: str) -> int:
    return {"low": 256, "medium": 1024, "high": 4096}.get(level.lower(), 1024)


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
        reasoning_effort: str = "high",
    ):
        self.judge_llm = judge_llm
        self.rubric_path = Path(rubric_path) if rubric_path else None
        self.pass_threshold = pass_threshold
        self._client_factory = client_factory
        self.reasoning_effort = reasoning_effort

    def _resolve_client(self):
        if self._client_factory is not None:
            return self._client_factory()
        # Pool-first: setup once via ~/.adx/llm_pool.env, dispatch by model id.
        try:
            from agentdex_observe.llm_pool import client_for

            return client_for(self.judge_llm)
        except Exception:
            pass
        prefix = self.judge_llm.split("-", 1)[0].lower()
        if prefix == "claude":
            from agentdex_observe import anthropic_client
            return anthropic_client()
        if prefix in {"gpt", "o1", "o3", "o4"}:
            from agentdex_observe import openai_client
            return openai_client()
        if prefix == "gemini":
            from agentdex_observe import gemini_client
            return gemini_client()
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
        user_prompt = self._build_user_prompt(response, rubric)
        raw_text = self._invoke_judge(client, user_prompt)
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

    def _invoke_judge(self, client: Any, user_prompt: str) -> str:
        """Adapter — dispatch by model prefix to the right SDK call shape.

        Wrapped in :func:`_judge_observation` so the call appears as a
        ``generation``-typed Langfuse child of the current Expedition trace
        regardless of which backend (Anthropic SDK / google-genai / OpenAI /
        subscription subprocess wrapper) handles the request.
        """
        prefix = self.judge_llm.split("-", 1)[0].lower()
        backend = type(client).__name__
        metadata = {
            "judge_llm": self.judge_llm,
            "prefix": prefix,
            "backend": backend,
            "reasoning_effort": self.reasoning_effort,
        }
        with _judge_observation(
            name=f"judge.{self.judge_llm}", metadata=metadata
        ) as obs:
            try:
                if obs is not None:
                    obs.update(input={"prompt": user_prompt[:4000]})
            except Exception:
                pass

            # Anthropic SDK (.messages.create)
            if prefix == "claude" or hasattr(client, "messages"):
                message = client.messages.create(
                    model=self.judge_llm,
                    max_tokens=2000,
                    system=self.SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                out = self._extract_text(message)
            # google-genai SDK (.models.generate_content)
            elif prefix == "gemini" or hasattr(client, "models"):
                cfg: dict[str, Any] = {"system_instruction": self.SYSTEM_PROMPT}
                if self.reasoning_effort:
                    cfg["thinking_config"] = {"thinking_budget": _budget_for(self.reasoning_effort)}
                try:
                    resp = client.models.generate_content(
                        model=self.judge_llm,
                        contents=user_prompt,
                        config=cfg,
                    )
                except TypeError:
                    # older SDK without config kw; retry minimal
                    resp = client.models.generate_content(
                        model=self.judge_llm,
                        contents=user_prompt,
                    )
                out = getattr(resp, "text", "") or self._extract_text(resp)
            # OpenAI SDK fallback (.chat.completions.create)
            elif hasattr(client, "chat"):
                comp = client.chat.completions.create(
                    model=self.judge_llm,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                out = comp.choices[0].message.content or ""
            else:
                raise RuntimeError(
                    f"no judge adapter matches client {type(client).__name__} "
                    f"for model {self.judge_llm!r}"
                )

            try:
                if obs is not None:
                    obs.update(output={"text": (out or "")[:4000]})
            except Exception:
                pass
            return out

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
