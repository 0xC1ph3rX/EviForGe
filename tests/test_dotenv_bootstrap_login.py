from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from eviforge.api.main import create_app


def test_dotenv_bootstraps_admin_login(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    vault_dir = tmp_path / "vault"
    db_path = tmp_path / "eviforge.sqlite"

    dotenv = "\n".join(
        [
            f"EVIFORGE_DATA_DIR={data_dir.as_posix()}",
            f"EVIFORGE_VAULT_DIR={vault_dir.as_posix()}",
            f"EVIFORGE_DATABASE_URL=sqlite:///{db_path.as_posix()}",
            "EVIFORGE_REDIS_URL=redis://127.0.0.1:0/0",
            "EVIFORGE_LOGIN_RATE_LIMIT=0",
            "EVIFORGE_ADMIN_USERNAME=admin",
            "EVIFORGE_ADMIN_PASSWORD=admin",
        ]
    )
    (tmp_path / ".env").write_text(dotenv + "\n", encoding="utf-8")

    for key in [
        "EVIFORGE_DATA_DIR",
        "EVIFORGE_VAULT_DIR",
        "EVIFORGE_DATABASE_URL",
        "EVIFORGE_REDIS_URL",
        "EVIFORGE_LOGIN_RATE_LIMIT",
        "EVIFORGE_ADMIN_USERNAME",
        "EVIFORGE_ADMIN_PASSWORD",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)

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
