from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from eviforge.api.main import create_app
from eviforge.config import ACK_TEXT
from eviforge.core.auth import get_password_hash
from eviforge.core.db import create_session_factory
from eviforge.core.models import User


def _login(client: TestClient, username: str, password: str) -> None:
    r = client.post("/api/auth/ack", json={"text": ACK_TEXT, "actor": "pytest"})
    assert r.status_code == 200

    r = client.post(
        "/api/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200


def test_osint_tools_data_requires_auth(tmp_path: Path, monkeypatch) -> None:
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
        r = client.get("/web/osint/tools-data")
        assert r.status_code == 401


def test_osint_tools_data_available_for_non_admin(tmp_path: Path, monkeypatch) -> None:
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

    SessionLocal = create_session_factory(f"sqlite:///{db_path.as_posix()}")
    with SessionLocal() as session:
        session.add(
            User(
                username="analyst",
                hashed_password=get_password_hash("analyst-password-12345"),
                role="analyst",
                is_active=True,
            )
        )
        session.commit()

    app = create_app()
    with TestClient(app) as client:
        _login(client, "analyst", "analyst-password-12345")

        r = client.get("/web/osint/tools-data")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data.get("tools"), list)
        assert isinstance(data.get("analytics"), dict)
        assert data.get("role") == "analyst"

        tool_names = {t.get("name") for t in data["tools"]}
        assert "whois" in tool_names

        r = client.get("/web/admin/tools-data")
        assert r.status_code == 403
