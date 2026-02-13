from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from eviforge.api.main import create_app
from eviforge.core.auth import get_password_hash
from eviforge.core.db import create_session_factory
from eviforge.core.models import User


def test_env_admin_is_upgraded_and_usable(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "eviforge.sqlite"

    monkeypatch.setenv("EVIFORGE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("EVIFORGE_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("EVIFORGE_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("EVIFORGE_REDIS_URL", "redis://127.0.0.1:0/0")
    monkeypatch.setenv("EVIFORGE_LOGIN_RATE_LIMIT", "0")
    monkeypatch.setenv("EVIFORGE_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("EVIFORGE_ADMIN_PASSWORD", "admin")
    monkeypatch.setenv("EVIFORGE_ENFORCE_ENV_ADMIN", "1")

    session_factory = create_session_factory(f"sqlite:///{db_path.as_posix()}")
    with session_factory() as session:
        session.add(
            User(
                username="admin",
                hashed_password=get_password_hash("old-password-12345"),
                role="analyst",
                is_active=True,
            )
        )
        session.commit()

    app = create_app()
    with TestClient(app) as client:
        r = client.post(
            "/api/auth/token",
            data={"username": "admin", "password": "admin"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200

        r = client.get("/web/admin")
        assert r.status_code == 200
        assert "System Administration" in r.text
