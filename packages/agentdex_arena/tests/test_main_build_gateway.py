"""Smoke for build_gateway() boot posture (ADR-0011 11c review #3410920013).

build_gateway() must NOT hard-require the badge signing key — the previous
fail-closed boot took down enrollment / ladder / battle / replay routes
when ARENA_BADGE_SIGNING_KEY_HEX was missing. The fix degrades to
badge_authority=None, which makes /badge/mint return 503 'badge mint not
configured' while leaving every other route operational.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_HEX64_A = "a" * 64
_HEX64_B = Ed25519PrivateKey.generate().private_bytes_raw().hex()


def _scrub_env(monkeypatch) -> None:
    for var in (
        "ARENA_BADGE_SIGNING_KEY_HEX",
        "ARENA_SIGNING_KEY_HEX",
        "ARENA_ADMIN_TOKEN_HASH",
        "AI_BUILDER_TOKEN",
        "ARENA_RUNTIME_DIR",
        "ARENA_OWNER_INBOX_DIR",
        "ARENA_PG_DSN",
        "ARENA_PUBLIC_BASE_URL",
        "ARENA_OWNER_WEBHOOK",
        "ARENA_OWNER_WEBHOOK_TIMEOUT",
    ):
        monkeypatch.delenv(var, raising=False)


def test_build_gateway_degrades_when_badge_env_unset(monkeypatch, tmp_path: Path):
    """ARENA_BADGE_SIGNING_KEY_HEX unset → build_gateway succeeds + badge_auth=None.
    Other authorities still constructed and boot is otherwise unaffected."""
    _scrub_env(monkeypatch)
    monkeypatch.setenv("ARENA_ADMIN_TOKEN_HASH", "0" * 64)
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _HEX64_B)
    monkeypatch.setenv("ARENA_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ARENA_OWNER_INBOX_DIR", str(tmp_path / "inbox"))

    from agentdex_arena.__main__ import build_gateway

    gw = build_gateway()
    assert gw.badge_auth is None
    assert gw.admin is not None
    assert gw.authority is not None


def test_build_gateway_degrades_when_badge_env_malformed(monkeypatch, tmp_path: Path):
    """Malformed key (wrong length / not hex) follows the same degraded path."""
    _scrub_env(monkeypatch)
    monkeypatch.setenv("ARENA_ADMIN_TOKEN_HASH", "0" * 64)
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _HEX64_B)
    monkeypatch.setenv("ARENA_BADGE_SIGNING_KEY_HEX", "not-hex")
    monkeypatch.setenv("ARENA_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ARENA_OWNER_INBOX_DIR", str(tmp_path / "inbox"))

    from agentdex_arena.__main__ import build_gateway

    gw = build_gateway()
    assert gw.badge_auth is None


def test_build_gateway_wires_badge_when_env_valid(monkeypatch, tmp_path: Path):
    """Happy path: when the env is set + valid, badge_auth is a real
    BadgeAuthority — degraded mode does NOT silently kick in."""
    from agentdex_arena.badge_auth import BadgeAuthority

    _scrub_env(monkeypatch)
    monkeypatch.setenv("ARENA_ADMIN_TOKEN_HASH", "0" * 64)
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _HEX64_B)
    monkeypatch.setenv("ARENA_BADGE_SIGNING_KEY_HEX", _HEX64_A)
    monkeypatch.setenv("ARENA_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ARENA_OWNER_INBOX_DIR", str(tmp_path / "inbox"))

    from agentdex_arena.__main__ import build_gateway

    gw = build_gateway()
    assert isinstance(gw.badge_auth, BadgeAuthority)


def test_build_gateway_defaults_public_base_url_empty(monkeypatch, tmp_path: Path):
    """ARENA_PUBLIC_BASE_URL unset → build_gateway sets gw.public_base_url=''.

    The earlier prod-hostname default (PR #136) made every non-prod deploy
    mint README URLs pointing at the prod hostname even though the badge
    was signed by the local deploy's badge key. Empty-default keeps the
    field relative on non-prod deploys and forces prod ops to set the env
    explicitly (per docs/runbooks/badge-admin.md §"Setting the README-embed
    base URL"). Closes PR #136 review #3411158896.
    """
    _scrub_env(monkeypatch)
    monkeypatch.setenv("ARENA_ADMIN_TOKEN_HASH", "0" * 64)
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _HEX64_B)
    monkeypatch.setenv("ARENA_BADGE_SIGNING_KEY_HEX", _HEX64_A)
    monkeypatch.setenv("ARENA_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ARENA_OWNER_INBOX_DIR", str(tmp_path / "inbox"))

    from agentdex_arena.__main__ import build_gateway

    gw = build_gateway()
    assert gw.public_base_url == ""


def test_build_gateway_honors_public_base_url_env(monkeypatch, tmp_path: Path):
    """Explicit ARENA_PUBLIC_BASE_URL env → propagated verbatim to the
    gateway. Trailing-slash normalization is the gateway's job (locked by
    test_badge_mint_endpoint::test_badge_mint_trailing_slash_in_base_stripped),
    not build_gateway's."""
    _scrub_env(monkeypatch)
    monkeypatch.setenv("ARENA_ADMIN_TOKEN_HASH", "0" * 64)
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _HEX64_B)
    monkeypatch.setenv("ARENA_BADGE_SIGNING_KEY_HEX", _HEX64_A)
    monkeypatch.setenv("ARENA_PUBLIC_BASE_URL", "https://staging.example")
    monkeypatch.setenv("ARENA_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ARENA_OWNER_INBOX_DIR", str(tmp_path / "inbox"))

    from agentdex_arena.__main__ import build_gateway

    gw = build_gateway()
    assert gw.public_base_url == "https://staging.example"


