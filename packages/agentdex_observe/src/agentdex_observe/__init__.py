"""agentdex_observe — Langfuse glue for trace-level observability.

Per ADR-0009 §Observability + user decision 2026-06-08 "we will self-host Langfuse
for now", `init_langfuse()` defaults to `LANGFUSE_HOST=http://localhost:3000` and
falls back to cloud only if user explicitly overrides.

Surface (per phase-4 spec):
- init_langfuse(public_key, secret_key, host) — singleton init from env vars
- anthropic_client() — Langfuse-wrapped Anthropic SDK (auto-instruments)
- openai_client() — Langfuse-wrapped OpenAI SDK (auto-instruments)
- @trace_session(name, metadata) — wraps Expedition / per-baseline session as root trace
- @trace_turn(name, metadata) — wraps single turn / tool call as span within parent trace
- current_trace_url() -> str | None — drill-down URL for current trace; None if not init'd
- get_trace_context_headers() -> dict[str, str] — HTTP headers for cross-process trace propagation (R3 spike)
- set_trace_context_from_headers(headers) — re-parent in-process spans from incoming HTTP headers (R3 fallback)

Graceful degradation: if LANGFUSE_PUBLIC_KEY unset, decorators no-op and
current_trace_url() returns None. MVP runs without Langfuse if env unconfigured.
"""

from __future__ import annotations

import functools
import os
from typing import Any, Callable

_DEFAULT_HOST = "http://localhost:3000"  # self-host per user decision 2026-06-08
_initialized = False
_client = None  # Langfuse singleton when init'd
_disabled_reason: str | None = None


def init_langfuse(
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
) -> bool:
    """Singleton init. Returns True if Langfuse is live; False if env unconfigured or SDK absent."""
    global _initialized, _client, _disabled_reason

    if _initialized:
        return _client is not None

    pk = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY")
    sk = secret_key or os.environ.get("LANGFUSE_SECRET_KEY")
    h = host or os.environ.get("LANGFUSE_HOST", _DEFAULT_HOST)

    if not pk or not sk:
        _initialized = True
        _disabled_reason = "LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY unset"
        return False

    try:
        from langfuse import Langfuse
    except ImportError as e:
        _initialized = True
        _disabled_reason = f"langfuse SDK import failed: {e}"
        return False

    _client = Langfuse(public_key=pk, secret_key=sk, host=h)
    _initialized = True
    return True


def _ensure_init() -> bool:
    """Lazy init on first decorator/client invocation."""
    if not _initialized:
        init_langfuse()
    return _client is not None


def anthropic_client():
    """Return Langfuse-wrapped Anthropic client.

    Falls back to vanilla Anthropic if Langfuse SDK absent or env unconfigured.
    Re-imports per call so tests can swap behavior; in hot path the import is cached by Python.
    """
    _ensure_init()
    if _client is None:
        try:
            from anthropic import Anthropic
            return Anthropic()
        except ImportError as e:
            raise RuntimeError(f"anthropic SDK missing: {e}") from e

    from langfuse.anthropic import Anthropic as LangfuseAnthropic
    return LangfuseAnthropic()


def openai_client():
    """Return Langfuse-wrapped OpenAI client. Falls back to vanilla OpenAI if Langfuse absent."""
    _ensure_init()
    if _client is None:
        try:
            from openai import OpenAI
            return OpenAI()
        except ImportError as e:
            raise RuntimeError(f"openai SDK missing: {e}") from e

    from langfuse.openai import OpenAI as LangfuseOpenAI
    return LangfuseOpenAI()


def gemini_client():
    """Return a direct-API google-genai client.

    Single resolution path (api-mode only): requires ``GEMINI_API_KEY`` or
    ``GOOGLE_API_KEY`` in env and the ``google-genai`` SDK installed.

    Raises :class:`RuntimeError` if neither env var is set or the SDK is
    missing. The prior 4-mode ladder (``cliproxy`` / ``vertex_oauth`` /
    ``api`` / ``antigravity``) was removed per the Musk-review slim: the
    cliproxy / subscription-broker path is now handled centrally by
    :func:`agentdex_observe.llm_pool.client_for`, which returns a
    :class:`agentdex_observe.llm_pool.PooledClient`. This entry point is
    the direct-API fallback only.
    """
    _ensure_init()
    if not (
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    ):
        raise RuntimeError(
            "gemini_client requires GEMINI_API_KEY or GOOGLE_API_KEY in env"
        )
    try:
        from google import genai  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"google-genai SDK missing: {e}") from e
    return genai.Client()


