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


def _login(c: TestClient) -> None:
    r = c.post("/api/auth/ack", json={"text": ACK_TEXT, "actor": "pytest"})
    assert r.status_code == 200

    r = c.post(
        "/api/auth/token",
        data={"username": "admin", "password": "test-password-12345"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200


def test_web_admin_page_renders(client: TestClient) -> None:
    _login(client)
    r = client.get("/web/admin")
    assert r.status_code == 200
    assert "System Administration" in r.text
    assert "System Audit Log" in r.text
    assert "Forensic Modules" in r.text
    assert "inventory" in r.text


def test_web_admin_tools_data_lists_tools_and_modules(client: TestClient) -> None:
    _login(client)
    r = client.get("/web/admin/tools-data")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("tools"), list)
    assert isinstance(data.get("forensic_modules"), list)
    assert isinstance(data.get("analytics"), dict)

    tool_names = {t.get("name") for t in data["tools"]}
    module_names = {m.get("name") for m in data["forensic_modules"]}
    categories = {t.get("category") for t in data["tools"]}

    assert "file" in tool_names
    assert "tcpdump" in tool_names
    assert "inventory" in module_names
    assert "network" in categories
