"""Local arena2d browser UI for ``adx arena play --ui``.

Serves the static arena2d viewer (``web/arena2d/``, unmodified on disk) on a local
port and exposes ``/live.json`` — a PS-replay-shaped snapshot of the in-progress
battle's raw Showdown protocol LOG. A background thread tails the arena's live SSE
stream, whose per-frame ``lines`` are exactly the raw protocol arena2d animates, and
appends them to a buffer.

Design notes:
- The BROWSER only ever talks to this local server (same-origin, no auth). The
  arena-side connection lives in the Python bridge thread, so no bearer token is
  ever exposed to the page.
- For the LOCAL player watching their OWN battle we tail the AUTHENTICATED owner
  stream (``GET /me/battle/{id}/live``) with the bearer token attached *server-side*
  in the bridge thread, so the viewer keeps the owner's own-side fog-of-war
  (``|split|`` private lines) instead of the public spectator projection's HP-%
  downgrade (PR #614 review). When no token is available we fall back to the PUBLIC
  spectator stream (``GET /battle/{id}/live``), which is unauthenticated by design.
- We do NOT edit any arena2d asset. ``web/arena2d/index.html`` already ships
  ``trace-loader.js``, which — given ``?trace=<url>`` — fetches a PS-replay-shaped
  doc (``{log, decisions}``), installs it as ``window.__ARENA2D_DATA``, then boots
  the engine (dex/battle/mind/anim), falling back to the baked ``data.js`` on any
  error. So the URL we open is just ``/?trace=/live.json`` and the loader does the
  rest — no script-block surgery, fully file://-compatible viewer left intact.
- ``trace-loader.js`` reads the endpoint once at load, so ``/live.json`` is a
  snapshot: reloading the page (or opening it after the match) renders the battle
  up to that point — the full animated replay is one reload away.

A human-played battle carries no LLM rationales, so ``decisions`` is always ``[]``
here (the spectator projection strips ``|-reasoning|`` / ``|say|`` anyway); the
viewer simply animates the real Showdown log without the rationale panel.
"""

from __future__ import annotations

import functools
import http.server
import json
import logging
import os
import threading
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import httpx

_log = logging.getLogger(__name__)


def find_arena2d_dir() -> Path | None:
    """Locate the on-disk ``web/arena2d`` viewer directory, or ``None``.

    Resolution order:

    1. ``ADX_ARENA2D_DIR`` wins when set (and points at a dir with an ``index.html``).
    2. The copy bundled *inside* the installed package (``agentdex_cli/arena2d/``) — hatch
       ``force-include``s ``web/arena2d`` there at wheel-build time, so ``adx arena play
       --ui`` works out of the box from a ``pip install``ed wheel with no repo checkout
       and no env override (PR #614 review).
    3. A walk up from the CWD and from this module's location looking for
       ``web/arena2d/index.html`` — covers a source checkout / editable install, where the
       bundled copy does not exist on disk but the repo-root ``web/arena2d`` does.

    ``None`` when nothing matches (the caller then degrades gracefully and runs the battle
    without the browser UI)."""
    env = os.environ.get("ADX_ARENA2D_DIR")
    if env:
        p = Path(env).expanduser()
        return p if (p / "index.html").is_file() else None
    packaged = Path(__file__).resolve().parent / "arena2d"
    if (packaged / "index.html").is_file():
        return packaged
    seen: set[Path] = set()
    for anchor in (Path.cwd(), Path(__file__).resolve().parent):
        cur = anchor
        for _ in range(10):
            cand = cur / "web" / "arena2d"
            if cand not in seen:
                seen.add(cand)
                if (cand / "index.html").is_file():
                    return cand
            if cur.parent == cur:
                break
            cur = cur.parent
    return None


def parse_sse_events(lines: Iterable[str]) -> Iterator[tuple[str, Any]]:
    """Parse a Server-Sent-Events line stream into ``(event_name, data_obj)`` tuples.

    Pure + synchronous so it is unit-testable off any line iterable. ``data:`` values
    are accumulated (newline-joined) and JSON-decoded on the event's terminating blank
    line; a malformed ``data`` payload yields ``None``. ``event:`` defaults to
    ``"message"``. Comment lines (leading ``:``) are ignored. A trailing event with no
    final blank line is still flushed."""
    event = "message"
    data_parts: list[str] = []

    def _decode(parts: list[str]) -> Any:
        try:
            return json.loads("\n".join(parts))
        except ValueError:
            return None

    for raw in lines:
        line = raw.rstrip("\n").rstrip("\r")
        if line == "":
            if data_parts:
                yield event, _decode(data_parts)
            event = "message"
            data_parts = []
            continue
        if line.startswith(":"):
            continue
        field, sep, value = line.partition(":")
        if sep and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event = value
        elif field == "data":
            data_parts.append(value)
    if data_parts:
        yield event, _decode(data_parts)


def live_stream_request(
    arena_base: str, battle_id: str, token: str | None
) -> tuple[str, dict[str, str]]:
    """The (url, headers) the bridge tails for this battle. With a ``token`` it is the
    AUTHENTICATED owner stream ``/me/battle/{id}/live`` + a server-side ``Authorization:
    Bearer`` header (own-side fog-of-war preserved); without one it is the PUBLIC
    spectator stream ``/battle/{id}/live`` (no auth). Pure, so the selection is unit-
    testable without a live arena. The header never reaches the browser — the page only
    talks to the local server."""
    base = arena_base.rstrip("/")
    if token:
        return f"{base}/me/battle/{battle_id}/live", {"Authorization": f"Bearer {token}"}
    return f"{base}/battle/{battle_id}/live", {}


