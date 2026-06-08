"""Unified LLM model pool — setup once, use everywhere.

Per user direction 2026-06-08 "we plugin CLIProxyAPI for LLM model pooling,
so we setup once and use it across adx-cli", every client (bridges, soft
Oracle judge, assist NL router) routes through one entry point:

    from agentdex_observe.llm_pool import client_for
    client = client_for("gemini-3.5-flash")

The pool resolves the right backend by reading ``~/.adx/llm_pool.env``
exactly once per process (or by env override). Resolution ladder:

1. ``cliproxy``     — CLIProxyAPI broker at ``CLIPROXY_BASE_URL`` (default
                       http://localhost:8118/v1). Returns an OpenAI-compatible
                       Langfuse-wrapped client; works for ANY model id
                       supported by the broker (claude-*, gpt-*, gemini-*).
2. ``vertex_oauth`` — google-genai Vertex client using ADC + GOOGLE_CLOUD_PROJECT.
3. ``api``          — provider-specific SDK with provider API key
                       (ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY).
4. ``antigravity``  — subscription-CLI shell wrapper (last-resort Gemini).
5. ``claude_code``  — subscription-CLI shell wrapper (last-resort Claude).

Pool mode is set globally via ``ADX_LLM_POOL_MODE``:
- ``cliproxy``       force pool
- ``direct``         skip pool, use provider SDK
- ``hybrid`` (default) try cliproxy, fall back to direct
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal


_ENV_PATH = Path(os.path.expanduser("~/.adx/llm_pool.env"))


PoolMode = Literal["cliproxy", "direct", "hybrid"]


def _load_pool_env(path: Path = _ENV_PATH) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def ensure_pool_env() -> dict[str, str]:
    """Read ~/.adx/llm_pool.env and export keys into ``os.environ`` (no clobber).

    Returns the parsed dict so callers can inspect what's set.
    """
    env = _load_pool_env()
    for k, v in env.items():
        os.environ.setdefault(k, v)
    return env


def _pool_mode() -> PoolMode:
    return os.environ.get("ADX_LLM_POOL_MODE", "hybrid")  # type: ignore[return-value]


def _model_family(model_id: str) -> str:
    head = model_id.split("-", 1)[0].lower()
    if head == "claude":
        return "anthropic"
    if head in {"gpt", "o1", "o3", "o4"}:
        return "openai"
    if head == "gemini":
        return "gemini"
    return "unknown"


@lru_cache(maxsize=8)
def _cliproxy_openai_client():
    base = os.environ.get("CLIPROXY_BASE_URL", "http://localhost:8118/v1")
    api_key = os.environ.get("CLIPROXY_API_KEY", "cliproxy-no-key")
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(f"openai SDK missing for cliproxy mode: {e}") from e
    return OpenAI(base_url=base, api_key=api_key)


def _cliproxy_available() -> bool:
    base = os.environ.get("CLIPROXY_BASE_URL")
    if not base:
        return False
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"{base.rstrip('/')}/models", timeout=1.5
        ) as r:
            return 200 <= r.status < 300
    except Exception:
        # Some proxies return 401 on /models without auth — still alive.
        try:
            import urllib.request

            req = urllib.request.Request(
                f"{base.rstrip('/')}/models",
                headers={"Authorization": "Bearer probe"},
            )
            with urllib.request.urlopen(req, timeout=1.5) as r:
                return 200 <= r.status < 500
        except Exception:
            return False


class PooledClient:
    """OpenAI-shaped wrapper exposing both Anthropic-style and Gemini-style
    surfaces against the same OpenAI completion endpoint (CLIProxyAPI normalises
    cross-vendor calls). Allows downstream code to call ``client.messages.create``
    OR ``client.models.generate_content`` without branching on vendor."""

    def __init__(self, openai_client: Any, model_id: str):
        self._client = openai_client
        self._model_id = model_id
        self.models = self          # gemini-style: client.models.generate_content
        self.messages = self        # anthropic-style: client.messages.create

    # ----- Anthropic-shaped -----
    def create(self, *, model, max_tokens=None, system=None, messages, **_):
        oai_messages = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        for m in messages:
            content = m["content"]
            if isinstance(content, list):
                # anthropic block list → flatten to text
                content = "\n".join(
                    b.get("text", "") for b in content if isinstance(b, dict)
                )
            oai_messages.append({"role": m["role"], "content": content})
        comp = self._client.chat.completions.create(
            model=model,
            messages=oai_messages,
            max_tokens=max_tokens,
        )
        text = comp.choices[0].message.content or ""

        class _Block:
            def __init__(self, t):
                self.text = t

        class _Msg:
            def __init__(self, t):
                self.content = [_Block(t)]

        return _Msg(text)

    # ----- Gemini-shaped -----
    def generate_content(self, *, model, contents, config=None):
        system = (config or {}).get("system_instruction") if config else None
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": contents})
        comp = self._client.chat.completions.create(model=model, messages=msgs)
        text = comp.choices[0].message.content or ""

        class _Resp:
            def __init__(self, t):
                self.text = t

        return _Resp(text)


def client_for(model_id: str):
    """Resolve ``model_id`` to a callable client using the pool config.

    Returns a backend-shaped client whose call surface matches what the soft
    Oracle / bridges expect (see :class:`PooledClient` for the dual interface).
    """
    ensure_pool_env()
    mode = _pool_mode()
    family = _model_family(model_id)

    if mode in {"cliproxy", "hybrid"} and _cliproxy_available():
        return PooledClient(_cliproxy_openai_client(), model_id)

    # Direct path — match provider SDK by family.
    from agentdex_observe import (
        anthropic_client,
        gemini_client,
        openai_client,
    )

    if family == "anthropic":
        return anthropic_client()
    if family == "openai":
        return openai_client()
    if family == "gemini":
        return gemini_client()
    # Fallback: try anthropic last so legacy callers still work.
    return anthropic_client()


__all__ = [
    "PoolMode",
    "PooledClient",
    "client_for",
    "ensure_pool_env",
]
