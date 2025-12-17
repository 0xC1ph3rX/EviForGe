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
    # Satisfy the authorization gate.
    r = c.post("/api/auth/ack", json={"text": ACK_TEXT, "actor": "pytest"})
    assert r.status_code == 200

    # Login using the bootstrapped admin user.
    r = c.post(
        "/api/auth/token",
        data={"username": "admin", "password": "test-password-12345"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_case(c: TestClient, headers: dict[str, str]) -> str:
    r = c.post("/api/cases", json={"name": "Test Case"}, headers=headers)
    assert r.status_code == 200
    return r.json()["id"]


def test_artifacts_tree_and_preview_are_safe(client: TestClient) -> None:
    headers = _auth_headers(client)
    case_id = _create_case(client, headers)

    # Create an artifact file under the case vault.
    from eviforge.config import load_settings

    settings = load_settings()
    artifacts_root = settings.vault_dir / case_id / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    (artifacts_root / "hello.txt").write_text("hello\n", encoding="utf-8")

    r = client.get(f"/api/cases/{case_id}/artifacts/tree", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert any(item["path"] == "hello.txt" and item["type"] == "file" for item in data["items"])

    r = client.get(f"/api/cases/{case_id}/artifacts/file", params={"path": "hello.txt"}, headers=headers)
    assert r.status_code == 200
    preview = r.json()
    assert preview["kind"] == "text"
    assert "hello" in preview.get("text", "")

    # Path traversal is rejected.
    r = client.get(f"/api/cases/{case_id}/artifacts/file", params={"path": "../case.json"}, headers=headers)
    assert r.status_code == 400


def test_evidence_upload_and_download_roundtrip(client: TestClient) -> None:
    headers = _auth_headers(client)
    case_id = _create_case(client, headers)

    r = client.post(
        f"/api/cases/{case_id}/evidence/upload",
        headers=headers,
        files={"file": ("sample.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 200
    evidence_id = r.json()["id"]

    r = client.get(f"/api/cases/{case_id}/evidence", headers=headers)
    assert r.status_code == 200
    assert any(ev["id"] == evidence_id for ev in r.json())

    r = client.get(f"/api/cases/{case_id}/evidence/{evidence_id}/download", headers=headers)
    assert r.status_code == 200
    assert r.content == b"hello"

