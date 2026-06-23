"""Integration tests for the GA-AUTH rate-limit + brute-force lockout WIRING.

These drive the real ``/auth/*`` routes through ``TestClient`` to prove the
TouchDrivenRateLimiter (unit-tested in test_limiter.py) is wired exactly where
intended: the volumetric guard fronts the flood surfaces, the verify path locks
an IP out after too many bad OTP codes, the whole thing is inert unless
``ARENA_RATE_LIMIT_ENABLED`` is set (and the inert path can't be crashed by a
garbage tuning knob), the client IP is keyed through ``X-Forwarded-For`` only
when proxies are trusted, and the 429s leak no lock-vs-rate distinction.
"""

from __future__ import annotations

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

_OWNER = "eddie@oppie.xyz"


def _gw(tmp_path):
    return ArenaGateway(
        authority=ConsentAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        session_authority=SessionAuthority(
            signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
        ),
    )


def _client(gw):
    return TestClient(create_app(gw, sidecar_factory=Sidecar), raise_server_exceptions=False)


def _enable(monkeypatch, **overrides):
    """Turn the limiter on and apply per-test env overrides before app build. Refill is
    left at its (small) default so a ms-scale test never refills a drained bucket."""
    monkeypatch.setenv("ARENA_RATE_LIMIT_ENABLED", "1")
    for k, v in overrides.items():
        monkeypatch.setenv(k, str(v))


def _has_retry_after(resp) -> bool:
    return "retry-after" in {k.lower() for k in resp.headers}


def _mask_ref(body):
    """Replace the random per-call correlation ref in an opaque error body so two
    responses can be compared for shape (the ref differs by design, not by cause)."""
    import re

    if isinstance(body, dict) and isinstance(body.get("detail"), str):
        return {**body, "detail": re.sub(r"ref: [0-9a-f]+", "ref: <REF>", body["detail"])}
    return body


# ---- volumetric guard on the flood surfaces ----


def test_volumetric_guard_429s_after_bucket_empty(tmp_path, monkeypatch):
    # device_flow is unconfigured → each allowed call 503s; once the per-IP bucket
    # drains, the guard 429s BEFORE the 503, proving it fronts the handler.
    _enable(monkeypatch, ARENA_AUTH_IP_MAX_TOKENS=2)
    client = _client(_gw(tmp_path))
    codes = [client.post("/auth/device/start").status_code for _ in range(3)]
    assert codes == [503, 503, 429]


def test_device_poll_is_rate_limited(tmp_path, monkeypatch):
    # F4 security floor: /auth/device/poll is unauthenticated and fans out to the GitHub
    # token URL, so it MUST sit behind the same per-IP volumetric guard as device/start.
    # device_flow is unconfigured → 503 while the bucket has tokens, then 429 once drained
    # (the pre-parse guard fronts the handler, so a malformed-code flood is capped).
    _enable(monkeypatch, ARENA_AUTH_IP_MAX_TOKENS=2)
    client = _client(_gw(tmp_path))
    codes = [
        client.post("/auth/device/poll", json={"device_code": "x"}).status_code for _ in range(3)
    ]
    assert codes == [503, 503, 429]


def test_disabled_by_default_never_rate_limits(tmp_path, monkeypatch):
    monkeypatch.delenv("ARENA_RATE_LIMIT_ENABLED", raising=False)
    client = _client(_gw(tmp_path))
    codes = {client.post("/auth/device/start").status_code for _ in range(10)}
    assert codes == {503}  # always reaches the handler; never 429


def test_inert_path_survives_a_garbage_tuning_knob(tmp_path, monkeypatch):
    # The default-off boot path must stay byte-identical: a malformed ARENA_TRUST_PROXIES
    # (or any ARENA_AUTH_* knob) staged WITHOUT the enable flag must NOT crash create_app
    # — the disabled branch parses no env beyond the enable flag.
    monkeypatch.delenv("ARENA_RATE_LIMIT_ENABLED", raising=False)
    monkeypatch.setenv("ARENA_TRUST_PROXIES", "   ")  # whitespace garbage
    monkeypatch.setenv("ARENA_AUTH_LIMIT_CAPACITY", "not-an-int")
    client = _client(_gw(tmp_path))  # must build, not raise
    assert client.post("/auth/device/start").status_code == 503  # inert, reaches handler


