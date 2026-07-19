"""#706 — openbox<->bridges contract. Gates 1-3.

Every test here runs against a REAL stdlib http.server on an ephemeral loopback
port that returns a chosen `model` in the response body. No API calls, no spend,
no mocked dispatch — the point of #706 is what happens when the thing that
answers is not the thing we asked for, and a monkeypatched dispatch cannot
exercise that.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from agentdex_cli.openbox_cmd import OpenboxError, bindings_from_doc, validate_openbox_doc
from agentdex_cli.run_cmd import (
    SUBSTITUTED_RECEIPT_KIND,
    FrontierSeedLedger,
    _dispatch_bridges,
)


def _serving(model_name: str):
    """An Anthropic-shaped gateway that always answers as ``model_name``."""

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("content-length") or 0))
            body = json.dumps(
                {
                    "model": model_name,
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 1000, "output_tokens": 1000},
                }
            ).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def _binding(**kw):
    doc = {
        "version": 1,
        "backends": {
            "claude-opus": {
                "kind": "anthropic-endpoint",
                "invoke": "x",
                "token_ref": "none",
                **kw,
            }
        },
    }
    return bindings_from_doc(validate_openbox_doc(doc))


# --------------------------- gate 1: binding resolution -------------------- #


def test_bound_name_dispatches_to_its_own_base_url():
    srv, url = _serving("deepseek-v4-flash")
    try:
        out = _dispatch_bridges(
            ["claude-opus"],
            task="t",
            max_tokens=16,
            timeout=5,
            base_url="http://127.0.0.1:1",  # default would refuse-connect
            bindings=_binding(base_url=url, serves_model="deepseek-v4-flash"),
        )
    finally:
        srv.shutdown()
    assert len(out) == 1, "bound name must reach its backend, not the default gateway"
    assert out[0]["served_model"] == "deepseek-v4-flash"


def test_unbound_name_uses_the_default_gateway():
    srv, url = _serving("claude-opus")
    try:
        out = _dispatch_bridges(
            ["claude-opus"], task="t", max_tokens=16, timeout=5, base_url=url, bindings={}
        )
    finally:
        srv.shutdown()
    assert out[0]["served_model"] == "claude-opus"
    assert out[0]["receipt_kind"] != SUBSTITUTED_RECEIPT_KIND


def test_serves_model_match_is_a_normal_receipt():
    srv, url = _serving("deepseek-v4-flash")
    try:
        out = _dispatch_bridges(
            ["claude-opus"],
            task="t",
            max_tokens=16,
            timeout=5,
            base_url=url,
            bindings=_binding(base_url=url, serves_model="deepseek-v4-flash"),
        )
    finally:
        srv.shutdown()
    assert out[0]["receipt_kind"] != SUBSTITUTED_RECEIPT_KIND


def test_mismatch_is_quarantined(capsys):
    srv, url = _serving("deepseek-v4-flash")
    try:
        out = _dispatch_bridges(
            ["claude-opus"],
            task="t",
            max_tokens=16,
            timeout=5,
            base_url=url,
            bindings=_binding(base_url=url, serves_model="claude-opus-4-8"),
        )
    finally:
        srv.shutdown()
    assert out[0]["receipt_kind"] == SUBSTITUTED_RECEIPT_KIND
    assert "SUBSTITUTED" in capsys.readouterr().out


# ------------------- gate 1b: quarantine excludes from selection ------------ #


def _ledger_with_substituted(tmp_path: Path) -> FrontierSeedLedger:
    led = FrontierSeedLedger(tmp_path / "seeds.jsonl")
    led.append(
        signature="s",
        model="claude-opus",
        scores={"quality": 0.5, "cost_dollar": 0.001, "wall_clock_sec": 1.0},
        ts="2026-07-19T00:00:00+00:00",
        receipt_kind=SUBSTITUTED_RECEIPT_KIND,
        served_model="deepseek-v4-flash",
    )
    led.append(
        signature="s",
        model="codex-gpt-5.6",
        scores={"quality": 0.5, "cost_dollar": 0.900, "wall_clock_sec": 9.0},
        ts="2026-07-19T00:00:01+00:00",
        receipt_kind="adx-run-bridges",
        served_model="codex-gpt-5.6",
    )
    return led


def test_substituted_row_never_wins_selection(tmp_path):
    """The substituted row is cheaper and faster — it must still not be chosen."""
    led = _ledger_with_substituted(tmp_path)
    assert led.best_model("s", ["cost"], None) == "codex-gpt-5.6"


def test_substituted_row_is_excluded_from_export_but_kept_on_disk(tmp_path):
    led = _ledger_with_substituted(tmp_path)
    out = json.loads(led.export_frontier().read_text(encoding="utf-8"))
    assert "claude-opus" not in json.dumps(out), "substituted row must not be exported"
    raw = (tmp_path / "seeds.jsonl").read_text(encoding="utf-8")
    assert "claude-opus" in raw, "substituted row must remain in the JSONL for audit"
    assert '"served_model": "deepseek-v4-flash"' in raw


# ----------------------------- gate 2: pricing ----------------------------- #


def test_priced_on_served_model_not_requested(tmp_path):
    """claude-opus rates are ~50x deepseek's; pricing the requested name fabricates cost."""
    srv, url = _serving("deepseek-v4-flash")
    try:
        served = _dispatch_bridges(
            ["claude-opus"], task="t", max_tokens=16, timeout=5, base_url=url, bindings={}
        )
        srv.shutdown()
        srv2, url2 = _serving("claude-opus")
        requested = _dispatch_bridges(
            ["claude-opus"], task="t", max_tokens=16, timeout=5, base_url=url2, bindings={}
        )
        srv2.shutdown()
    finally:
        pass
    assert served[0]["scores"]["cost_dollar"] < requested[0]["scores"]["cost_dollar"]


# ---------------------------- gate 3: loopback ----------------------------- #


def test_non_loopback_base_url_is_rejected_naming_the_backend():
    doc = {
        "version": 1,
        "backends": {
            "b": {
                "kind": "anthropic-endpoint",
                "invoke": "x",
                "token_ref": "none",
                "base_url": "http://evil.example.com",
            }
        },
    }
    # openbox validation accepts the type; dispatch-time enforcement refuses it.
    b = bindings_from_doc(validate_openbox_doc(doc))
    from agentdex_cli.run_cmd import require_loopback_base_url

    with pytest.raises(ValueError):
        require_loopback_base_url(b["b"].base_url)


def test_binding_fields_are_type_checked():
    for bad in (123, ""):
        doc = {
            "version": 1,
            "backends": {
                "b": {
                    "kind": "anthropic-endpoint",
                    "invoke": "x",
                    "token_ref": "none",
                    "serves_model": bad,
                }
            },
        }
        with pytest.raises(OpenboxError):
            validate_openbox_doc(doc)
