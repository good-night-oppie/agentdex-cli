#!/usr/bin/env python3
"""scripts/prepare_release.py

Bump the FIRST-PARTY workspace package versions, pin internal workspace
dependencies strictly, and generate release notes + social copy templates.

Design notes (why this is not the naive version):

* Independently-versioned vendored packages (``kaos`` git-subtree at 0.9.x,
  ``helios-client`` external lifecycle) are NEVER bumped and NEVER pinned to the
  release version — bumping them would ship a version/namespace regression to
  PyPI. See ``INDEPENDENT_PACKAGES`` and CLAUDE.md ("Why KAOS lives at
  packages/kaos/" / "Why helios stays external").
* TOML is rewritten by parsing with ``tomllib`` to learn the exact version key
  and the exact internal dependency spec strings, then doing targeted,
  quoted-literal replacement on the raw text. No string-blind bracket counting
  (a ``]`` inside an env-marker used to silently leave a later dep unpinned),
  and PEP 508 extras + environment markers are preserved when pinning.
* ``--version`` is validated against PEP 440 BEFORE any file is touched, and
  every manifest is rewritten in memory and validated before a single write —
  then written atomically (tmp + os.replace) so a mid-run error cannot leave the
  tree half-mutated.
* Release notes + social copy are written to ``release-assets/`` (NOT ``dist/``)
  so that ``uv build --clear`` (which wipes ``dist/``) cannot destroy the notes
  the GitHub release step consumes.
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

# Packages that carry their OWN version line and lifecycle — excluded from the
# release bump and from internal-dependency pinning.
INDEPENDENT_PACKAGES = {"kaos", "helios-client"}

# PEP 440 (pragmatic but strict): release segments, optional epoch, pre/post/dev
# segments, and an optional local version. Rejects the malformed values that
# would otherwise be written into every manifest before any check.
_PEP440 = re.compile(
    r"^\s*(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*"
    r"(?:(?:a|b|c|rc|alpha|beta|pre|preview)[._-]?[0-9]+)?"
    r"(?:(?:\.post|-post|\.r|-r)[._-]?[0-9]+)?"
    r"(?:(?:\.dev|-dev)[._-]?[0-9]+)?"
    r"(?:\+[a-z0-9]+(?:[._-][a-z0-9]+)*)?\s*$",
    re.IGNORECASE,
)


def validate_version(version: str) -> str:
    if not _PEP440.match(version or ""):
        print(
            f"ERROR: --version {version!r} is not a valid PEP 440 version "
            "(e.g. 0.2.0, 0.2.0rc1, 0.2.0.dev20260621).",
            file=sys.stderr,
        )
        sys.exit(2)
    return version.strip()


def run_git(args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def discover_workspace_packages(root_dir: Path):
    """Map every packages/* member's [project].name -> its pyproject.toml path."""
    packages = {}
    packages_dir = root_dir / "packages"
    if not packages_dir.is_dir():
        return packages
    for item in sorted(packages_dir.iterdir()):
        toml_path = item / "pyproject.toml"
        if item.is_dir() and toml_path.exists():
            try:
                with open(toml_path, "rb") as f:
                    name = tomllib.load(f).get("project", {}).get("name")
                if name:
                    packages[name] = toml_path
            except Exception as e:  # noqa: BLE001 - report and skip a bad manifest
                print(f"Warning: failed to parse {toml_path}: {e}", file=sys.stderr)
    return packages


def pin_spec(spec: str, version: str) -> str:
    """Pin an internal dependency spec to ``==version`` while preserving the
    package name, any extras, and any PEP 508 environment marker."""
    spec = spec.strip()
    marker = ""
    if ";" in spec:
        head, marker = spec.split(";", 1)
        marker = f"; {marker.strip()}"
    else:
        head = spec
    m = re.match(r"^([A-Za-z0-9._-]+)(\[[^\]]*\])?", head.strip())
    if not m:
        return spec
    name = m.group(1)
    extras = m.group(2) or ""
    return f"{name}{extras}=={version}{marker}"


def _dep_name(spec: str) -> str:
    m = re.match(r"^\s*([A-Za-z0-9._-]+)", spec)
    return m.group(1) if m else ""


def _internal_dep_specs(data: dict, owned: set) -> list:
    """Collect every dependency spec (main + optional) whose package is owned."""
    specs = set()
    project = data.get("project", {})
    for spec in project.get("dependencies", []) or []:
        if _dep_name(spec) in owned:
            specs.add(spec)
    for group in (project.get("optional-dependencies", {}) or {}).values():
        for spec in group or []:
            if _dep_name(spec) in owned:
                specs.add(spec)
    return sorted(specs)


def _replace_project_version(content: str, version: str) -> str:
    """Replace the version key only while inside the [project] table (so keys
    like ``version_scheme`` or a ``[tool.x] version`` are never clobbered)."""
    out = []
    in_project = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped[1:-1].strip() == "project"
        elif in_project and re.match(r"^\s*version\s*=", line):
            line = re.sub(r'^(\s*version\s*=\s*)"[^"]*"(.*)$', rf'\g<1>"{version}"\g<2>', line)
        out.append(line)
    return "\n".join(out) + ("\n" if content.endswith("\n") else "")


def rewrite_manifest(content: str, version: str, owned: set) -> str:
    """Bump [project].version and pin owned internal deps, via tomllib-learned
    targeted replacement (no bracket counting)."""
    data = tomllib.loads(content)
    new_content = _replace_project_version(content, version)
    for spec in _internal_dep_specs(data, owned):
        pinned = pin_spec(spec, version)
        if pinned != spec:
            new_content = new_content.replace(f'"{spec}"', f'"{pinned}"')
    return new_content


def generate_release_notes(version: str) -> str:
    """Group commits since the last reachable tag by Conventional Commit type.

    Honestly distinguishes "no tags in repository", "tags exist but none
    reachable from HEAD", and "no new commits since <tag>"."""
    tags_exist = bool(run_git(["tag", "--list"]))
    reachable_tag = None
    if tags_exist:
        try:
            reachable_tag = run_git(["describe", "--tags", "--abbrev=0", "HEAD"])
        except subprocess.CalledProcessError:
            reachable_tag = None

    if reachable_tag:
        commits = run_git(["log", f"{reachable_tag}..HEAD", "--oneline"]).splitlines()
        tag_info = (
            f"Commits since tag **{reachable_tag}**"
            if commits
            else f"No new commits since tag **{reachable_tag}**"
        )
    elif tags_exist:
        commits = run_git(["log", "-n", "50", "--oneline"]).splitlines()
        tag_info = "Last (up to) 50 commits — tags exist but none are reachable from HEAD"
    else:
        commits = run_git(["log", "-n", "50", "--oneline"]).splitlines()
        tag_info = "Last (up to) 50 commits — no tags in repository"

    categories = {
        "🚀 Features": [],
        "🐛 Bug Fixes": [],
        "📚 Documentation": [],
        "⚙️ Refactoring & Infrastructure": [],
    }
    for commit in commits:
        if not commit.strip():
            continue
        parts = commit.split(" ", 1)
        if len(parts) < 2:
            continue
        short_hash, msg = parts
        m = re.match(r"^([a-zA-Z0-9_-]+)(?:\([^)]+\))?!?\s*:\s*(.*)$", msg.strip())
        type_ = m.group(1).lower() if m else ""
        if type_ == "feat":
            categories["🚀 Features"].append((msg.strip(), short_hash))
        elif type_ == "fix":
            categories["🐛 Bug Fixes"].append((msg.strip(), short_hash))
        elif type_ == "docs":
            categories["📚 Documentation"].append((msg.strip(), short_hash))
        else:
            categories["⚙️ Refactoring & Infrastructure"].append((msg.strip(), short_hash))

    md = [
        f"# Release Notes - v{version}",
        "",
        f"Date: {datetime.date.today().isoformat()}  ",
        f"Context: {tag_info}",
        "",
        "## Changelog",
        "",
    ]
    has_content = False
    for cat_name, items in categories.items():
        if items:
            has_content = True
            md.append(f"### {cat_name}")
            md.append("")
            md.extend(f"- {msg_item} ({short_hash})" for msg_item, short_hash in items)
            md.append("")
    if not has_content:
        md.append("No changes recorded.")
        md.append("")
    return "\n".join(md)


def generate_social_copies(version: str, owned_count: int):
    """Social templates. Claims are bound to what the pipeline actually does:
    ``owned_count`` first-party packages are bumped (kaos/helios are excluded)."""
    x_copy = (
        "[Hook - Under 280 chars]\n"
        "Tired of vibe coding your agentic releases?\n\n"
        f"agentdex-cli v{version} is live. {owned_count} first-party packages bumped in "
        "lockstep, internal deps strictly pinned, release gates automated, OIDC publish. "
        "No-compromise CI.\n\n"
        "[Visual Recommendation]\n"
        "GIF of the GHA release run: ruff/mypy/pytest gates, twine check, OIDC publish green.\n\n"
        "[Post Copy]\n"
        "- Strictly pinned internal workspace deps (goodbye PyPI install drift).\n"
        f"- Lockstep version bump across {owned_count} first-party packages (kaos/helios "
        "keep their own version lines).\n"
        "- Deterministic gates: ruff, mypy, pytest, twine check.\n"
        "- Passwordless OIDC publish via GitHub Actions.\n\n"
        f"Release: https://github.com/good-night-oppie/agentdex-cli/releases/tag/v{version}\n"
    )
    linkedin_copy = (
        f"🚀 agentdex-cli v{version} is now live!\n\n"
        "Publishing multiple packages from a uv monorepo invites a class of bugs: internal "
        "version drift, release-notes lost to a build-dir clean, and a published wheel whose "
        "version exists in no commit. Here is how the release pipeline closes those holes:\n\n"
        "1. The Problem: monorepo consumers can end up with incompatible internal packages.\n"
        "2. The Mechanics:\n"
        f"   - Lockstep bump of the {owned_count} first-party workspace packages (the vendored\n"
        "     kaos subtree and helios-client keep their independent versions).\n"
        f"   - Strict ==-pinning of internal deps (e.g. agentdex-engine=={version}).\n"
        "   - Conventional-Commit release notes written outside dist/ so the build can't wipe them.\n"
        "   - Local --dry-run to keep debug commits out of history.\n"
        "3. The Lessons:\n"
        "   - Encode quality gates as code (ruff, mypy, pytest, twine check).\n"
        "   - Use passwordless OIDC token exchange for PyPI publishing.\n"
        "   - Make the gate assert the real invariant, not a convenient one.\n\n"
        f"Changelog: https://github.com/good-night-oppie/agentdex-cli/releases/tag/v{version}\n\n"
        "#SoftwareEngineering #Python #AgenticAI #CI #DevOps\n"
    )
    return x_copy, linkedin_copy


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def main():
    parser = argparse.ArgumentParser(
        description="Bump first-party versions, pin internal deps, generate release assets."
    )
    parser.add_argument("--version", required=True, help="Target release version (PEP 440)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print updates and generated files to stdout without modifying disk.",
    )
    args = parser.parse_args()
    version = validate_version(args.version)

    current_path = Path(__file__).resolve()
    root_dir = current_path.parent.parent if current_path.parent.name == "scripts" else Path.cwd()

    discovered = discover_workspace_packages(root_dir)
    owned_names = set(discovered) - INDEPENDENT_PACKAGES
    skipped = sorted(set(discovered) & INDEPENDENT_PACKAGES)

    # Root workspace manifest + every OWNED package manifest (kaos/helios excluded).
    toml_files = {}
    root_toml = root_dir / "pyproject.toml"
    if root_toml.exists():
        toml_files["agentdex-cli-workspace (root)"] = root_toml
    for name in sorted(owned_names):
        toml_files[name] = discovered[name]

    # Rewrite ALL manifests in memory and validate before writing ANY (fail-fast).
    updated = {}
    for name, toml_path in toml_files.items():
        try:
            content = toml_path.read_text(encoding="utf-8")
            new_content = rewrite_manifest(content, version, owned_names)
            tomllib.loads(new_content)  # the rewrite must still be valid TOML
            updated[toml_path] = (content, new_content)
        except Exception as e:  # noqa: BLE001 - abort the whole run on any failure
            print(f"Error: failed to rewrite {name} ({toml_path}): {e}", file=sys.stderr)
            sys.exit(1)

    release_notes = generate_release_notes(version)
    social_x, social_linkedin = generate_social_copies(version, len(owned_names))

    if args.dry_run:
        print("=== DRY RUN: no files will be modified ===")
        if skipped:
            print(f"Independently-versioned (NOT bumped): {', '.join(skipped)}")
        for path, (old, new) in updated.items():
            rel = path.relative_to(root_dir)
            if old == new:
                print(f"\n[{rel}] (no changes)")
                continue
            print(f"\n[{rel}]")
            for i, (ol, nl) in enumerate(zip(old.splitlines(), new.splitlines(), strict=False)):
                if ol != nl:
                    print(f"  L{i + 1}: - {ol}")
                    print(f"  L{i + 1}: + {nl}")
        print("\n--- release-assets/release_notes.md ---")
        print(release_notes)
        print("\n--- release-assets/social_x.txt ---")
        print(social_x)
        print("\n--- release-assets/social_linkedin.txt ---")
        print(social_linkedin)
        return

    for path, (_, new) in updated.items():
        _atomic_write(path, new)
        print(f"Bumped + pinned: {path.relative_to(root_dir)}")
    if skipped:
        print(f"Left at their own version (vendored/external): {', '.join(skipped)}")

    assets_dir = root_dir / "release-assets"
    assets_dir.mkdir(exist_ok=True)
    _atomic_write(assets_dir / "release_notes.md", release_notes)
    _atomic_write(assets_dir / "social_x.txt", social_x)
    _atomic_write(assets_dir / "social_linkedin.txt", social_linkedin)
    print(f"Wrote release assets to {assets_dir.relative_to(root_dir)}/")


if __name__ == "__main__":
    main()
