from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from eviforge.api.main import create_app
from eviforge.config import ACK_TEXT


def _login(client: TestClient) -> dict[str, str]:
    r = client.post("/api/auth/ack", json={"text": ACK_TEXT, "actor": "pytest"})
    assert r.status_code == 200
    r = client.post(
        "/api/auth/token",
        data={"username": "admin", "password": "test-password-12345"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_and_case_controls_render(tmp_path: Path, monkeypatch) -> None:
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
    with TestClient(app) as client:
        headers = _login(client)

        r = client.get("/web")
        assert r.status_code == 200
        assert 'id="exportSnapshotBtn"' in r.text
        assert 'id="toggleHeroTerminalBtn"' in r.text
        assert 'id="closeHeroTerminalBtn"' in r.text

        r = client.post("/api/cases", json={"name": "UI controls case"}, headers=headers)
        assert r.status_code == 200
        case_id = r.json()["id"]

        r = client.get(f"/web/cases/{case_id}")
        assert r.status_code == 200
        assert 'id="runPipelineBtn"' in r.text

