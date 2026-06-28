"""Tests for the ``adx arena play --ui`` arena2d browser bridge (``arena_ui``).

The bridge has three independently-testable seams: the pure SSE parser, the
``_LiveBuffer`` → PS-replay (``{log, decisions}``) projection that ``trace-loader.js``
consumes, and the local HTTP server that serves ``web/arena2d`` + ``/live.json``.
No live arena is needed — the spectator bridge is best-effort and stays silent when
it cannot connect, which is exactly what the serve test exercises.
"""

from __future__ import annotations

import http.server
import json
import threading
import time
import urllib.request
from urllib.parse import urlsplit

from agentdex_cli import arena_ui
from agentdex_cli.arena_ui import (
    ArenaUiServer,
    _LiveBuffer,
    find_arena2d_dir,
    live_stream_candidates,
    parse_sse_events,
)


def test_live_stream_candidates_tries_owner_then_public_with_token():
    cands = live_stream_candidates("http://arena.test/", "b1", "tok-abc")
    assert cands == [
        # 1st: AUTHENTICATED owner stream (own-side fog-of-war) with the bearer header
        ("http://arena.test/me/battle/b1/live", {"Authorization": "Bearer tok-abc"}),
        # 2nd: PUBLIC spectator fallback — the CLI consent token 403s on the owner stream,
        # so the viewer falls back to the public projection instead of staying empty.
        ("http://arena.test/battle/b1/live", {}),
    ]


def test_live_stream_candidates_is_public_only_without_token():
    cands = live_stream_candidates("http://arena.test", "b1", None)
    assert cands == [("http://arena.test/battle/b1/live", {})]  # PUBLIC, unauthenticated


def test_parse_sse_events_yields_data_and_end():
    stream = [
        ": keep-alive comment",
        'data: {"turn": 1, "lines": ["|turn|1"]}',
        "",
        "event: end",
        'data: {"replay": "/replay/b1"}',
        "",
    ]
    events = list(parse_sse_events(stream))
    assert events[0] == ("message", {"turn": 1, "lines": ["|turn|1"]})
    assert events[1][0] == "end"
    assert events[1][1] == {"replay": "/replay/b1"}


def test_parse_sse_events_malformed_data_is_none_and_trailing_flushes():
    # A trailing event with no terminating blank line must still flush; bad JSON -> None.
    events = list(parse_sse_events(["data: not-json"]))
    assert events == [("message", None)]


def test_live_buffer_concatenates_frame_lines_in_order():
    buf = _LiveBuffer("b1")
    assert buf.trace_doc() == {"log": "", "decisions": []}
    buf.ingest({"lines": ["|turn|1", "|move|p1a: Pikachu|Thunderbolt"]})
    buf.ingest({"lines": ["|turn|2"]})
    buf.ingest("not-a-dict")  # ignored
    buf.ingest({"lines": "not-a-list"})  # ignored
    assert buf.trace_doc() == {
        "log": "|turn|1\n|move|p1a: Pikachu|Thunderbolt\n|turn|2",
        "decisions": [],
    }


def test_find_arena2d_dir_honors_env_override(tmp_path, monkeypatch):
    web = tmp_path / "viewer"
    web.mkdir()
    (web / "index.html").write_text("<html></html>")
    monkeypatch.setenv("ADX_ARENA2D_DIR", str(web))
    assert find_arena2d_dir() == web
    # Pointing at a dir without an index.html resolves to None (no silent half-serve).
    monkeypatch.setenv("ADX_ARENA2D_DIR", str(tmp_path / "missing"))
    assert find_arena2d_dir() is None


def test_find_arena2d_dir_resolves_packaged_copy(tmp_path, monkeypatch):
    # Simulate an installed wheel: hatch force-include drops web/arena2d next to the module
    # as agentdex_cli/arena2d/. With no env override and a CWD that has no web/arena2d, only
    # the packaged-copy branch can match — so --ui works from a pip-installed wheel with no
    # repo checkout (PR #614 review).
    pkg = tmp_path / "agentdex_cli"
    (pkg / "arena2d").mkdir(parents=True)
    (pkg / "arena2d" / "index.html").write_text("<title>arena2d</title>")
    monkeypatch.delenv("ADX_ARENA2D_DIR", raising=False)
    monkeypatch.setattr(arena_ui, "__file__", str(pkg / "arena_ui.py"))
    monkeypatch.chdir(tmp_path)  # no web/arena2d here → rules out the walk branch
    found = find_arena2d_dir()
    assert found is not None
    assert found.name == "arena2d"
    assert (found / "index.html").is_file()
    assert found.resolve() == (pkg / "arena2d").resolve()


def test_server_serves_static_and_live_json(tmp_path):
    web = tmp_path / "web" / "arena2d"
    web.mkdir(parents=True)
    (web / "index.html").write_text("<title>arena2d</title>")

    # arena_base points at a refused localhost port: the bridge fails silently
    # (best-effort), so /live.json reflects only what we ingest directly.
    server = ArenaUiServer(web, "http://127.0.0.1:1", "b1")
    url = server.start()
    try:
        port = urlsplit(url).port
        assert url.endswith("/?trace=/live.json")

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/live.json", timeout=5) as r:
            doc = json.loads(r.read())
        assert doc == {"log": "", "decisions": []}

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=5) as r:
            assert b"arena2d" in r.read()

        server.buf.ingest({"lines": ["|turn|1"]})
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/live.json", timeout=5) as r:
            doc = json.loads(r.read())
        assert doc == {"log": "|turn|1", "decisions": []}
    finally:
        server.stop()


def test_bridge_falls_back_to_public_spectator_when_owner_stream_403s(tmp_path):
    # PR #615 review: the CLI play path holds a *consent* token, but /me/battle/{id}/live is
    # session-authed and 403s it. The bridge must fall back to the PUBLIC /battle/{id}/live
    # spectator stream instead of leaving the viewer empty.
    web = tmp_path / "web" / "arena2d"
    web.mkdir(parents=True)
    (web / "index.html").write_text("<title>arena2d</title>")

    hits: list[str] = []

    class _ArenaStub(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — http.server API
            hits.append(self.path)
            if self.path == "/me/battle/b1/live":  # owner stream rejects the consent token
                self.send_response(403)
                self.end_headers()
                return
            if self.path == "/battle/b1/live":  # public spectator: a tiny SSE then end
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(
                    b'data: {"lines": ["|turn|1", "|move|p1a: Pikachu|Thunderbolt"]}\n\n'
                )
                self.wfile.write(b"event: end\ndata: {}\n\n")
                self.wfile.flush()
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):  # silence stdlib request logging
            pass

    stub = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ArenaStub)
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    stub_base = f"http://127.0.0.1:{stub.server_address[1]}"
    # A consent token is present, so the bridge tries the owner stream FIRST (403) then falls back.
    server = ArenaUiServer(web, stub_base, "b1", token="consent-tok")
    server.start()
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not server.buf.trace_doc()["log"]:
            time.sleep(0.02)
        assert server.buf.trace_doc() == {
            "log": "|turn|1\n|move|p1a: Pikachu|Thunderbolt",
            "decisions": [],
        }
        assert "/me/battle/b1/live" in hits  # owner stream was tried first
        assert "/battle/b1/live" in hits  # then fell back to the public spectator stream
    finally:
        server.stop()
        stub.shutdown()
        stub.server_close()
