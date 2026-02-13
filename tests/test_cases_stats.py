from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eviforge.api.main import create_app
from eviforge.config import ACK_TEXT


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data_dir = tmp_path / "data"
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "eviforge.sqlite"

    monkeypatch.setenv("EVIFORGE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("EVIFORGE_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("EVIFORGE_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("EVIFORGE_REDIS_URL", "redis://127.0.0.1:0/0")
    monkeypatch.setenv("EVIFORGE_LOGIN_RATE_LIMIT", "0")
    monkeypatch.setenv("EVIFORGE_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("EVIFORGE_ADMIN_PASSWORD", "test-password-12345")

    app = create_app()
    with TestClient(app) as c:
        yield c


def _auth_headers(c: TestClient) -> dict[str, str]:
    r = c.post("/api/auth/ack", json={"text": ACK_TEXT, "actor": "pytest"})
    assert r.status_code == 200
    r = c.post(
        "/api/auth/token",
        data={"username": "admin", "password": "test-password-12345"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_overview_stats_tracks_cases_and_evidence(client: TestClient) -> None:
    headers = _auth_headers(client)

    r = client.get("/api/cases/stats/overview", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"cases": 0, "evidence": 0, "jobs_running": 0}

    r = client.post("/api/cases", json={"name": "Case 1"}, headers=headers)
    assert r.status_code == 200
    case_id = r.json()["id"]

    r = client.post(
        f"/api/cases/{case_id}/evidence/upload",
        headers=headers,
        files={"file": ("sample.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 200

    r = client.get("/api/cases/stats/overview", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["cases"] == 1
    assert data["evidence"] == 1
    assert data["jobs_running"] == 0