def trace_session(name: str, metadata: dict[str, Any] | None = None):
    """Decorator: wrap function as Langfuse root trace (Expedition / per-baseline session)."""

    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not _ensure_init():
                return fn(*args, **kwargs)
            with _client.start_as_current_observation(name=name, as_type="span") as obs:
                if metadata:
                    obs.update(metadata=metadata)
                return fn(*args, **kwargs)

        return wrapper

    return decorator


def trace_turn(name: str, metadata: dict[str, Any] | None = None):
    """Decorator: wrap function as Langfuse span within current trace (per-turn / per-tool-call)."""

    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not _ensure_init():
                return fn(*args, **kwargs)
            with _client.start_as_current_observation(name=name, as_type="span") as obs:
                if metadata:
                    obs.update(metadata=metadata)
                return fn(*args, **kwargs)

        return wrapper

    return decorator


def current_trace_url() -> str | None:
    """Return Langfuse drill-down URL for current trace, or None if no active trace."""
    if not _ensure_init():
        return None
    trace_id = _client.get_current_trace_id()
    if trace_id is None:
        return None
    host = os.environ.get("LANGFUSE_HOST", _DEFAULT_HOST).rstrip("/")
    return f"{host}/trace/{trace_id}"


def get_trace_context_headers() -> dict[str, str]:
    """R3 spike support: serialize current trace context for outbound HTTP.

    Returns headers to inject in HTTP requests to a downstream Hermes gateway
    so the gateway-side plugin hook can re-parent its spans to the orchestrator's
    Expedition trace. Empty dict if no active trace or Langfuse disabled.
    """
    if not _ensure_init():
        return {}
    trace_id = _client.get_current_trace_id()
    parent_observation_id = _client.get_current_observation_id()
    if trace_id is None:
        return {}
    headers = {"X-Langfuse-Trace-Id": trace_id}
    if parent_observation_id:
        headers["X-Langfuse-Parent-Observation-Id"] = parent_observation_id
    return headers


def set_trace_context_from_headers(headers: dict[str, str]) -> bool:
    """R3 spike support: gateway-side, re-parent in-process spans from incoming HTTP headers.

    Returns True if a trace context was extracted + applied; False otherwise.
    Used by the agentdex_plugin gateway-side hook to propagate the Expedition
    trace context from the orchestrator process.

    Note: actual re-parent semantics depend on Langfuse SDK v4 propagation API.
    If SDK does not expose context-injection, returns False and the gateway
    spans become per-baseline-root (Phase 4 R3 spike fallback documented in
    phase-4-r3-spike-outcome.md).
    """
    if not _ensure_init():
        return False
    trace_id = headers.get("X-Langfuse-Trace-Id")
    parent_id = headers.get("X-Langfuse-Parent-Observation-Id")
    if not trace_id:
        return False
    try:
        # SDK v4: propagate_attributes is the supported way; if missing, this raises.
        _client.propagate_attributes(trace_id=trace_id)
        return True
    except (AttributeError, TypeError):
        return False


def is_enabled() -> bool:
    """Returns True if Langfuse is initialized + live; False if disabled (graceful degrade)."""
    if not _initialized:
        init_langfuse()
    return _client is not None


def disabled_reason() -> str | None:
    """Returns reason Langfuse is disabled (env unset / SDK absent), or None if live."""
    return _disabled_reason


__all__ = [
    "init_langfuse",
    "anthropic_client",
    "openai_client",
    "gemini_client",
    "trace_session",
    "trace_turn",
    "current_trace_url",
    "get_trace_context_headers",
    "set_trace_context_from_headers",
    "is_enabled",
    "disabled_reason",
]
