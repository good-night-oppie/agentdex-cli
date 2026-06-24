from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import pytest


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "llm_proxy_measure.py"
    spec = importlib.util.spec_from_file_location("llm_proxy_measure", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_percentile_uses_nearest_rank_for_small_tail_samples():
    mod = _load_module()
    assert mod._percentile([10.0, 200.0], 0.95) == 200.0
    assert mod._percentile([10.0, 20.0, 30.0, 400.0], 0.95) == 400.0


def test_default_arena_proxy_uses_builder_token(monkeypatch):
    mod = _load_module()
    for name in (
        "ADX_BUILDER_PROXY_URL",
        "AI_BUILDER_PROXY_URL",
        "PURE100_PROXY_URL",
        "OPENAI_BASE_URL",
        "PURE100_PROXY_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AI_BUILDER_TOKEN", "builder-token")

    cfg = mod._select_proxy_config(None, None)

    assert cfg.base_url == mod.DEFAULT_ARENA_PROXY_URL
    assert cfg.token == "builder-token"
    assert cfg.token_env == "AI_BUILDER_TOKEN"


def test_explicit_openai_base_url_requires_matching_openai_key(monkeypatch):
    mod = _load_module()
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example/v1")
    monkeypatch.setenv("AI_BUILDER_TOKEN", "builder-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(SystemExit, match="OPENAI_API_KEY"):
        mod._select_proxy_config("https://openai.example/v1", None)


def test_run_level_releases_workers_from_shared_start_event():
    mod = _load_module()
    src = inspect.getsource(mod._run_level)
    assert "threading.Event()" in src
    assert "start_event.wait()" in src
    assert "start_event.set()" in src
