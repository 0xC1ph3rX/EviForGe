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


def test_web_osint_page_and_actions_flow(tmp_path: Path, monkeypatch) -> None:
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

        r = client.get("/web/osint")
        assert r.status_code == 200
        assert "Case OSINT Action Tracker" in r.text

        r = client.post("/api/cases", json={"name": "OSINT web test"}, headers=headers)
        assert r.status_code == 200
        case_id = r.json()["id"]

        r = client.post(
            f"/api/cases/{case_id}/osint/actions",
            json={
                "provider": "facecheck",
                "action_type": "remove_my_photos",
                "target_label": "target-1",
                "notes": "draft note",
            },
            headers=headers,
        )
        assert r.status_code == 200
        action_id = r.json()["id"]

        r = client.patch(
            f"/api/cases/{case_id}/osint/actions/{action_id}",
            json={
                "status": "in_review",
                "target_label": "target-1-updated",
                "tracking_url": "https://example.test/ticket/1",
            },
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "in_review"
        assert r.json()["target_label"] == "target-1-updated"

        r = client.get(f"/api/cases/{case_id}/osint/actions", headers=headers)
        assert r.status_code == 200
        assert r.json()[0]["target_label"] == "target-1-updated"


def test_osint_endpoints_accept_cookie_auth(tmp_path: Path, monkeypatch) -> None:
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
        r = client.post("/api/cases", json={"name": "Cookie auth case"}, headers=headers)
        assert r.status_code == 200
        case_id = r.json()["id"]

        # No Authorization header; relies on auth cookie set during login.
        r = client.post(
            f"/api/cases/{case_id}/osint/actions",
            json={"provider": "custom", "action_type": "privacy_request", "target_label": "cookie-path"},
        )
        assert r.status_code == 200
        action_id = r.json()["id"]

        r = client.patch(
            f"/api/cases/{case_id}/osint/actions/{action_id}",
            json={"status": "submitted", "target_label": "cookie-updated"},
        )
        assert r.status_code == 200
        assert r.json()["target_label"] == "cookie-updated"
