from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from eviforge.api.main import create_app


def _isolated_env(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "eviforge.sqlite"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVIFORGE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("EVIFORGE_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("EVIFORGE_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("EVIFORGE_REDIS_URL", "redis://127.0.0.1:0/0")
    monkeypatch.setenv("EVIFORGE_LOGIN_RATE_LIMIT", "0")
    monkeypatch.delenv("EVIFORGE_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("EVIFORGE_SECRET_KEY", raising=False)
    monkeypatch.delenv("EVIFORGE_SETUP_ENABLED", raising=False)
    monkeypatch.delenv("EVIFORGE_SETUP_TOKEN", raising=False)


def test_secure_setup_token_bootstrap_flow(tmp_path: Path, monkeypatch) -> None:
    _isolated_env(tmp_path, monkeypatch)
    monkeypatch.setenv("EVIFORGE_SECRET_KEY", "test-secret-key-1234567890")
    monkeypatch.setenv("EVIFORGE_SETUP_TOKEN", "test-setup-token-1234567890")

    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/auth/bootstrap/status")
        assert r.status_code == 200
        data = r.json()
        assert data["setup_required"] is True
        assert data["remote_bootstrap_enabled"] is True
        assert data["setup_token_required"] is True

        r = client.post(
            "/api/auth/bootstrap",
            json={"username": "owner", "password": "very-long-password"},
        )
        assert r.status_code == 403
        assert r.json()["detail"]["error"] == "invalid_setup_token"

        r = client.post(
            "/api/auth/bootstrap",
            json={
                "username": "owner",
                "password": "very-long-password",
                "setup_token": "test-setup-token-1234567890",
            },
        )
        assert r.status_code == 200
        assert r.json()["username"] == "owner"

        r = client.post(
            "/api/auth/token",
            data={"username": "owner", "password": "very-long-password"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200

        r = client.get("/web", follow_redirects=False)
        assert r.status_code == 200


def test_dev_setup_enabled_bootstrap_still_works(tmp_path: Path, monkeypatch) -> None:
    _isolated_env(tmp_path, monkeypatch)
    monkeypatch.setenv("EVIFORGE_SETUP_ENABLED", "1")

    app = create_app()
    with TestClient(app) as client:
        r = client.post(
            "/api/auth/bootstrap",
            json={"username": "owner", "password": "very-long-password"},
        )
        assert r.status_code == 200
        assert r.json()["role"] == "admin"
