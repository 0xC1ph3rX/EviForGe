from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eviforge.api.main import create_app
from eviforge.config import ACK_TEXT


@pytest.fixture()
def configured_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data-not-created-yet"
    vault_dir = tmp_path / "vault-not-created-yet"
    db_path = data_dir / "nested" / "eviforge.sqlite"

    monkeypatch.setenv("EVIFORGE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("EVIFORGE_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("EVIFORGE_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("EVIFORGE_REDIS_URL", "redis://127.0.0.1:0/0")
    monkeypatch.setenv("EVIFORGE_LOGIN_RATE_LIMIT", "0")
    monkeypatch.setenv("EVIFORGE_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("EVIFORGE_ADMIN_PASSWORD", "test-password-12345")

    app = create_app()
    return app, data_dir, db_path


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


def test_startup_creates_sqlite_parent_dirs(configured_app) -> None:
    app, data_dir, db_path = configured_app
    assert not data_dir.exists()

    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.status_code == 200

    assert data_dir.exists()
    assert db_path.exists()


def test_import_files_endpoint_for_case_panel(configured_app, tmp_path: Path) -> None:
    app, _data_dir, _db_path = configured_app

    with TestClient(app) as c:
        headers = _auth_headers(c)

        # Prepare import directory used by the API fallback (cwd/import).
        import_dir = Path.cwd() / "import"
        import_dir.mkdir(parents=True, exist_ok=True)
        (import_dir / "alpha.bin").write_bytes(b"a")
        (import_dir / "beta.bin").write_bytes(b"bb")
        (import_dir / "subdir").mkdir(exist_ok=True)
        (import_dir / "subdir" / "nested.bin").write_bytes(b"nested")

        r = c.post("/api/cases", json={"name": "Import Files Case"}, headers=headers)
        assert r.status_code == 200
        case_id = r.json()["id"]

        r = c.get(f"/api/cases/{case_id}/import-files", headers=headers)
        assert r.status_code == 200
        data = r.json()
        names = [f["name"] for f in data["files"]]
        assert "alpha.bin" in names
        assert "beta.bin" in names
        # Endpoint intentionally lists top-level files only.
        assert "nested.bin" not in names
