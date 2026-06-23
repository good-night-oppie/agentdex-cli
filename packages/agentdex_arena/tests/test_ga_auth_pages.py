"""GA-AUTH page routes (ADX-Online Track A, steps 2-3): GET /signup, /login, /enroll
serve the CSP-safe GA self-serve SPA built into web/ga/ (tools/ga_spa/build.mjs), with
the bundle reachable read-only under /ga.

The hard floor these pin: the served shell is reachable (200 text/html), carries NO
password field (passwordless per ADR-0013), names the passwordless auth surface, and
loads ONLY same-origin, no-eval, no-CDN, no-inline-JS assets so it renders under a
strict `script-src 'self'` CSP (the production box CSP) — the failure mode the previous
in-browser-Babel prototype hit (200 but blank)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

# packages/agentdex_arena/tests/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_GA_DIR = _REPO_ROOT / "web" / "ga"
_HAS_GA = (_GA_DIR / "index.html").is_file()

# A silently-skipped security-invariant test is a false-green: it lets the
# passwordless / CSP-safe floor regress while CI stays green. The
# ga-auth-invariants CI gate sets ADX_REQUIRE_GA_BUNDLE=1 so a missing/broken
# web/ga bundle FAILS LOUD here instead of waving the invariants through.
_REQUIRE_GA = os.environ.get("ADX_REQUIRE_GA_BUNDLE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
# When required, do NOT skip on a missing bundle — let the tests run and fail
# (loud red) so the gap is visible at the merge boundary.
_needs_ga = pytest.mark.skipif(
    not _HAS_GA and not _REQUIRE_GA,
    reason="web/ga bundle not present in this tree",
)


def test_ga_bundle_present_when_required():
    """Fail loud (not skip) when the invariant gate demands the GA bundle.

    Locks the false-green hole: under ADX_REQUIRE_GA_BUNDLE=1 (set by the
    ga-auth-invariants CI job) the passwordless/CSP invariant suite must
    actually execute, so a missing web/ga bundle has to surface as a failure
    here rather than a silent skip."""
    if not _REQUIRE_GA:
        pytest.skip("ADX_REQUIRE_GA_BUNDLE not set (local-dev tolerance)")
    assert _HAS_GA, (
        f"web/ga/index.html absent at {_GA_DIR} — build the GA SPA bundle "
        "(node tools/ga_spa/build.mjs) before running the GA-AUTH invariant gate"
    )


def _client(tmp_path: Path) -> TestClient:
    gw = ArenaGateway(
        authority=ConsentAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )
    # create_app resolves web/ga relative to CWD (same as / serving web/index.html)
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


@_needs_ga
@pytest.mark.parametrize(
    "path", ["/signup", "/login", "/enroll", "/modes", "/arena", "/battle/new"]
)
def test_entry_route_serves_spa_shell(tmp_path, monkeypatch, path):
    monkeypatch.chdir(_REPO_ROOT)
    r = _client(tmp_path).get(path)
    assert r.status_code == 200, f"{path} -> {r.status_code}"
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert '<div id="root">' in body  # SPA mount point
    assert "/ga/app/boot.js" in body  # the funnel bootstraps from the built bundle
    assert "/ga/app/screens.js" in body


@_needs_ga
@pytest.mark.parametrize(
    "path", ["/signup", "/login", "/enroll", "/modes", "/arena", "/battle/new"]
)
def test_served_shell_is_passwordless_and_csp_safe(tmp_path, monkeypatch, path):
    # The security floor a step scores 0 without: no password field, and a shell that
    # renders under a strict script-src 'self' CSP (no inline <script>, no CDN origin).
    monkeypatch.chdir(_REPO_ROOT)
    body = _client(tmp_path).get(path).text
    low = body.lower()
    assert 'type="password"' not in low and "type='password'" not in low
    # passwordless auth surface is named in the served DOM (greppable auth hooks)
    assert "passwordless" in low
    assert "github" in low and "magic link" in low
    # CSP-hostile patterns that broke the prototype must be gone
    assert "unpkg.com" not in low and "babel" not in low
    assert "text/babel" not in low
    # every <script> is an external same-origin src — no inline script body
    import re

    for tag in re.findall(r"<script\b[^>]*>(.*?)</script>", body, flags=re.S | re.I):
        assert tag.strip() == "", "inline <script> body breaks a strict script-src CSP"
    for m in re.findall(r"<script\b[^>]*\bsrc=\"([^\"]+)\"", body, flags=re.I):
        assert m.startswith("/ga/"), f"non-same-origin script src: {m}"


@_needs_ga
def test_bundle_assets_are_served(tmp_path, monkeypatch):
    monkeypatch.chdir(_REPO_ROOT)
    c = _client(tmp_path)
    for asset in (
        "/ga/index.html",
        "/ga/page.css",
        "/ga/styles.css",
        "/ga/tokens/fonts.css",
        "/ga/tokens/colors.css",
        "/ga/app/boot.js",
        "/ga/app/shell.js",
        "/ga/app/screens.js",
        "/ga/app/data.js",
        "/ga/app/ds-bundle.js",
        "/ga/app/react.production.min.js",
        "/ga/app/react-dom.production.min.js",
    ):
        assert c.get(asset).status_code == 200, f"{asset} not served"


@_needs_ga
def test_arena_aliases_boot_to_modes_screen(tmp_path, monkeypatch):
    monkeypatch.chdir(_REPO_ROOT)
    boot = _client(tmp_path).get("/ga/app/boot.js").text
    assert 'path === "/arena"' in boot
    assert 'path === "/battle/new"' in boot
    assert '"modes"' in boot


@_needs_ga
def test_compiled_screens_are_csp_safe(tmp_path, monkeypatch):
    # The compiled funnel must be plain JS the browser runs directly: it exposes
    # FunnelApp via React.createElement (no raw JSX left) and contains no eval/Function
    # so a strict CSP can run it without unsafe-eval.
    monkeypatch.chdir(_REPO_ROOT)
    c = _client(tmp_path)
    screens = c.get("/ga/app/screens.js").text
    assert "FunnelApp" in screens
    assert "createElement" in screens
    assert "</" not in screens, "raw JSX remains in the compiled bundle"
    for js in ("/ga/app/screens.js", "/ga/app/shell.js", "/ga/app/boot.js"):
        src = c.get(js).text
        assert "eval(" not in src and "new Function(" not in src, f"eval in {js}"


@_needs_ga
def test_no_password_in_compiled_funnel(tmp_path, monkeypatch):
    # The passwordless floor lives in JS-rendered components, not the static shell, so
    # scan the COMPILED funnel for a password input type (the form a `type="password"`
    # JSX prop takes after build): `type: "password"`.
    monkeypatch.chdir(_REPO_ROOT)
    c = _client(tmp_path)
    for js in ("/ga/app/shell.js", "/ga/app/screens.js"):
        resp = c.get(js)
        # Assert the asset is actually served BEFORE scanning: a 404 body
        # trivially satisfies the negative assertion (vacuous pass), which would
        # false-green the passwordless invariant if the bundle were ever absent.
        assert resp.status_code == 200, f"{js} not served"
        src = resp.text.lower()
        assert 'type: "password"' not in src and "type:'password'" not in src, js


@_needs_ga
def test_funnel_wires_the_auth_backends(tmp_path, monkeypatch):
    # F1 anti-dead-stub floor: the served funnel must actually CALL the /auth/* backends,
    # not just navigate locally (the buttons were `onClick={()=>go('github')}` with zero
    # network — a funnel that serves 200 but can never sign anyone in). Pins that the
    # compiled bundle issues same-origin fetches to all four endpoints, with ?web=1 on
    # the session-establishing verify/poll so the token lands in the HttpOnly cookie.
    monkeypatch.chdir(_REPO_ROOT)
    screens = _client(tmp_path).get("/ga/app/screens.js").text
    assert "fetch(" in screens, "funnel issues no network call (dead-stub regression)"
    for endpoint in (
        "/auth/github",
        "/auth/email/start",
        "/auth/email/verify?web=1",
        "/auth/device/start",
        "/auth/device/poll?web=1",
    ):
        assert endpoint in screens, f"funnel does not wire {endpoint}"
    assert "location.assign" in screens, "browser GitHub OAuth CTA must redirect"


@_needs_ga
def test_css_surface_is_same_origin(tmp_path, monkeypatch):
    # No third-party origin anywhere in the served CSS: the Google Fonts @import is
    # stripped at build time so the auth funnel never beacons to fonts.googleapis.com /
    # gstatic.com (privacy on the passwordless sign-in surface) and the bundle stays
    # truly same-origin under a strict CSP. Fonts fall back to the token stacks.
    monkeypatch.chdir(_REPO_ROOT)
    c = _client(tmp_path)
    for css in ("/ga/styles.css", "/ga/tokens/fonts.css", "/ga/page.css"):
        resp = c.get(css)
        # Served-before-scan: a 404 body trivially passes the negative
        # same-origin assertion (vacuous pass) — guard so the invariant
        # cannot false-green on a missing bundle.
        assert resp.status_code == 200, f"{css} not served"
        body = resp.text.lower()
        assert "http://" not in body and "https://" not in body, f"third-party origin in {css}"
        assert "googleapis" not in body and "gstatic" not in body, css
