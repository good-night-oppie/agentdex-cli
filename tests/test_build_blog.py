from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def load_builder() -> ModuleType:
    script = Path(__file__).resolve().parents[1] / "site" / "build-blog.py"
    spec = importlib.util.spec_from_file_location("build_blog", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def point_builder_at_tmp(module: ModuleType, tmp_path: Path) -> None:
    module.ROOT = tmp_path
    module.BLOG = tmp_path / "blog"
    module.SITE = tmp_path / "site"
    module.OUT = module.SITE / "blog"
    module.ZH_OUT = module.SITE / "zh" / "blog"


def test_build_refuses_to_clear_output_when_source_tree_missing(tmp_path: Path) -> None:
    builder = load_builder()
    point_builder_at_tmp(builder, tmp_path)
    stale = builder.OUT / "old-post.html"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")

    with pytest.raises(SystemExit, match="source directory missing"):
        builder.build()

    assert stale.read_text(encoding="utf-8") == "stale"


def test_build_allows_empty_source_tree_and_clears_stale_output(tmp_path: Path) -> None:
    builder = load_builder()
    point_builder_at_tmp(builder, tmp_path)
    builder.BLOG.mkdir()
    stale_en = builder.OUT / "old-post.html"
    stale_zh = builder.ZH_OUT / "old-post.html"
    stale_en.parent.mkdir(parents=True)
    stale_zh.parent.mkdir(parents=True)
    stale_en.write_text("stale en", encoding="utf-8")
    stale_zh.write_text("stale zh", encoding="utf-8")

    builder.build()

    assert not stale_en.exists()
    assert not stale_zh.exists()
    assert (builder.OUT / "index.html").is_file()
    assert (builder.ZH_OUT / "index.html").is_file()