def test_garbage_knob_while_enabled_degrades_not_crashes(tmp_path, monkeypatch):
    # Even ENABLED, a mistyped knob must degrade to the floored default rather than crash
    # boot (capacity<1 would otherwise raise) or fail the control open.
    _enable(
        monkeypatch,
        ARENA_AUTH_LIMIT_CAPACITY="0",  # would fail-open / raise unfloored
        ARENA_AUTH_IP_MAX_TOKENS=2,
        ARENA_AUTH_IP_REFILL_PER_SEC="garbage",
    )
    client = _client(_gw(tmp_path))  # must build
    codes = [client.post("/auth/device/start").status_code for _ in range(3)]
    assert codes == [503, 503, 429]  # still enforced (floored capacity keeps it bounded)


def test_non_finite_token_knob_does_not_disable_control(tmp_path, monkeypatch):
    # float("inf")/"1e999"/"nan" parse WITHOUT raising and max(floor, inf) keeps inf, so
    # an un-guarded *_MAX_TOKENS=inf would make the bucket never empty — silently failing
    # the control OPEN while it looks enabled. _env_float must treat non-finite as garbage
    # and degrade to the floored default, so the volumetric guard STILL 429s.
    for bad in ("inf", "1e999", "nan"):
        with monkeypatch.context() as m:
            _enable(m, ARENA_AUTH_IP_MAX_TOKENS=bad, ARENA_AUTH_IP_REFILL_PER_SEC="1e-9")
            client = _client(_gw(tmp_path))
            # Default floored bucket is 30 tokens; with a ~0 refill it drains and 429s.
            codes = [client.post("/auth/device/start").status_code for _ in range(40)]
            assert 429 in codes, f"control failed OPEN for ARENA_AUTH_IP_MAX_TOKENS={bad!r}"


# ---- brute-force lockout on the OTP-verify surface ----


def test_verify_locks_out_after_too_many_bad_codes(tmp_path, monkeypatch):
    _enable(
        monkeypatch,
        ARENA_TRUST_PROXIES=1,  # lockout is gated on a trusted (per-client) IP key
        ARENA_AUTH_VERIFY_MAX_TOKENS=100,  # keep volumetric out of the way
        ARENA_AUTH_VERIFY_MAX_FAILURES=3,
        ARENA_AUTH_VERIFY_LOCKOUT_SEC=900,
    )
    client = _client(_gw(tmp_path))
    # send XFF so the key is a TRUSTED per-client slot (N=1) — the lockout only latches
    # on a trusted key, never on the shared proxy-peer fallback (see the fallback test).
    xff = {"X-Forwarded-For": "1.2.3.4"}
    codes = [
        client.post("/auth/email/verify", json={"code": "wrong"}, headers=xff).status_code
        for _ in range(4)
    ]
    # 3 bad guesses each 403; the 3rd trips the lockout so the 4th is an opaque 429.
    assert codes == [403, 403, 403, 429]


def test_verify_lockout_disabled_without_trusted_proxy(tmp_path, monkeypatch):
    # Security floor: with ARENA_TRUST_PROXIES unset (0) the IP key is the socket peer,
    # which behind a reverse proxy is the SHARED proxy IP — so the failure-lockout is
    # DISABLED (volumetric-only) to avoid an arena-wide login killswitch one attacker
    # trips with a handful of bad codes. Bad guesses keep 403-ing, never latch a 429.
    _enable(
        monkeypatch,
        ARENA_AUTH_VERIFY_MAX_TOKENS=100,  # volumetric out of the way
        ARENA_AUTH_VERIFY_MAX_FAILURES=3,  # would lock IF the leg were enabled
        ARENA_AUTH_VERIFY_LOCKOUT_SEC=900,
    )
    client = _client(_gw(tmp_path))
    codes = [
        client.post("/auth/email/verify", json={"code": "wrong"}).status_code for _ in range(6)
    ]
    assert codes == [403] * 6  # no lockout latch without a trusted proxy


