from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from eviforge import cli


runner = CliRunner()


def test_api_command_forwards_host_port(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    vault_dir = tmp_path / "vault"

    monkeypatch.setenv("EVIFORGE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("EVIFORGE_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("EVIFORGE_DATABASE_URL", f"sqlite:///{(tmp_path / 'eviforge.sqlite').as_posix()}")
    monkeypatch.setenv("EVIFORGE_REDIS_URL", "redis://127.0.0.1:0/0")

    captured: dict[str, object] = {}

    def fake_uvicorn_run(app_ref: str, **kwargs) -> None:
        captured["app_ref"] = app_ref
        captured.update(kwargs)

    monkeypatch.setattr(cli, "_assert_bind_available", lambda host, port: None)
    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)

    result = runner.invoke(cli.app, ["api", "--host", "127.0.0.1", "--port", "8101"])

    assert result.exit_code == 0
    assert captured["app_ref"] == "eviforge.api.main:app"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8101


def test_api_command_prints_clear_message_when_port_busy(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    vault_dir = tmp_path / "vault"

    monkeypatch.setenv("EVIFORGE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("EVIFORGE_VAULT_DIR", str(vault_dir))
    monkeypatch.setenv("EVIFORGE_DATABASE_URL", f"sqlite:///{(tmp_path / 'eviforge.sqlite').as_posix()}")
    monkeypatch.setenv("EVIFORGE_REDIS_URL", "redis://127.0.0.1:0/0")

    def raise_busy(host: str, port: int) -> None:
        raise cli.BindInUseError(f"busy {host}:{port}")

    monkeypatch.setattr(cli, "_assert_bind_available", raise_busy)

    result = runner.invoke(cli.app, ["api", "--host", "127.0.0.1", "--port", "8000"])

    assert result.exit_code == 1
    assert "Port busy" in result.output
    assert "eviforge api --port 8001" in result.output