def test_build_gateway_still_fails_closed_on_admin_env_missing(monkeypatch, tmp_path: Path):
    """The boot soft-fail is ONLY for BadgeAuthority. Other fail-closed
    authorities (AdminAuthority) still hard-stop boot — only the paid badge
    feature is allowed to come up unconfigured."""
    from agentdex_arena.admin_auth import AdminAuthError

    _scrub_env(monkeypatch)
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _HEX64_B)
    monkeypatch.setenv("ARENA_BADGE_SIGNING_KEY_HEX", _HEX64_A)
    monkeypatch.setenv("ARENA_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ARENA_OWNER_INBOX_DIR", str(tmp_path / "inbox"))
    # ARENA_ADMIN_TOKEN_HASH stays unset → AdminAuthority should raise.

    from agentdex_arena.__main__ import build_gateway

    with pytest.raises(AdminAuthError):
        build_gateway()


# ---------- owner confirmation-code delivery channel (ENROLL-P0-delivery-channel) ----------


def _min_env(monkeypatch, tmp_path: Path) -> None:
    """The minimal valid env for a build_gateway() boot (no badge needed)."""
    _scrub_env(monkeypatch)
    monkeypatch.setenv("ARENA_ADMIN_TOKEN_HASH", "0" * 64)
    monkeypatch.setenv("ARENA_SIGNING_KEY_HEX", _HEX64_B)
    monkeypatch.setenv("ARENA_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ARENA_OWNER_INBOX_DIR", str(tmp_path / "inbox"))


def test_build_gateway_selects_webhook_when_env_set(monkeypatch, tmp_path: Path):
    """ARENA_OWNER_WEBHOOK set → notify_owner is the webhook notifier (file inbox
    becomes the fallback), parsing ARENA_OWNER_WEBHOOK_TIMEOUT."""
    import agentdex_arena.__main__ as m

    _min_env(monkeypatch, tmp_path)
    monkeypatch.setenv("ARENA_OWNER_WEBHOOK", "https://hook.example/owner")
    monkeypatch.setenv("ARENA_OWNER_WEBHOOK_TIMEOUT", "2.5")

    captured: dict = {}

    def fake_webhook_notifier(url, *, fallback, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        captured["has_fallback"] = fallback is not None
        return lambda owner, code: None

    monkeypatch.setattr(m, "_webhook_notifier", fake_webhook_notifier)

    gw = m.build_gateway()
    assert gw.notify_owner is not None
    assert captured["url"] == "https://hook.example/owner"
    assert captured["timeout"] == 2.5
    assert captured["has_fallback"] is True  # file inbox is always the fallback


def test_build_gateway_uses_file_inbox_when_webhook_unset(monkeypatch, tmp_path: Path):
    """No ARENA_OWNER_WEBHOOK → notify_owner writes the code to the file inbox
    (the local/playtest path), preserving prior behavior."""
    import agentdex_arena.__main__ as m

    _min_env(monkeypatch, tmp_path)
    gw = m.build_gateway()

    gw.notify_owner("owner@example.com", "code-xyz")
    files = list((tmp_path / "inbox").glob("*.code"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8").strip() == "code-xyz"


def test_deliver_webhook_posts_payload(monkeypatch):
    """_deliver_webhook POSTs {owner, code} and returns True on 2xx; no fallback."""
    import agentdex_arena.__main__ as m

    sent: dict = {}

    class _FakeResp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

    class _FakeClient:
        def __init__(self, *a, **k) -> None:
            sent["timeout"] = k.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *a) -> bool:
            return False

        def post(self, url, json):
            sent["url"] = url
            sent["json"] = json
            return _FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "Client", _FakeClient)

    fallback_calls: list = []
    ok = m._deliver_webhook(
        "https://hook.example/owner",
        "owner@example.com",
        "the-code",
        timeout=3.0,
        fallback=lambda o, c: fallback_calls.append((o, c)),
    )
    assert ok is True
    assert sent["url"] == "https://hook.example/owner"
    assert sent["json"] == {"owner": "owner@example.com", "code": "the-code"}
    assert sent["timeout"] == 3.0
    assert fallback_calls == []  # success → fallback never fires


def test_deliver_webhook_falls_back_on_network_error(monkeypatch):
    """A POST that raises → _deliver_webhook returns False and invokes the fallback
    (a code is never dropped)."""
    import agentdex_arena.__main__ as m

    class _BoomClient:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a) -> bool:
            return False

        def post(self, url, json):
            raise RuntimeError("connection refused")

    import httpx

    monkeypatch.setattr(httpx, "Client", _BoomClient)

    fallback_calls: list = []
    ok = m._deliver_webhook(
        "https://hook.example/owner",
        "owner@example.com",
        "the-code",
        timeout=3.0,
        fallback=lambda o, c: fallback_calls.append((o, c)),
    )
    assert ok is False
    assert fallback_calls == [("owner@example.com", "the-code")]


