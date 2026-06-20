"""Static dashboard mount for the agentdex.builders GA SPA."""

from __future__ import annotations

from pathlib import Path

from adx_showdown.sidecar import Sidecar
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway, create_app
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient


def _gateway(tmp_path: Path) -> ArenaGateway:
    authority = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    return ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )


def test_dashboard_mount_serves_bundled_spa(monkeypatch, tmp_path: Path):
    dashboard = tmp_path / "web" / "dashboard"
    dashboard.mkdir(parents=True)
    (dashboard / "index.html").write_text("<h1>agentdex dashboard</h1>\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    app = create_app(_gateway(tmp_path), sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        redirect = client.get("/dashboard", follow_redirects=False)
        assert redirect.status_code == 308
        assert redirect.headers["location"] == "/dashboard/"

        response = client.get("/dashboard/")
        assert response.status_code == 200
        assert "agentdex dashboard" in response.text


def test_dashboard_mount_absent_without_bundled_spa(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)

    app = create_app(_gateway(tmp_path), sidecar_factory=Sidecar)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/dashboard").status_code == 404
        assert client.get("/dashboard/").status_code == 404
