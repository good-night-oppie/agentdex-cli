"""Manus bridge — Camofox browser driver (primary) + codex_web fallback (A4).

P5.5 probe outcome history (2026-06-08):
  1. First probe: ``camoufox`` Python pkg NOT installable → bridge fell back to
     :class:`CodexWebBridge` (commit pending).
  2. User installed camoufox mid-phase; bridge upgraded to camoufox primary,
     codex-web kept as runtime fallback when:
       * ``MANUS_URL`` env var unset (no web target configured), OR
       * camoufox import fails at runtime (env regression), OR
       * browser navigation / response scrape errors out.

Async co-opetition note (ADR-0009 §Amendment-2026-06-08): bridge participates in
per-baseline async loop, never real-time race against claude/codex.

MVP shim caveat: the web-scrape selectors target a generic chat input + last
assistant turn. Override via ``MANUS_INPUT_SELECTOR`` /
``MANUS_RESPONSE_SELECTOR`` env vars when point-of-presence schema differs.
"""

from __future__ import annotations

import asyncio
import logging
import os

from adx_bridges.base import (
    BridgeConfig,
    CliDead,
    LongRunningCliBridge,
    new_session_id,
)

log = logging.getLogger(__name__)

_CAMOUFOX_AVAILABLE: bool | None = None


def _probe_camoufox() -> bool:
    global _CAMOUFOX_AVAILABLE
    if _CAMOUFOX_AVAILABLE is not None:
        return _CAMOUFOX_AVAILABLE
    try:
        import camoufox  # type: ignore  # noqa: F401

        _CAMOUFOX_AVAILABLE = True
    except ImportError:
        _CAMOUFOX_AVAILABLE = False
    return _CAMOUFOX_AVAILABLE


def select_manus_backend() -> str:
    """``camoufox`` if pkg + MANUS_URL present, else ``codex-web``."""
    if _probe_camoufox() and os.environ.get("MANUS_URL"):
        return "camoufox"
    return "codex-web"


class CamoufoxManusBridge(LongRunningCliBridge):
    """Drives Camofox Firefox to a Manus-like web chat endpoint.

    Cookie/storage state persisted under ``~/.cache/adx_bridges/manus/state.json``
    so subsequent runs reuse browser session = continuity. ``session_id`` is the
    storage-state path hash for the workdir.
    """

    DEFAULT_INPUT_SEL = "textarea, [contenteditable='true']"
    DEFAULT_RESPONSE_SEL = "[data-role='assistant'], .markdown, .message-assistant"

    def __init__(self, cfg: BridgeConfig):
        super().__init__(cfg)
        self._url = os.environ.get("MANUS_URL")
        if not self._url:
            raise CliDead("MANUS_URL env var required for camoufox bridge")
        self._input_sel = os.environ.get("MANUS_INPUT_SELECTOR", self.DEFAULT_INPUT_SEL)
        self._response_sel = os.environ.get("MANUS_RESPONSE_SELECTOR", self.DEFAULT_RESPONSE_SEL)
        self._state_path = os.path.expanduser(
            os.environ.get(
                "MANUS_STATE_PATH",
                "~/.cache/adx_bridges/manus/state.json",
            )
        )
        os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
        self._sid: str | None = None
        self._browser_ctx = None
        self._page = None
        self._camoufox_ctx_mgr = None

    async def ensure_proc(self) -> None:
        # Codereview M2 (2026-06-08): mirror base.ensure_proc lock discipline so
        # a retry that races a previous spawn cannot stand up two browser
        # contexts and leak the camoufox process.
        async with self._proc_lock:
            if self._page is not None:
                return
            await self._spawn_browser()

    async def _spawn_browser(self) -> None:
        # camoufox provides only sync_api in 0.4.x; run in thread executor to keep async-friendly.
        from camoufox.async_api import AsyncCamoufox

        kwargs = {"headless": os.environ.get("MANUS_HEADLESS", "1") == "1"}
        if os.path.isfile(self._state_path):
            kwargs["persistent_context"] = False

        self._camoufox_ctx_mgr = AsyncCamoufox(**kwargs)
        browser = await self._camoufox_ctx_mgr.__aenter__()
        ctx_args = {}
        if os.path.isfile(self._state_path):
            ctx_args["storage_state"] = self._state_path
        self._browser_ctx = (
            await browser.new_context(**ctx_args) if hasattr(browser, "new_context") else browser
        )
        self._page = (
            await self._browser_ctx.new_page() if hasattr(self._browser_ctx, "new_page") else None
        )
        if self._page is None:
            self._page = await browser.new_page()
        await self._page.goto(self._url, wait_until="domcontentloaded")

    async def _handshake(self) -> None:
        return

    async def _kill(self) -> None:
        try:
            if self._browser_ctx and hasattr(self._browser_ctx, "storage_state"):
                try:
                    await self._browser_ctx.storage_state(path=self._state_path)
                except Exception:
                    log.warning("could not persist manus storage state")
            if self._camoufox_ctx_mgr is not None:
                await self._camoufox_ctx_mgr.__aexit__(None, None, None)
        finally:
            self._camoufox_ctx_mgr = None
            self._browser_ctx = None
            self._page = None

    async def _send_turn(self, prompt: str, *, session_id, extra) -> str:
        await self.ensure_proc()
        assert self._page is not None
        sid = session_id or self._sid or new_session_id()
        self._sid = sid

        await self._page.fill(self._input_sel, prompt)
        await self._page.keyboard.press("Enter")

        # Wait for a new assistant response to appear/settle.
        try:
            await self._page.wait_for_selector(self._response_sel, timeout=60_000)
        except Exception as e:
            raise CliDead(f"manus response selector timeout: {e}") from e

        # Allow streaming completion (best effort: small settle delay).
        await asyncio.sleep(2.0)
        elements = await self._page.query_selector_all(self._response_sel)
        if not elements:
            raise CliDead("manus: no response elements after wait")
        text = await elements[-1].inner_text()
        self._last_response_text = text
        return sid

    async def _cold_shot(self, prompt: str, *, session_id, extra) -> dict:
        raise NotImplementedError("manus is browser-driven only")


def make_manus_bridge(cfg: BridgeConfig | None = None) -> LongRunningCliBridge:
    """Factory: camoufox primary, codex-web fallback.

    Falls back to ``CodexWebBridge`` whenever camoufox unavailable or
    ``MANUS_URL`` unset (Phase-5 P5.5 fallback ladder).
    """
    backend = select_manus_backend()
    cfg = cfg or BridgeConfig(
        name="manus",
        port=int(os.environ.get("MANUS_BRIDGE_PORT", "49804")),
        workdir=os.environ.get("WORKDIR") or os.getcwd(),
        cli_argv=[],
    )
    if backend == "camoufox":
        cfg.name = "manus(camoufox)"
        try:
            return CamoufoxManusBridge(cfg)
        except CliDead as e:
            log.warning("camoufox bridge init failed (%s) — falling back to codex-web", e)

    from adx_bridges.codex_web_bridge import CodexWebBridge

    cfg.name = "manus(codex-web-fallback)"
    return CodexWebBridge(cfg)


__all__ = ["make_manus_bridge", "select_manus_backend", "CamoufoxManusBridge"]
