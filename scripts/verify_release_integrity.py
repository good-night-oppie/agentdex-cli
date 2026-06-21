#!/usr/bin/env python3
"""scripts/verify_release_integrity.py

Deterministic, non-LLM release gate. Asserts the LOAD-BEARING invariants, not
convenient proxies:

* FIRST-PARTY package versions are all == the target (kaos/helios-client are
  independently versioned and MUST NOT be bumped — asserted explicitly, the
  mirror of prepare_release.py's exclusion).
* Every internal first-party dependency is pinned ``name==target`` (the real
  anti-install-drift invariant; substring/length probes are not enough).
* The agent-facing SKILL.md references the target version (not merely ">100 bytes").
* Stable releases have a release blog post referencing the version, and the
  landing/docs pages interlink.

INDEPENDENT_PACKAGES MUST stay in sync with scripts/prepare_release.py.
"""

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# MUST match scripts/prepare_release.py — vendored/external, never release-bumped.
INDEPENDENT_PACKAGES = {"kaos", "helios-client"}


def _load(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _owned_manifests():
    """Yield (name, path, data) for the root + every first-party package."""
    out = []
    root = ROOT / "pyproject.toml"
    if root.exists():
        out.append(("agentdex-cli-workspace", root, _load(root)))
    for p in sorted((ROOT / "packages").glob("*/pyproject.toml")):
        data = _load(p)
        name = data.get("project", {}).get("name")
        if name and name not in INDEPENDENT_PACKAGES:
            out.append((name, p, data))
    return out


def _dep_name(spec: str) -> str:
    m = re.match(r"^\s*([A-Za-z0-9._-]+)", spec)
    return m.group(1) if m else ""


def check_versions(target_version: str) -> bool:
    ok = True
    owned_names = set()
    for name, path, data in _owned_manifests():
        owned_names.add(name)
        ver = data.get("project", {}).get("version")
        if not ver:
            print(f"ERROR: no [project].version in {path.relative_to(ROOT)}")
            ok = False
        elif ver != target_version:
            print(
                f"ERROR: version mismatch in {path.relative_to(ROOT)}: "
                f"expected {target_version}, found {ver}"
            )
            ok = False
    # Independently-versioned packages MUST NOT have been bumped to the target.
    for p in sorted((ROOT / "packages").glob("*/pyproject.toml")):
        data = _load(p)
        name = data.get("project", {}).get("name")
        if (
            name in INDEPENDENT_PACKAGES
            and data.get("project", {}).get("version") == target_version
        ):
            print(
                f"ERROR: independently-versioned {name} was bumped to the release "
                f"version {target_version} in {p.relative_to(ROOT)} — this would ship a "
                "version regression to PyPI. It must keep its own version."
            )
            ok = False
    if ok:
        print("✓ First-party versions synchronized; vendored packages untouched.")
    return ok


def check_internal_pins(target_version: str) -> bool:
    """Every first-party internal dependency must be pinned name==target."""
    owned_names = {name for name, _, _ in _owned_manifests()}
    ok = True
    for _name, path, data in _owned_manifests():
        project = data.get("project", {})
        specs = list(project.get("dependencies", []) or [])
        for group in (project.get("optional-dependencies", {}) or {}).values():
            specs.extend(group or [])
        for spec in specs:
            dn = _dep_name(spec)
            if dn in owned_names and f"=={target_version}" not in spec:
                print(
                    f"ERROR: internal dep '{spec}' in {path.relative_to(ROOT)} is not "
                    f"pinned to =={target_version} (install-drift risk)."
                )
                ok = False
    if ok:
        print("✓ All internal first-party dependencies pinned to the release version.")
    return ok


def check_skill_files(target_version: str) -> bool:
    skill_paths = [
        ROOT / "packages" / "agentdex_arena" / "src" / "agentdex_arena" / "SKILL.md",
        ROOT / "site" / "SKILL.md",
    ]
    ok = True
    for p in skill_paths:
        if not p.is_file():
            print(f"ERROR: skill file missing: {p.relative_to(ROOT)}")
            ok = False
            continue
        content = p.read_text(encoding="utf-8")
        if target_version not in content:
            print(
                f"ERROR: skill file {p.relative_to(ROOT)} does not reference "
                f"release version {target_version}."
            )
            ok = False
    if ok:
        print("✓ Skill files reference the release version.")
    return ok


def check_blog_presence(target_version: str, is_stable: bool) -> bool:
    if not is_stable:
        print("✓ Nightly release: skipping stable blog presence check.")
        return True
    blog_dir = ROOT / "blog"
    site_blog_dir = ROOT / "site" / "blog"
    md_posts = (
        list(blog_dir.glob("*.md")) + list(blog_dir.glob("zh/*.md")) if blog_dir.exists() else []
    )
    html_posts = list(site_blog_dir.glob("*.html")) if site_blog_dir.exists() else []
    found = any(
        target_version in p.name or target_version in p.read_text(encoding="utf-8", errors="ignore")
        for p in md_posts + html_posts
    )
    if not found:
        print(f"ERROR: no release blog post references version {target_version}.")
        return False
    print("✓ Stable release blog post verified.")
    return True


def check_link_lineage() -> bool:
    landing = ROOT / "web" / "index.html"
    docs_idx = ROOT / "site" / "docs" / "index.html"
    if not landing.is_file() or not docs_idx.is_file():
        print("ERROR: landing page or docs index HTML missing.")
        return False
    landing_content = landing.read_text(encoding="utf-8")
    docs_content = docs_idx.read_text(encoding="utf-8")
    if 'href="/skill.md"' not in landing_content and 'href="/bene/SKILL.md"' not in landing_content:
        print("ERROR: landing page missing link to agent skill.")
        return False
    if "/bene/" not in landing_content and "docs/" not in landing_content:
        print("ERROR: landing page missing link to documentation.")
        return False
    if 'href="../index.html"' not in docs_content and 'href="index.html"' not in docs_content:
        print("ERROR: docs index missing navigation links.")
        return False
    print("✓ Website link lineage verified.")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="Target version to verify")
    parser.add_argument("--stable", action="store_true", help="Assert stable release criteria")
    args = parser.parse_args()

    print(f"Verifying release integrity for v{args.version} (stable={args.stable})...")
    checks = [
        check_versions(args.version),
        check_internal_pins(args.version),
        check_skill_files(args.version),
        check_blog_presence(args.version, args.stable),
        check_link_lineage(),
    ]
    if not all(checks):
        print("❌ Release integrity verification FAILED!")
        sys.exit(1)
    print("✨ Release integrity verification PASSED!")
    sys.exit(0)


if __name__ == "__main__":
    main()