def test_deliver_webhook_falls_back_on_non_2xx(monkeypatch):
    """A non-2xx response → raise_for_status raises → fallback fires, returns False."""
    import agentdex_arena.__main__ as m
    import httpx

    class _FakeResp:
        status_code = 500

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError("500", request=None, response=None)  # type: ignore[arg-type]

    class _FakeClient:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a) -> bool:
            return False

        def post(self, url, json):
            return _FakeResp()

    monkeypatch.setattr(httpx, "Client", _FakeClient)

    fallback_calls: list = []
    ok = m._deliver_webhook(
        "https://hook.example/owner",
        "owner@example.com",
        "the-code",
        timeout=3.0,
        fallback=lambda o, c: fallback_calls.append((o, c)),
    )
    assert ok is False
    assert fallback_calls == [("owner@example.com", "the-code")]


def test_webhook_notifier_delivers_off_thread(monkeypatch):
    """The notifier returned by _webhook_notifier fires delivery in a thread and
    returns immediately; the code is delivered (joined for determinism)."""
    import threading

    import agentdex_arena.__main__ as m

    delivered: list = []
    done = threading.Event()

    def fake_deliver(url, owner, code, *, timeout, fallback):
        delivered.append((url, owner, code, timeout))
        done.set()
        return True

    monkeypatch.setattr(m, "_deliver_webhook", fake_deliver)

    notify = m._webhook_notifier("https://hook.example/owner", fallback=None, timeout=4.0)
    notify("owner@example.com", "abc")
    assert done.wait(timeout=5), "webhook delivery thread did not run"
    assert delivered == [("https://hook.example/owner", "owner@example.com", "abc", 4.0)]


def test_webhook_notifier_backpressures_to_fallback_when_saturated(monkeypatch):
    """A saturated backlog must NOT spawn unbounded threads (256 MB Koyeb nano OOM
    risk). With the in-flight slot held by a blocked delivery, the next notify
    delivers via the file-inbox fallback inline instead of queueing. PR #231 review."""
    import threading

    import agentdex_arena.__main__ as m

    started = threading.Event()
    release = threading.Event()

    def blocking_deliver(url, owner, code, *, timeout, fallback):
        started.set()
        release.wait(timeout=5)  # hold the single in-flight slot
        return True

    monkeypatch.setattr(m, "_deliver_webhook", blocking_deliver)

    fallback_calls: list = []
    notify = m._webhook_notifier(
        "https://hook.example/owner",
        fallback=lambda o, c: fallback_calls.append((o, c)),
        timeout=1.0,
        max_workers=1,
        max_inflight=1,
    )

    notify("a@example.com", "code1")  # takes the only slot, blocks in delivery
    assert started.wait(timeout=5), "first delivery did not start"
    notify("b@example.com", "code2")  # saturated -> inline file-inbox fallback
    assert fallback_calls == [("b@example.com", "code2")]
    release.set()  # let the first delivery finish cleanly
