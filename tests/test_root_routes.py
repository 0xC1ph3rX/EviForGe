from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from eviforge.api.main import create_app


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


def test_root_redirects_to_web(client: TestClient) -> None:
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers.get("location") == "/web"


def test_favicon_does_not_404(client: TestClient) -> None:
    r = client.get("/favicon.ico")
    assert r.status_code == 204
