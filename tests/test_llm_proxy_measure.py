from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest

_PROXY_ENV_NAMES = (
    "ADX_BUILDER_PROXY_URL",
    "AI_BUILDER_PROXY_URL",
    "PURE100_PROXY_URL",
    "OPENAI_BASE_URL",
    "AI_BUILDER_TOKEN",
    "PURE100_PROXY_KEY",
    "OPENAI_API_KEY",
)


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "llm_proxy_measure.py"
    spec = importlib.util.spec_from_file_location("llm_proxy_measure", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _clear_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _PROXY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_percentile_uses_nearest_rank_for_small_tail_samples():
    mod = _load_module()
    assert mod._percentile([10.0, 200.0], 0.95) == 200.0
    assert mod._percentile([10.0, 20.0, 30.0, 400.0], 0.95) == 400.0


def test_default_arena_proxy_uses_builder_token(monkeypatch):
    mod = _load_module()
    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv("AI_BUILDER_TOKEN", "builder-token")

    cfg = mod._select_proxy_config(None, None)

    assert cfg.base_url == mod.DEFAULT_ARENA_PROXY_URL
    assert cfg.token == "builder-token"
    assert cfg.token_env == "AI_BUILDER_TOKEN"


def test_ai_builder_proxy_url_beats_arena_default(monkeypatch):
    mod = _load_module()
    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv("AI_BUILDER_PROXY_URL", "https://builder.example/backend/v1")
    monkeypatch.setenv("AI_BUILDER_TOKEN", "builder-token")

    cfg = mod._select_proxy_config(None, None)

    assert cfg.base_url == "https://builder.example/backend/v1"
    assert cfg.token == "builder-token"
    assert cfg.token_env == "AI_BUILDER_TOKEN"


def test_explicit_openai_base_url_requires_matching_openai_key(monkeypatch):
    mod = _load_module()
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example/v1")
    monkeypatch.setenv("AI_BUILDER_TOKEN", "builder-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(SystemExit, match="OPENAI_API_KEY"):
        mod._select_proxy_config("https://openai.example/v1", None)


def test_done_json_reports_selected_proxy_when_base_url_omitted(monkeypatch, capsys):
    mod = _load_module()
    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv("AI_BUILDER_TOKEN", "builder-token")
    monkeypatch.setattr(sys, "argv", ["llm_proxy_measure.py", "--levels", "1", "--skip-usage"])
    def _fake_run_level(level, **kwargs):  # noqa: ARG001
        return {
            "concurrency": level,
            "requests": 1,
            "ok": 1,
            "errors": 0,
            "latency_ms_p50": 1.0,
            "latency_ms_p95": 1.0,
            "status_counts": {"200": 1},
        }

    monkeypatch.setattr(mod, "_run_level", _fake_run_level)

    assert mod.main() == 0

    done_line = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("DONE_JSON ")
    ][0]
    payload = json.loads(done_line.removeprefix("DONE_JSON "))
    assert payload["base_url"] == "https://space.ai-builders.com/..."


def test_run_level_releases_workers_from_shared_start_event():
    mod = _load_module()
    src = inspect.getsource(mod._run_level)
    assert "threading.Event()" in src
    assert "start_event.wait()" in src
    assert "start_event.set()" in src
