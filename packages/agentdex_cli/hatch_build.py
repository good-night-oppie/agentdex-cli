"""Hatch build hook: vendor the arena2d browser viewer into the package.

``adx arena play --ui`` serves the static arena2d viewer. Its single source of truth is the
repo-root ``web/arena2d/`` (also published as the dev site), which lives OUTSIDE this package
project — so it cannot ship in the wheel/sdist on its own. A static out-of-tree
``force-include = "../../web/arena2d"`` only works for a wheel built from a repo checkout: the
sdist would omit the assets, and a wheel built from the published sdist
(``pip install --no-binary``) would fail because ``../../web/arena2d`` does not exist in the
extracted sdist (PR #616 review).

This hook copies ``web/arena2d`` into a build-scratch dir ``_arena2d/`` at build time and
force-includes it, so the assets ship inside BOTH the wheel and the sdist from every build
context:

  * repo / sdist-from-repo: ``../../web/arena2d`` exists -> (re)materialize ``_arena2d/``;
  * wheel-from-extracted-sdist (``pip install --no-binary``): the source is gone but the
    sdist already shipped ``_arena2d/`` -> reuse it as-is;
  * neither present -> raise (a genuinely broken tree fails the build loudly).

``_arena2d/`` is deliberately OUTSIDE ``src/`` so the ``packages = ["src/agentdex_cli"]``
file walk never also picks it up (that would double-add it to the wheel alongside the
force-include). It is git-ignored build output (see .gitignore); force-include maps it to
``agentdex_cli/arena2d/`` in the wheel, where ``find_arena2d_dir`` resolves it as
``<module dir>/arena2d`` from an installed wheel with no repo checkout.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class Arena2dVendorHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        root = Path(self.root)
        staging = root / "_arena2d"
        repo_src = root.parent.parent / "web" / "arena2d"
        if (repo_src / "index.html").is_file():
            # Repo or sdist-from-repo build: refresh the staged copy from the source of truth.
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(repo_src, staging)
        elif not (staging / "index.html").is_file():
            raise RuntimeError(
                "arena2d assets missing: neither the repo-root web/arena2d nor the staged "
                f"{staging} is present; cannot build the --ui viewer into the package"
            )
        # Ship the staged copy in whichever distribution is being built. force_include keys are
        # source paths (the copy exists in every context above); values are dist paths:
        #   wheel -> agentdex_cli/arena2d/ (importable next to arena_ui.py)
        #   sdist -> _arena2d/ (so a wheel built from the extracted sdist finds it again)
        target = "agentdex_cli/arena2d" if self.target_name == "wheel" else "_arena2d"
        build_data.setdefault("force_include", {})[str(staging)] = target
