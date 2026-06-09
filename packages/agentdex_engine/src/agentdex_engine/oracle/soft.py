"""Soft Oracle — LLM-as-judge narrative coherence scorer.

Per phase-6 spec + ADR-0008 §Amendment-2026-06-08 §judge-as-profile DOWNGRADE:
``judge_llm`` is a **model id string** (e.g. ``"claude-haiku-4-5"``), NOT a
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
import sys
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


# PR #18 — retry policy for transient upstream 5xx (Cloudflare 525 SSL
# handshake failure, gateway 502, rate-limit 503 etc.) on the judge SDK
# call. Without retries, ONE transient upstream blip on the judge path takes
# down EVERY baseline in the Expedition because the orchestrator catches
# the SDK exception inside `_run_one_bridge` and marks the baseline as
# `excluded-failed`. The retry budget is intentionally small: judge calls
# are sequential per-baseline, so a 3-attempt backoff adds at most ~6 s
# per baseline on a sustained outage before falling through.
_JUDGE_RETRY_MAX_ATTEMPTS = 3
_JUDGE_RETRY_BASE_DELAY_SEC = 2.0


def _is_retryable_judge_error(exc: BaseException) -> bool:
    """Heuristic — retry on transient upstream 5xx / network blip.

    Matches by exception class name + stringified body so we do not have to
    import every SDK's specific exception type (anthropic, openai,
    google-genai, cohere, etc. — the pool is open-ended). Errors we DO
    want to retry: InternalServerError (5xx generic), APIConnectionError,
    APITimeoutError, RateLimitError (429), and any exception whose
    stringified body mentions a 5xx Cloudflare edge code (520..527) or a
    standard gateway 5xx (502/503/504).
    """
    name = type(exc).__name__.lower()
    if any(
        marker in name
        for marker in (
            "internalserver",
            "apiconnection",
            "apitimeout",
            "ratelimit",
            "serviceunavailable",
            "badgateway",
            "gatewaytimeout",
        )
    ):
        return True
    text = repr(exc)
    if any(
        code in text
        for code in (
            "520",
            "521",
            "522",
            "523",
            "524",
            "525",
            "526",
            "527",
            "502",
            "503",
            "504",
        )
    ):
        return True
    return False


def _call_judge_with_retries(fn: Any, *, label: str) -> Any:
    """Invoke ``fn()`` with exponential-backoff retries on transient upstream errors.

    Synchronous (judge calls run inside ``asyncio.to_thread`` from the
    orchestrator, so blocking-sleep here does not stall the event loop).
    Re-raises the original exception after ``_JUDGE_RETRY_MAX_ATTEMPTS``
    attempts or immediately for non-retryable errors.
    """
    import time

    last_exc: BaseException | None = None
    for attempt in range(1, _JUDGE_RETRY_MAX_ATTEMPTS + 1):
        try:
            return fn()
        except BaseException as exc:
            last_exc = exc
            if attempt >= _JUDGE_RETRY_MAX_ATTEMPTS or not _is_retryable_judge_error(exc):
                raise
            delay = _JUDGE_RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1))
            log.warning(
                "judge %s attempt %d/%d failed (%s); retrying in %.1fs",
                label,
                attempt,
                _JUDGE_RETRY_MAX_ATTEMPTS,
                type(exc).__name__,
                delay,
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]  # unreachable


@contextlib.contextmanager
def _judge_observation(name: str, metadata: dict[str, Any] | None = None):
    """Open a Langfuse ``generation``-typed observation around a judge call.

    No-op when Langfuse is not initialized. Always yields so callers can
    use a single ``with`` statement regardless of tracing state. SF1 fix:
    first failure of the import / get_client / start_as_current_observation
    path emits a WARNING so the operator notices trace-orphan drift.

    Generator-protocol invariant (live-bridge regression fix, PR #10): each
    branch yields EXACTLY ONCE. The prior shape wrapped a yielded block in
    ``try/except Exception`` and yielded ``None`` from the except clause —
    when the caller threw into the original yield (asyncio task cancellation
    propagating an upstream bridge ``CliDead``), Python's contextmanager
    machinery raised ``RuntimeError("generator didn't stop after throw()")``
    because the second yield resumed an already-thrown-into generator. Now
    setup vs body exceptions are split: setup failures yield ``None`` then
    return, body exceptions propagate cleanly through the inner observation
    context manager via explicit ``__enter__`` / ``__exit__`` driving.
    """
    global _judge_observation_failed_once

    # --- setup phase: ALL setup work happens BEFORE the first yield, so
    #     no throw landing in our yield can reach the except clause -----
    obs: Any = None
    cm: Any = None
    enabled = False
    try:
        from agentdex_observe import is_enabled

        enabled = is_enabled()
        if enabled:
            from langfuse import get_client

            client = get_client()
            cm = client.start_as_current_observation(name=name, as_type="generation")
            obs = cm.__enter__()
    except Exception as exc:
        # Setup failed (import error / client init / observation start). Log
        # once, drop to the no-op branch — we have NOT yielded yet.
        if not _judge_observation_failed_once:
            _judge_observation_failed_once = True
            log.warning(
                "judge observation tracing disabled (import failure: %r). "
                "Langfuse spans will NOT parent under the Expedition trace "
                "until init_langfuse + the langfuse SDK are both importable.",
                exc,
            )
        enabled = False
        obs = None
        cm = None

    # --- no-op branch: yield exactly once + return ----------------------
    if not enabled or cm is None:
        yield None
        return

    # --- body phase: yield exactly once + ensure inner cm exits cleanly,
    #     even when the caller throws into our yield point. NO second
    #     yield anywhere in this branch — that is what raised
    #     ``RuntimeError("generator didn't stop after throw()")`` in the
    #     live-bridge regression. -------------------------------------
    if metadata:
        try:
            obs.update(metadata=metadata)
        except Exception:
            pass
    try:
        yield obs
    except BaseException:
        # Caller threw into our yield. Forward live exc_info to the inner
        # observation context manager so its __exit__ sees it; re-raise
        # unless the inner cm explicitly suppressed.
        if not cm.__exit__(*sys.exc_info()):
            raise
    else:
        try:
            cm.__exit__(None, None, None)
        except Exception:
            pass


def _budget_for(level: str) -> int:
    return {"low": 256, "medium": 1024, "high": 4096}.get(level.lower(), 1024)


def _extract_anthropic_usage(message: Any) -> dict[str, int] | None:
    """Pull input_tokens / output_tokens / cache_* from an Anthropic message.

    Real Claude Code calls surface ``cache_creation_input_tokens`` +
    ``cache_read_input_tokens`` which dominate cost. Roll them up so the
    Langfuse generation span carries the full cost-relevant token count.
    """
    usage = getattr(message, "usage", None)
    if usage is None and isinstance(message, dict):
        usage = message.get("usage")
    if usage is None:
        return None

    def _g(name: str) -> int:
        v = getattr(usage, name, None)
        if v is None and isinstance(usage, dict):
            v = usage.get(name)
        try:
            return int(v) if v is not None else 0
        except (TypeError, ValueError):
            return 0

    inp = _g("input_tokens")
    out = _g("output_tokens")
    cc = _g("cache_creation_input_tokens")
    cr = _g("cache_read_input_tokens")
    total = inp + out + cc + cr
    if total == 0:
        return None
    return {
        "input": inp,
        "output": out,
        "cache_creation": cc,
        "cache_read": cr,
        "total": total,
    }


def _extract_openai_usage(comp: Any) -> dict[str, int] | None:
    usage = getattr(comp, "usage", None)
    if usage is None and isinstance(comp, dict):
        usage = comp.get("usage")
    if usage is None:
        return None

    def _g(name: str) -> int:
        v = getattr(usage, name, None)
        if v is None and isinstance(usage, dict):
            v = usage.get(name)
        try:
            return int(v) if v is not None else 0
        except (TypeError, ValueError):
            return 0

    inp = _g("prompt_tokens")
    out = _g("completion_tokens")
    total = _g("total_tokens") or (inp + out)
    if total == 0:
        return None
    return {"input": inp, "output": out, "total": total}


def _extract_gemini_usage(resp: Any) -> dict[str, int] | None:
    # google-genai puts counts under usage_metadata.
    meta = getattr(resp, "usage_metadata", None)
    if meta is None and isinstance(resp, dict):
        meta = resp.get("usage_metadata")
    if meta is None:
        return None

    def _g(name: str) -> int:
        v = getattr(meta, name, None)
        if v is None and isinstance(meta, dict):
            v = meta.get(name)
        try:
            return int(v) if v is not None else 0
        except (TypeError, ValueError):
            return 0

    inp = _g("prompt_token_count")
    out = _g("candidates_token_count")
    total = _g("total_token_count") or (inp + out)
    if total == 0:
        return None
    return {"input": inp, "output": out, "total": total}


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
            "Default rubric: response coherence, factual presentation, narrative flow. Score 0..1."
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
        with _judge_observation(name=f"judge.{self.judge_llm}", metadata=metadata) as obs:
            try:
                if obs is not None:
                    obs.update(input={"prompt": user_prompt[:4000]})
            except Exception:
                pass

            # SF2 (harness-praxis tracer follow-up): extract usage tokens
            # from each SDK shape so the Langfuse generation span carries
            # input_tokens / output_tokens. Without these, judge cost +
            # latency dashboards have no signal. None when the backend
            # (e.g. subscription subprocess wrapper) does not surface usage.
            usage: dict[str, int] | None = None
            model_id_used = self.judge_llm

            # Each backend's SDK call is wrapped in `_call_judge_with_retries`
            # so a transient upstream 5xx (e.g. Cloudflare 525 SSL handshake
            # failure) does not propagate up and excluded-fail every baseline
            # in the Expedition. See `_is_retryable_judge_error` for the
            # retry classifier; non-5xx exceptions still propagate cleanly.

            # Anthropic SDK (.messages.create)
            if prefix == "claude" or hasattr(client, "messages"):
                message = _call_judge_with_retries(
                    lambda: client.messages.create(
                        model=self.judge_llm,
                        max_tokens=2000,
                        system=self.SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": user_prompt}],
                    ),
                    label=f"anthropic/{self.judge_llm}",
                )
                out = self._extract_text(message)
                usage = _extract_anthropic_usage(message)
                model_id_used = getattr(message, "model", self.judge_llm) or self.judge_llm
            # google-genai SDK (.models.generate_content)
            elif prefix == "gemini" or hasattr(client, "models"):
                cfg: dict[str, Any] = {"system_instruction": self.SYSTEM_PROMPT}
                if self.reasoning_effort:
                    cfg["thinking_config"] = {"thinking_budget": _budget_for(self.reasoning_effort)}

                def _gemini_call() -> Any:
                    try:
                        return client.models.generate_content(
                            model=self.judge_llm,
                            contents=user_prompt,
                            config=cfg,
                        )
                    except TypeError:
                        # older SDK without config kw; fall through to minimal call
                        return client.models.generate_content(
                            model=self.judge_llm,
                            contents=user_prompt,
                        )

                resp = _call_judge_with_retries(_gemini_call, label=f"gemini/{self.judge_llm}")
                out = getattr(resp, "text", "") or self._extract_text(resp)
                usage = _extract_gemini_usage(resp)
            # OpenAI SDK fallback (.chat.completions.create)
            elif hasattr(client, "chat"):
                comp = _call_judge_with_retries(
                    lambda: client.chat.completions.create(
                        model=self.judge_llm,
                        messages=[
                            {"role": "system", "content": self.SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                    ),
                    label=f"openai/{self.judge_llm}",
                )
                out = comp.choices[0].message.content or ""
                usage = _extract_openai_usage(comp)
                model_id_used = getattr(comp, "model", self.judge_llm) or self.judge_llm
            else:
                raise RuntimeError(
                    f"no judge adapter matches client {type(client).__name__} "
                    f"for model {self.judge_llm!r}"
                )

            try:
                if obs is not None:
                    update_kwargs: dict[str, Any] = {
                        "output": {"text": (out or "")[:4000]},
                        "model": model_id_used,
                    }
                    if usage is not None:
                        update_kwargs["usage_details"] = usage
                    obs.update(**update_kwargs)
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
                t = getattr(block, "text", None) or (
                    block.get("text") if isinstance(block, dict) else None
                )
                if t:
                    parts.append(t)
            return "\n".join(parts)
        if isinstance(content, str):
            return content
        return str(message)