def test_valid_login_still_succeeds_when_enabled(tmp_path, monkeypatch):
    _enable(
        monkeypatch,
        ARENA_AUTH_VERIFY_MAX_TOKENS=100,
        ARENA_AUTH_VERIFY_MAX_FAILURES=3,
        ARENA_AUTH_IP_MAX_TOKENS=100,
    )
    gw = _gw(tmp_path)
    gw.email_login_start(_OWNER)
    code = next(iter(gw.pending_email_logins))
    r = _client(gw).post("/auth/email/verify", json={"code": code})
    assert r.status_code == 200, r.text
    assert "session_token" in r.json()  # happy path unaffected by the limiter


# ---- anti-enumeration: lock-vs-rate 429 indistinguishability ----


def test_volumetric_429s_carry_no_retry_after_header(tmp_path, monkeypatch):
    # Two VOLUMETRIC 429s (verify-bucket-empty vs device-bucket-empty) must be
    # indistinguishable: same status, no Retry-After. (The lock-vs-volumetric case is
    # covered separately by test_lockout_429_indistinguishable_from_volumetric_429,
    # which needs a trusted proxy to actually trip a lockout.)
    _enable(
        monkeypatch,
        ARENA_AUTH_VERIFY_MAX_TOKENS=1,  # 2nd verify trips the VOLUMETRIC leg
        ARENA_AUTH_IP_MAX_TOKENS=1,
    )
    client = _client(_gw(tmp_path))
    client.post("/auth/email/verify", json={"code": "x"})  # 403, burns the 1 verify token
    volumetric = client.post("/auth/email/verify", json={"code": "x"})  # bucket empty → 429
    device_429 = None
    for _ in range(3):  # drain the device/start IP bucket to a 429
        device_429 = client.post("/auth/device/start")
    assert volumetric.status_code == 429
    assert device_429.status_code == 429
    assert not _has_retry_after(volumetric)
    assert not _has_retry_after(device_429)


def test_lockout_429_indistinguishable_from_volumetric_429(tmp_path, monkeypatch):
    # The anti-enumeration invariant the suite actually needs: a genuine LOCKOUT 429 and
    # a VOLUMETRIC 429 must be byte-indistinguishable to a guesser — same status, no
    # Retry-After, identical opaque body — so neither leaks which defense fired. Needs a
    # trusted proxy (lockout is gated on a per-client IP key) and ample verify tokens so
    # the LOCKOUT leg (not the volumetric leg) produces the verify 429.
    _enable(
        monkeypatch,
        ARENA_TRUST_PROXIES=1,
        ARENA_AUTH_VERIFY_MAX_TOKENS=100,  # keep the volumetric leg out of the way
        ARENA_AUTH_VERIFY_MAX_FAILURES=2,
        ARENA_AUTH_VERIFY_LOCKOUT_SEC=900,
        ARENA_AUTH_IP_MAX_TOKENS=1,  # device/start bucket drains to a volumetric 429
    )
    client = _client(_gw(tmp_path))
    # XFF → trusted per-client key so the lockout leg (not the fallback peer) latches.
    xff = {"X-Forwarded-For": "1.2.3.4"}
    client.post("/auth/email/verify", json={"code": "x"}, headers=xff)  # 403, failure #1
    client.post("/auth/email/verify", json={"code": "x"}, headers=xff)  # 403, #2 → trips lock
    lock_429 = client.post("/auth/email/verify", json={"code": "x"}, headers=xff)  # locked → 429
    device_429 = None
    for _ in range(3):  # drain the device/start IP bucket to a volumetric 429
        device_429 = client.post("/auth/device/start")
    assert lock_429.status_code == 429 and device_429.status_code == 429
    assert not _has_retry_after(lock_429) and not _has_retry_after(device_429)
    # Bodies carry a RANDOM per-call correlation ref (not a leak); masking it, the two
    # 429s must reduce to the identical opaque shape — neither reveals which defense fired.
    assert _mask_ref(lock_429.json()) == _mask_ref(device_429.json())


# ---- X-Forwarded-For keying under a trusted proxy ----


