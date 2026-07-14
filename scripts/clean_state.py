#!/usr/bin/env python3
"""clean_state.py — the single definition of a "clean" agentdex-cli tree.

WHY THIS EXISTS (2026-07-14, redesign/evolution-market)
------------------------------------------------------
`doc_lint.py` globs the WORKING TREE. CI runs on a FRESH CLONE. Untracked files
are therefore invisible to CI but fully visible to the local gate. One untracked
`.md` under `docs/` (the harness-HA design doc sat there for 3 days) makes
DOC-LINT-020 fire -> `doc_lint --staged` exits 1 -> EVERY commit by EVERY session
in this repo is blocked, while CI stays green and nobody can see why.

The rational response to a structurally unpassable gate is `--no-verify`. That is
what happened. The gate was present but not running.

The fix is to make the local tree CONGRUENT with the CI tree: a file is either
TRACKED or IGNORED. "Neither" is not a state.

THE DOCS CAVEAT (learned the hard way, adversarial review 2026-07-14)
--------------------------------------------------------------------
For most paths, "gitignore it" is a valid resolution. For `docs/**/*.md` IT IS
NOT. doc_lint walks the filesystem with `pathlib.rglob`, which does not consult
.gitignore -- so an IGNORED .md under docs/ still trips DOC-LINT-020 and still
red-lines every commit. Telling a developer to gitignore it would send them in a
circle. The only resolutions there are: track it AND link it from AGENTS.md, or
move/delete it out of docs/. `_remedy_for()` encodes this; do not "simplify" it.

CHECKS
------
  untracked      no unignored untracked paths (path-aware remedy, see above)
  dirty          no modified/staged tracked files
  doc-lint       scripts/doc_lint.py exits 0 over the full tree
  generators     run generators, assert they did not move the tree (DELTA, so a
                 human's own WIP is not blamed on a generator)
  hook-wired     the gate is still DECLARED (config + installer). Anti-rot.
  hook-installed the gate is actually INSTALLED in this clone's hooks dir.
                 Distinct from hook-wired: a config can declare a hook that no
                 developer has ever installed. Local-only -- CI has no hooks.
  junk-paths     paths that must never be tracked (.playwright-mcp/, *.local.json)

MODES
-----
  precommit   untracked + junk-paths
              (NOT `dirty` -- staged changes ARE the commit.)
  worktree    untracked + dirty + doc-lint + hook-installed + junk-paths
  ci          generators + hook-wired + junk-paths
              (NOT `untracked` -- a fresh clone has none, so asserting it in CI
              is theater that always passes.)

EXIT CODES
----------
  0  clean      1  unclean      2  usage / internal error (never a traceback:
                                   a gate that crashes teaches people to bypass)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

EXIT_CLEAN = 0
EXIT_UNCLEAN = 1
EXIT_ERROR = 2

# `git commit --no-verify` bypasses any local hook anyway, so making this harder
# than --no-verify buys nothing but resentment. It is loud so it is greppable.
#
# It is IGNORED in --mode ci. An escape hatch that greens the authoritative gate
# is not an escape hatch, it is a hole: anyone able to set an env var in a
# workflow could turn CI green while shipping an unclean tree.
OVERRIDE_ENV = "CLEAN_STATE_OVERRIDE"
OVERRIDABLE_MODES = frozenset({"precommit", "worktree"})

GENERATORS: tuple[tuple[str, list[str]], ...] = (("sync_toc", ["bash", "scripts/sync_toc.sh"]),)

JUNK_PATTERNS: tuple[tuple[str, str], ...] = (
    (".playwright-mcp/", "browser page dumps — carry live session material (challstr nonces)"),
    ("settings.local.json", "machine-local agent settings (absolute paths, trustedFolders)"),
)

# doc_lint walks docs/ with rglob and ignores .gitignore entirely.
DOC_LINT_GLOB = re.compile(r"^docs/.*\.md$")


class Finding(NamedTuple):
    check: str
    detail: str
    remedy: str


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def repo_root() -> Path:
    cp = _run(["git", "rev-parse", "--show-toplevel"], Path.cwd())
    if cp.returncode != 0:
        raise RuntimeError("not inside a git repository")
    return Path(cp.stdout.strip())


def hooks_dir(root: Path) -> Path:
    """The REAL hooks dir.

    NOT `root/.git/hooks`. In a git worktree `.git` is a FILE ("gitdir: ..."),
    so that path is `Not a directory` and every hook operation fails. This repo
    is developed out of worktrees, so the naive path is broken in the common case.
    core.hooksPath wins when set; otherwise $GIT_COMMON_DIR/hooks, which every
    worktree of a repo SHARES.
    """
    cp = _run(["git", "config", "--get", "core.hooksPath"], root)
    if cp.returncode == 0 and cp.stdout.strip():
        p = Path(cp.stdout.strip())
        return p if p.is_absolute() else root / p
    cp = _run(["git", "rev-parse", "--git-common-dir"], root)
    if cp.returncode != 0:
        raise RuntimeError("cannot resolve --git-common-dir")
    common = Path(cp.stdout.strip())
    if not common.is_absolute():
        common = root / common
    return common / "hooks"


def _porcelain(root: Path) -> list[tuple[str, str]]:
    """[(xy, path)] from `git status --porcelain -z`.

    -z is not a nicety. Without it git applies core.quotepath: a path with a
    space, a non-ASCII byte, or a quote comes back C-quoted ("\\303\\251.md"),
    and naive line splitting mangles it -- so the file we name in the error is
    not the file on disk, and a rename ("R  a -> b") is parsed as one path.
    NUL-delimited output is unambiguous and quoting-free.
    """
    # --untracked-files=all, NOT the default `normal`. `normal` COLLAPSES a wholly
    # untracked directory to a single entry ("?? docs/"), so a new docs/orphan.md
    # is reported as "docs/" -- which never matches the docs/**/*.md rule, and the
    # developer is handed the "just gitignore it" remedy that provably does NOT
    # unblock doc_lint. The collapse silently defeats the path-aware remedy in
    # exactly the case the remedy exists for.
    cp = _run(["git", "status", "--porcelain", "-z", "--untracked-files=all"], root)
    if cp.returncode != 0:
        raise RuntimeError(f"git status failed: {cp.stderr.strip()}")

    rows: list[tuple[str, str]] = []
    fields = cp.stdout.split("\0")
    i = 0
    while i < len(fields):
        entry = fields[i]
        if not entry or len(entry) < 4:
            i += 1
            continue
        xy, path = entry[:2], entry[3:]
        # Rename/copy entries are followed by a second NUL-delimited field (the
        # ORIGINAL path). Consume it so it is never mistaken for a status entry.
        if xy and xy[0] in ("R", "C"):
            i += 1
        rows.append((xy, path))
        i += 1
    return rows


def _remedy_for(path: str) -> str:
    """Path-aware remedy. See THE DOCS CAVEAT in the module docstring."""
    if DOC_LINT_GLOB.match(path):
        return (
            "track it AND link it from AGENTS.md, or move/delete it out of docs/. "
            "Do NOT gitignore it: doc_lint walks docs/ with rglob and does not read "
            ".gitignore, so an ignored .md STILL trips DOC-LINT-020 and still blocks "
            "every commit."
        )
    return (
        f"track it (`git add {path}`) or ignore it (add to .gitignore) — a file that "
        "is neither is invisible to CI but red locally"
    )


def check_untracked(root: Path) -> list[Finding]:
    return [
        Finding("untracked", path, _remedy_for(path)) for xy, path in _porcelain(root) if xy == "??"
    ]


def check_dirty(root: Path) -> list[Finding]:
    return [
        Finding("dirty", f"{xy} {path}", "commit, stash, or discard it before branching")
        for xy, path in _porcelain(root)
        if xy != "??"
    ]


def check_doc_lint(root: Path) -> list[Finding]:
    script = root / "scripts" / "doc_lint.py"
    if not script.exists():
        return []
    cp = _run([sys.executable, str(script)], root)
    if cp.returncode == 0:
        return []
    blocks = [ln.strip() for ln in (cp.stdout + cp.stderr).splitlines() if "[BLOCK]" in ln]
    return [
        Finding("doc-lint", b, "fix the BLOCK — see the doc-lint rule cited in it") for b in blocks
    ] or [Finding("doc-lint", f"doc_lint exited {cp.returncode}", "run scripts/doc_lint.py")]


def _dirty_set(root: Path) -> set[str]:
    cp = _run(["git", "diff", "--name-only"], root)
    return {p for p in cp.stdout.splitlines() if p.strip()}


def check_generators(root: Path) -> list[Finding]:
    """Run the generators, assert THEY did not move the tree.

    Measures the DELTA across the run, not the absolute diff. Absolute-diff also
    lists files the developer had already edited by hand, so it accused the
    generators of rewriting a human's WIP. In a fresh CI clone the pre-run diff is
    empty and both definitions coincide -- which is exactly how a bug like that
    survives review and misfires only on a real person's machine.

    KNOWN LIMIT (asserted in _smoke_clean_state.sh so it cannot silently change):
    if a generated file is ALREADY dirty, the generator's change to it is masked.
    CI is authoritative precisely because its pre-run diff is empty.
    """
    out: list[Finding] = []
    before = _dirty_set(root)
    for name, cmd in GENERATORS:
        cp = _run(cmd, root)
        if cp.returncode != 0:
            out.append(
                Finding("generators", f"{name} failed rc={cp.returncode}", cp.stderr.strip()[:200])
            )
    for path in sorted(_dirty_set(root) - before):
        out.append(
            Finding(
                "generators",
                path,
                "a generator rewrote this — run it and commit the output "
                "(e.g. `bash scripts/sync_toc.sh` then commit CLAUDE.md)",
            )
        )
    return out


def _strip_comments(text: str) -> str:
    """Drop comment lines before grepping for a wiring string.

    check_hook_wired used to substring-match the raw file, so the PROSE in these
    very comments satisfied it: you could delete the entire hook and the gate
    would still report itself wired, because the word survived in a comment
    explaining the gate. A gate validated by its own documentation is not a gate.
    """
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def check_hook_wired(root: Path) -> list[Finding]:
    out: list[Finding] = []

    cfg_path = root / ".pre-commit-config.yaml"
    declared = False
    if cfg_path.exists():
        try:
            import yaml  # noqa: PLC0415

            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            for repo in cfg.get("repos", []) or []:
                for hook in repo.get("hooks", []) or []:
                    if hook.get("id") == "clean-state" and "clean_state.py" in str(
                        hook.get("entry", "")
                    ):
                        declared = True
        except ImportError:
            # No yaml on a bare runner: fall back to a comment-stripped grep.
            declared = "id: clean-state" in _strip_comments(cfg_path.read_text(encoding="utf-8"))
    if not declared:
        out.append(
            Finding(
                "hook-wired",
                ".pre-commit-config.yaml no longer declares a `clean-state` hook running clean_state.py",
                "restore the local hook (id: clean-state)",
            )
        )

    installer = root / "scripts" / "install_doc_lint_precommit.sh"
    if installer.exists():
        body = _strip_comments(installer.read_text(encoding="utf-8", errors="replace"))
        if "clean_state.py" not in body:
            out.append(
                Finding(
                    "hook-wired",
                    "install_doc_lint_precommit.sh no longer installs clean_state.py (comments don't count)",
                    "restore the clean-state block in the hook template",
                )
            )
    return out


def check_hook_installed(root: Path) -> list[Finding]:
    """Is the gate actually INSTALLED here — not merely declared in a config?

    Nothing in this repo ever installs hooks automatically, so a fresh clone or a
    brand-new worktree has NO gate at all while every config file cheerfully
    claims one. Declaration is not installation.
    """
    try:
        hook = hooks_dir(root) / "pre-commit"
    except RuntimeError as exc:
        return [Finding("hook-installed", str(exc), "could not resolve the hooks dir")]
    remedy = "run `bash scripts/install_doc_lint_precommit.sh` (idempotent; hooks are shared by all worktrees)"
    if not hook.exists():
        return [Finding("hook-installed", f"no pre-commit hook at {hook}", remedy)]
    if "clean_state.py" not in _strip_comments(hook.read_text(encoding="utf-8", errors="replace")):
        return [Finding("hook-installed", f"{hook} does not run clean_state.py", remedy)]
    return []


def check_junk_paths(root: Path, extra: list[str]) -> list[Finding]:
    """Refuse paths that must never enter the tree.

    Scans the working tree (untracked + staged) so this is enforced AT COMMIT
    TIME, not only in CI against a PR diff. Previously JUNK_PATTERNS only ran when
    --added-paths was passed, i.e. never at the one moment junk actually appears.
    """
    candidates = {p for _xy, p in _porcelain(root)} | set(extra)
    out: list[Finding] = []
    for p in sorted(candidates):
        for pat, why in JUNK_PATTERNS:
            if pat in p:
                out.append(Finding("junk-path", p, f"must never be tracked — {why}"))
    return out


MODES: dict[str, tuple[str, ...]] = {
    "precommit": ("untracked", "junk-paths"),
    "worktree": ("untracked", "dirty", "doc-lint", "hook-installed", "junk-paths"),
    "ci": ("generators", "hook-wired", "junk-paths"),
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="clean_state.py", description="enforce a clean agentdex-cli tree"
    )
    ap.add_argument("--mode", choices=sorted(MODES), required=True)
    ap.add_argument("--added-paths", nargs="*", default=[], help="ci: paths added by the PR")
    ns = ap.parse_args(argv)

    try:
        root = repo_root()
        runners = {
            "untracked": lambda: check_untracked(root),
            "dirty": lambda: check_dirty(root),
            "doc-lint": lambda: check_doc_lint(root),
            "generators": lambda: check_generators(root),
            "hook-wired": lambda: check_hook_wired(root),
            "hook-installed": lambda: check_hook_installed(root),
            "junk-paths": lambda: check_junk_paths(root, ns.added_paths),
        }
        findings: list[Finding] = []
        for check in MODES[ns.mode]:
            findings.extend(runners[check]())
    except (RuntimeError, OSError) as exc:
        print(f"[clean-state] error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if not findings:
        print(f"[clean-state] PASS mode={ns.mode}")
        return EXIT_CLEAN

    print(f"[clean-state] FAIL mode={ns.mode} — {len(findings)} finding(s)", file=sys.stderr)
    for f in findings:
        print(f"  [{f.check}] {f.detail}\n      -> {f.remedy}", file=sys.stderr)

    if os.environ.get(OVERRIDE_ENV) == "1":
        if ns.mode in OVERRIDABLE_MODES:
            print(
                f"\n[clean-state] OVERRIDDEN via {OVERRIDE_ENV}=1 — nothing above was fixed.\n"
                "[clean-state] Recorded in your shell history and this transcript.",
                file=sys.stderr,
            )
            return EXIT_CLEAN
        print(
            f"\n[clean-state] {OVERRIDE_ENV} is IGNORED in mode={ns.mode}. CI is the authoritative\n"
            "[clean-state] gate; an escape hatch that greens it is not an escape hatch, it is a hole.",
            file=sys.stderr,
        )

    print(
        f"\n[clean-state] Fix the above, or set {OVERRIDE_ENV}=1 (local modes only).\n"
        "[clean-state] Untracked files are the usual cause. A file is TRACKED or IGNORED;\n"
        "[clean-state] 'neither' hides it from CI while red-lining every local commit —\n"
        "[clean-state] which is how this repo taught itself to use --no-verify.",
        file=sys.stderr,
    )
    return EXIT_UNCLEAN


if __name__ == "__main__":
    sys.exit(main())
