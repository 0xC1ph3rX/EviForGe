from __future__ import annotations

import time
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
    monkeypatch.setenv("EVIFORGE_JOB_EXECUTION", "inline")
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


def test_job_runs_inline_without_redis(client: TestClient) -> None:
    headers = _auth_headers(client)

    r = client.post("/api/cases", json={"name": "Inline Job Case"}, headers=headers)
    assert r.status_code == 200
    case_id = r.json()["id"]

    r = client.post(
        f"/api/cases/{case_id}/evidence/upload",
        headers=headers,
        files={"file": ("sample.bin", b"abc123", "application/octet-stream")},
    )
    assert r.status_code == 200
    evidence_id = r.json()["id"]

    r = client.post(
        f"/api/cases/{case_id}/jobs",
        headers=headers,
        json={"module": "verify", "evidence_id": evidence_id, "params": {}},
    )
    assert r.status_code == 200
    job_id = r.json()["id"]

    status = None
    for _ in range(40):
        r = client.get(f"/api/jobs/{job_id}", headers=headers)
        assert r.status_code == 200
        status = r.json()["status"]
        if status in {"COMPLETED", "FAILED"}:
            break
        time.sleep(0.1)

    assert status == "COMPLETED"
    assert r.json()["output_files"]