def test_xff_keys_per_client_when_proxy_trusted(tmp_path, monkeypatch):
    _enable(monkeypatch, ARENA_TRUST_PROXIES=1, ARENA_AUTH_IP_MAX_TOKENS=1)
    client = _client(_gw(tmp_path))
    first = client.post("/auth/device/start", headers={"X-Forwarded-For": "1.1.1.1"})
    repeat = client.post("/auth/device/start", headers={"X-Forwarded-For": "1.1.1.1"})
    other = client.post("/auth/device/start", headers={"X-Forwarded-For": "2.2.2.2"})
    assert first.status_code == 503  # bucket spent, handler reached
    assert repeat.status_code == 429  # same client IP → its bucket is empty
    assert other.status_code == 503  # distinct client IP → independent bucket


def test_xff_forged_left_of_chain_cannot_move_the_key(tmp_path, monkeypatch):
    # With N=1 the keyed slot is the RIGHTMOST hop (the one the trusted proxy appended).
    # An attacker who forges the LEFT of the chain cannot change the key: two requests
    # whose rightmost hop matches share a bucket regardless of the forged prefix.
    _enable(monkeypatch, ARENA_TRUST_PROXIES=1, ARENA_AUTH_IP_MAX_TOKENS=1)
    client = _client(_gw(tmp_path))
    a = client.post("/auth/device/start", headers={"X-Forwarded-For": "9.9.9.9, 2.2.2.2"})
    b = client.post("/auth/device/start", headers={"X-Forwarded-For": "8.8.8.8, 2.2.2.2"})
    assert a.status_code == 503  # keyed on the rightmost "2.2.2.2"
    assert b.status_code == 429  # forged prefix differs, key (2.2.2.2) is the same → empty


def test_xff_ignored_when_no_proxy_trusted(tmp_path, monkeypatch):
    # With ARENA_TRUST_PROXIES unset (0), a forged XFF cannot move the key off the socket
    # peer, so two different forged IPs share the one TestClient peer bucket.
    _enable(monkeypatch, ARENA_AUTH_IP_MAX_TOKENS=1)
    client = _client(_gw(tmp_path))
    first = client.post("/auth/device/start", headers={"X-Forwarded-For": "1.1.1.1"})
    forged = client.post("/auth/device/start", headers={"X-Forwarded-For": "9.9.9.9"})
    assert first.status_code == 503
    assert forged.status_code == 429  # forged XFF ignored → same bucket, now empty


def test_xff_duplicate_headers_combined_keys_on_proxy_hop(tmp_path, monkeypatch):
    # A trusted proxy may APPEND its hop as a SEPARATE X-Forwarded-For header rather than
    # rewriting the client's comma chain. With N=1 the key must come from the proxy-
    # appended (rightmost) hop, not the client's first header — so two requests with
    # DIFFERENT forged first headers but the SAME proxy hop share one bucket. A naive
    # headers.get() would read only the forged first header and let the key be rotated.
    _enable(monkeypatch, ARENA_TRUST_PROXIES=1, ARENA_AUTH_IP_MAX_TOKENS=1)
    client = _client(_gw(tmp_path))
    a = client.post(
        "/auth/device/start",
        headers=[("x-forwarded-for", "9.9.9.9"), ("x-forwarded-for", "2.2.2.2")],
    )
    b = client.post(
        "/auth/device/start",
        headers=[("x-forwarded-for", "8.8.8.8"), ("x-forwarded-for", "2.2.2.2")],
    )
    assert a.status_code == 503  # keyed on the rightmost (proxy-appended) hop 2.2.2.2
    assert b.status_code == 429  # different forged first header, same key → bucket empty


