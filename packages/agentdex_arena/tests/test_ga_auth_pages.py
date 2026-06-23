"""GA-AUTH page routes (ADX-Online Track A, steps 2-3): GET /signup + GET /login
serve the design/ga-selfserve self-serve screens, with the design assets reachable
under /ga-assets and the SPA landing on the right screen."""

from __future__ import annotations

from pathlib import Path

import pytest
from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

# packages/agentdex_arena/tests/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_HAS_DESIGN = (_REPO_ROOT / "design" / "ga-selfserve" / "index.html").is_file()


def _client(tmp_path: Path) -> TestClient:
    gw = ArenaGateway(
        authority=ConsentAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


@pytest.mark.skipif(not _HAS_DESIGN, reason="design/ga-selfserve not present in this tree")
@pytest.mark.parametrize("path,screen", [("/signup", "signup"), ("/login", "login")])
def test_page_route_serves_ga_screen(tmp_path, monkeypatch, path, screen):
    # routes resolve design/ relative to CWD (same as / serving web/index.html)
    monkeypatch.chdir(_REPO_ROOT)
    r = _client(tmp_path).get(path)
    assert r.status_code == 200, f"{path} -> {r.status_code}"
    body = r.text
    # <base> rewrite so the page's relative assets resolve to the static mount
    assert '<base href="/ga-assets/ga-selfserve/">' in body
    # lands on the requested screen (hash set before the SPA scripts run)
    assert f'location.hash="#{screen}"' in body
    # the GA self-serve SPA, not the landing/dashboard
    assert "FunnelApp" in body


@pytest.mark.skipif(not _HAS_DESIGN, reason="design/ga-selfserve not present in this tree")
def test_ga_assets_are_served(tmp_path, monkeypatch):
    monkeypatch.chdir(_REPO_ROOT)
    c = _client(tmp_path)
    # the page's own runtime files
    assert c.get("/ga-assets/ga-selfserve/index.html").status_code == 200
    assert c.get("/ga-assets/ga-selfserve/data.js").status_code == 200
    assert c.get("/ga-assets/ga-selfserve/shell.jsx").status_code == 200
    assert c.get("/ga-assets/ga-selfserve/screens.jsx").status_code == 200
    # design-system entry files + the tokens/*.css that styles.css @imports (the
    # allow-list MUST keep these or the page renders unstyled)
    assert c.get("/ga-assets/agentdex-design-system/styles.css").status_code == 200
    assert c.get("/ga-assets/agentdex-design-system/_ds_bundle.js").status_code == 200
    for tok in ("fonts", "colors", "typography", "spacing"):
        assert c.get(f"/ga-assets/agentdex-design-system/tokens/{tok}.css").status_code == 200


@pytest.mark.skipif(not _HAS_DESIGN, reason="design/ga-selfserve not present in this tree")
def test_ga_assets_allowlist_denies_everything_else(tmp_path, monkeypatch):
    # Default-deny allow-list (PR #461 review): the mount publishes ONLY the page's
    # assets, so every other file under the bundled design/ tree — planning docs,
    # component source, guidelines, manifests, design notes — must 404.
    monkeypatch.chdir(_REPO_ROOT)
    c = _client(tmp_path)
    denied = [
        "/ga-assets/agentdex-design-system/uploads/prd.html",  # internal planning doc
        "/ga-assets/agentdex-design-system/uploads/moodboard.html",
        "/ga-assets/agentdex-design-system/components/core/Button.jsx",  # component source
        "/ga-assets/agentdex-design-system/components/core/Button.prompt.md",
        "/ga-assets/agentdex-design-system/components/core/Button.d.ts",
        "/ga-assets/agentdex-design-system/guidelines/brand-themes.html",
        "/ga-assets/agentdex-design-system/README.md",
        "/ga-assets/agentdex-design-system/SKILL.md",
        "/ga-assets/agentdex-design-system/_ds_manifest.json",
        "/ga-assets/agentdex-design-system/_adherence.oxlintrc.json",
        "/ga-assets/ga-selfserve/DESIGN.md",  # the page dir's own design notes
    ]
    for p in denied:
        assert c.get(p).status_code == 404, f"{p} should be denied, not served"
