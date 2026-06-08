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


def gemini_client(prefer: str | None = None):
    """Return a Gemini-shaped judge client.

    Resolution ladder (override via ``prefer``):
    1. ``cliproxy``     — OpenAI SDK pointed at ``CLIPROXY_BASE_URL`` (model
                          pool broker; brokers subscription CLI quota into an
                          OpenAI-compatible endpoint).
    2. ``vertex_oauth`` — ``google.genai.Client(vertexai=True)`` using
                          Application Default Credentials + ``GOOGLE_CLOUD_PROJECT``
                          (Google AI subscription via OAuth / ADC).
    3. ``api``          — ``google.genai.Client()`` if ``GEMINI_API_KEY`` /
                          ``GOOGLE_API_KEY`` in env.
    4. ``antigravity``  — :class:`AntigravityShellClient` shells to the
                          ``antigravity`` subscription CLI.

    Returns whichever works first. Raises ``RuntimeError`` if all unavailable.
    """
    _ensure_init()
    order = ("cliproxy", "vertex_oauth", "api", "antigravity")
    if prefer:
        order = (prefer, *[m for m in order if m != prefer])

    last_err: Exception | None = None
    for mode in order:
        try:
            if mode == "cliproxy":
                base = os.environ.get("CLIPROXY_BASE_URL")
                if not base:
                    raise RuntimeError("CLIPROXY_BASE_URL not set")
                from openai import OpenAI  # type: ignore

                return CliProxyGeminiClient(
                    base_url=base,
                    api_key=os.environ.get("CLIPROXY_API_KEY", "no-key"),
                    underlying=OpenAI(
                        base_url=base,
                        api_key=os.environ.get("CLIPROXY_API_KEY", "no-key"),
                    ),
                )
            if mode == "vertex_oauth":
                project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
                    "VERTEX_PROJECT"
                )
                if not project:
                    raise RuntimeError(
                        "GOOGLE_CLOUD_PROJECT (or VERTEX_PROJECT) not set; "
                        "vertex_oauth requires ADC scope"
                    )
                from google import genai  # type: ignore

                location = os.environ.get("VERTEX_LOCATION", "us-central1")
                return genai.Client(
                    vertexai=True, project=project, location=location
                )
            if mode == "api":
                if not (
                    os.environ.get("GEMINI_API_KEY")
                    or os.environ.get("GOOGLE_API_KEY")
                ):
                    raise RuntimeError("no GEMINI_API_KEY / GOOGLE_API_KEY in env")
                from google import genai  # type: ignore

                return genai.Client()
            if mode == "antigravity":
                import shutil as _shutil

                bin_ = os.environ.get("ANTIGRAVITY_BIN", "antigravity")
                if not _shutil.which(bin_):
                    raise RuntimeError(f"antigravity binary {bin_!r} not on PATH")
                return AntigravityShellClient(bin_)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(
        f"no Gemini backend available (tried {order}); last error: {last_err}"
    )


class CliProxyGeminiClient:
    """OpenAI-shaped Gemini client backed by a CLIProxyAPI broker.

    Exposes ``.models.generate_content(model, contents, config=None)`` so the
    LlmJudgeOracle adapter is backend-agnostic. The broker translates
    OpenAI-style chat completions into subscription-CLI invocations under
    the hood.
    """

    def __init__(self, *, base_url: str, api_key: str, underlying: Any):
        self._base_url = base_url
        self._api_key = api_key
        self._client = underlying
        self.models = self

    def generate_content(
        self, *, model: str, contents: str, config: dict | None = None
    ):
        system = (config or {}).get("system_instruction", "") if config else ""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": contents})
        comp = self._client.chat.completions.create(
            model=model,
            messages=messages,
        )
        text = comp.choices[0].message.content or ""
        return _SimpleResponse(text=text)


class AntigravityShellClient:
    """Shell-based Gemini client mirroring google-genai's surface.

    Exposes ``.models.generate_content(model, contents, config=None)`` so the
    :class:`LlmJudgeOracle` adapter does not branch on backend.
    """

    def __init__(self, bin_: str = "antigravity"):
        self._bin = bin_
        self.models = self  # so `.models.generate_content` works

    def generate_content(self, *, model: str, contents: str, config: dict | None = None):
        import subprocess as _subprocess

        prompt = contents if config is None else _prepend_system(config, contents)
        cmd = [self._bin, "exec", "--model", model, "--prompt", prompt]
        proc = _subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if proc.returncode != 0:
            raise RuntimeError(
                f"antigravity exec failed ({proc.returncode}): "
                f"{proc.stderr[:400] if proc.stderr else proc.stdout[:400]}"
            )
        return _SimpleResponse(text=proc.stdout)


class _SimpleResponse:
    def __init__(self, text: str):
        self.text = text


def _prepend_system(config: dict, contents: str) -> str:
    sys_inst = config.get("system_instruction") if isinstance(config, dict) else None
    if not sys_inst:
        return contents
    return f"[SYSTEM]\n{sys_inst}\n[/SYSTEM]\n\n{contents}"


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
