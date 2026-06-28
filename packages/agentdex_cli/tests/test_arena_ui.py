"""Tests for the ``adx arena play --ui`` arena2d browser bridge (``arena_ui``).

The bridge has three independently-testable seams: the pure SSE parser, the
``_LiveBuffer`` → PS-replay (``{log, decisions}``) projection that ``trace-loader.js``
consumes, and the local HTTP server that serves ``web/arena2d`` + ``/live.json``.
No live arena is needed — the spectator bridge is best-effort and stays silent when
it cannot connect, which is exactly what the serve test exercises.
"""

from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlsplit

from agentdex_cli.arena_ui import (
    ArenaUiServer,
    _LiveBuffer,
    find_arena2d_dir,
    parse_sse_events,
)


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
