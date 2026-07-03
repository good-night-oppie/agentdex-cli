"""GA-ENROLL Step-5 invariant: device-flow poll spam is rate-limited.

The device-flow poll endpoint is an unauthenticated OOB enrollment surface. It
must sit behind the same pre-parse per-IP volumetric guard as /auth/device/start
so malformed-code floods cannot fan out unboundedly to the GitHub token URL.
"""

from __future__ import annotations

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from agentdex_arena.session import SessionAuthority
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient


def _gateway(tmp_path):
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


def _client(gateway):
    return TestClient(create_app(gateway, sidecar_factory=Sidecar), raise_server_exceptions=False)


def test_device_flow_poll_rate_limited(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("ARENA_AUTH_IP_MAX_TOKENS", "2")
    client = _client(_gateway(tmp_path))

    codes = [
        client.post("/auth/device/poll", json={"device_code": "malformed"}).status_code
        for _ in range(3)
    ]

    assert codes == [503, 503, 429]


def test_device_flow_poll_never_rate_limited_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("ARENA_RATE_LIMIT_ENABLED", raising=False)
    client = _client(_gateway(tmp_path))

    codes = {
        client.post("/auth/device/poll", json={"device_code": f"malformed-{i}"}).status_code
        for i in range(8)
    }

    assert codes == {503}