def test_verify_lockout_skipped_on_proxy_peer_fallback(tmp_path, monkeypatch):
    # ARENA_TRUST_PROXIES=1 ENABLES the lockout, but a request whose XFF chain is shorter
    # than N (here: no XFF at all) falls back to the SHARED socket peer. Latching a
    # lockout on that shared key would deny every client behind the proxy, so the lockout
    # is withheld on the fallback path — bad codes keep 403-ing without ever latching a
    # 429 (contrast test_verify_locks_out_after_too_many_bad_codes, which sends XFF).
    _enable(
        monkeypatch,
        ARENA_TRUST_PROXIES=1,
        ARENA_AUTH_VERIFY_MAX_TOKENS=100,  # keep the volumetric leg out of the way
        ARENA_AUTH_VERIFY_MAX_FAILURES=3,
        ARENA_AUTH_VERIFY_LOCKOUT_SEC=900,
    )
    client = _client(_gw(tmp_path))
    # no X-Forwarded-For → chain shorter than N=1 → fallback to peer → trusted is False
    codes = [
        client.post("/auth/email/verify", json={"code": "wrong"}).status_code for _ in range(6)
    ]
    assert codes == [403] * 6  # never latches a lockout 429 on the shared fallback peer


# ---- pre-parse throttling: invalid bodies can't bypass the limiter ----


def test_invalid_body_flood_throttled_pre_parse(tmp_path, monkeypatch):
    # FastAPI parses+validates the Pydantic body BEFORE the endpoint runs, so a pre-#1
    # in-endpoint guard never saw a malformed/schema-invalid flood (it 422s first), letting
    # an attacker burn parser/validation work uncapped. The _auth_preparse_throttle
    # middleware runs before routing/body-parsing, so BOTH invalid-body kinds still drain
    # the per-IP bucket: 2 invalid bodies spend the 2 tokens, the 3rd is an opaque 429.
    _enable(monkeypatch, ARENA_AUTH_IP_MAX_TOKENS=2)
    client = _client(_gw(tmp_path))
    schema_invalid = client.post("/auth/email/start", json={})  # missing 'email' → 422
    malformed = client.post(
        "/auth/email/start", content=b"not json", headers={"content-type": "application/json"}
    )  # unparseable JSON → 422 (after the pre-parse guard ran)
    throttled = client.post("/auth/email/start", json={})  # bucket drained pre-parse → 429
    assert throttled.status_code == 429, (
        schema_invalid.status_code,
        malformed.status_code,
        throttled.status_code,
    )
    assert not _has_retry_after(throttled)  # anti-enumeration preserved through the middleware


def test_verify_invalid_body_flood_throttled_pre_parse(tmp_path, monkeypatch):
    # Same bypass on the OTP-verify surface: an invalid-body flood must drain the verify
    # limiter pre-parse, not get free 422s. With a 2-token verify bucket the 3rd invalid
    # body is an opaque 429.
    _enable(monkeypatch, ARENA_TRUST_PROXIES=1, ARENA_AUTH_VERIFY_MAX_TOKENS=2)
    client = _client(_gw(tmp_path))
    xff = {"X-Forwarded-For": "1.2.3.4"}
    codes = [
        client.post("/auth/email/verify", json={}, headers=xff).status_code  # missing 'code'
        for _ in range(3)
    ]
    assert codes[-1] == 429, codes  # 2 invalid bodies spend the bucket, 3rd 429s pre-parse


def test_oauth_github_callback_is_volumetric_guarded(tmp_path, monkeypatch):
    # The browser-OAuth callback /oauth/github does an upstream GitHub token exchange,
    # gated only by a caller-controlled state==cookie check — so it must sit behind the
    # same per-IP volumetric guard as the other unauthenticated GitHub-token fanout
    # (/auth/device/poll). Without rate-limiting an attacker replays matching state+cookie
    # with arbitrary `code` to drive unbounded exchange_web_code calls. With a 2-token
    # bucket the 3rd hit is an opaque 429 (the pre-parse guard fires before the handler).
    _enable(monkeypatch, ARENA_AUTH_IP_MAX_TOKENS=2)
    client = _client(_gw(tmp_path))
    # device_flow unconfigured here → handler 503s; once the bucket drains the guard 429s
    # FIRST, proving /oauth/github is in _auth_preparse_guards.
    codes = [client.get("/oauth/github?code=x&state=y").status_code for _ in range(3)]
    assert codes[-1] == 429, codes
    # the redirect entrypoint is guarded too
    other = _client(_gw(tmp_path))
    eco = [other.get("/auth/github").status_code for _ in range(3)]
    assert eco[-1] == 429, eco