class _LiveBuffer:
    """Thread-safe accumulator of the raw protocol ``lines`` seen across SSE frames.

    The spectator stream emits each frame's OWN new protocol lines (not cumulative),
    so concatenating them in arrival order reconstructs the full battle log — exactly
    what arena2d animates."""

    def __init__(self, battle_id: str) -> None:
        self.battle_id = battle_id
        self._lines: list[str] = []
        self.ended = False
        self._lock = threading.Lock()

    def ingest(self, frame: Any) -> None:
        """Append one spectator frame's protocol lines (a no-op for non-dict frames)."""
        if not isinstance(frame, dict):
            return
        new = frame.get("lines") or []
        if not isinstance(new, list):
            return
        with self._lock:
            self._lines.extend(str(x) for x in new)

    def trace_doc(self) -> dict[str, Any]:
        """The PS-replay-shaped snapshot ``trace-loader.js`` consumes: ``{log, decisions}``.

        ``log`` is the newline-joined protocol; ``decisions`` is empty (a human battle
        carries no LLM rationales, and the spectator projection strips them anyway)."""
        with self._lock:
            log = "\n".join(self._lines)
        return {"log": log, "decisions": []}


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Static file handler for ``web/arena2d`` that also answers ``/live.json``."""

    def do_GET(self) -> None:  # noqa: N802 — http.server API
        if self.path.split("?", 1)[0] == "/live.json":
            buf: _LiveBuffer = self.server.live_buffer  # type: ignore[attr-defined]
            body = json.dumps(buf.trace_doc()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *args: Any) -> None:  # silence stdlib request logging
        pass


class ArenaUiServer:
    """Serves arena2d + ``/live.json`` and bridges the arena spectator SSE into it."""

    def __init__(
        self, web_dir: Path, arena_base: str, battle_id: str, token: str | None = None
    ) -> None:
        self.web_dir = Path(web_dir)
        self.arena_base = arena_base.rstrip("/")
        self.battle_id = battle_id
        self.token = token  # owner stream + Bearer when set; public spectator when None
        self.buf = _LiveBuffer(battle_id)
        self.url = ""
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._serve_thread: threading.Thread | None = None
        self._bridge_thread: threading.Thread | None = None
        self._resp: httpx.Response | None = None
        self._stop = threading.Event()

    def start(self) -> str:
        """Bind an ephemeral localhost port, start the static+JSON server and the SSE
        bridge thread, and return the browser URL (``/?trace=/live.json``)."""
        handler = functools.partial(_Handler, directory=str(self.web_dir))
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        httpd.live_buffer = self.buf  # type: ignore[attr-defined]
        self._httpd = httpd
        port = httpd.server_address[1]
        self.url = f"http://127.0.0.1:{port}/?trace=/live.json"

        try:
            self._serve_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            self._serve_thread.start()
            self._bridge_thread = threading.Thread(target=self._bridge, daemon=True)
            self._bridge_thread.start()
        except Exception:  # noqa: BLE001
            # Thread creation failed (e.g. resource exhaustion). serve_forever() never
            # started, so close the bound socket DIRECTLY — calling shutdown() here would
            # block forever waiting on an event only serve_forever()'s loop ever sets.
            httpd.server_close()
            self._httpd = None
            raise
        return self.url

    def _bridge(self) -> None:
        """Tail the live SSE (owner stream with the bearer token when set, else the
        public spectator stream) and ingest each frame's protocol lines.

        Best-effort: any network/parse failure ends the bridge quietly (the buffer
        keeps whatever it captured; the page still renders that prefix). The bearer
        header is sent ONLY on the arena-side connection — never to the browser."""
        live_url, headers = live_stream_request(self.arena_base, self.battle_id, self.token)
        # read=None on purpose: a human battle is SILENT between turns (the gateway
        # sends no heartbeat), so a finite read timeout would drop the stream mid-match.
        # stop() instead closes self._resp to unblock a parked read promptly.
        try:
            with httpx.stream(
                "GET", live_url, headers=headers, timeout=httpx.Timeout(10.0, read=None)
            ) as resp:
                self._resp = resp
                if resp.status_code != 200:
                    return
                for event, data in parse_sse_events(resp.iter_lines()):
                    if self._stop.is_set():
                        return
                    if event == "end":
                        self.buf.ended = True
                        return
                    self.buf.ingest(data)
        except Exception as e:  # noqa: BLE001 — best-effort; a closed stream lands here on stop()
            _log.debug("arena2d spectator bridge ended: %s", e)
        finally:
            self._resp = None

    def stop(self) -> None:
        """Stop the SSE bridge and shut the local server down (idempotent)."""
        self._stop.set()
        resp = self._resp
        if resp is not None:
            try:
                resp.close()  # unblock a parked iter_lines() read in the bridge thread
            except Exception:  # noqa: BLE001
                pass
        bridge = self._bridge_thread
        if bridge is not None and bridge.is_alive():
            bridge.join(timeout=2.0)
        httpd = self._httpd
        if httpd is not None:
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
            self._httpd = None
