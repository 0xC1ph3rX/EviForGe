from __future__ import annotations

import errno
import json
import socket
from pathlib import Path

import typer
from rich import print

from eviforge.config import ACK_TEXT, load_settings
from eviforge.core.db import create_session_factory, get_setting

app = typer.Typer(add_completion=False, help="EviForge CLI (offline-first forensic platform)")


class BindInUseError(RuntimeError):
    pass


def _session_factory():
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return create_session_factory(settings.database_url)


def _assert_bind_available(host: str, port: int) -> None:
    """
    Preflight server bind to provide a clean, actionable error when the
    configured host/port is already occupied.
    """
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    last_exc: OSError | None = None
    for family, socktype, proto, _canon, sockaddr in infos:
        with socket.socket(family, socktype, proto) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(sockaddr)
                return
            except OSError as exc:
                last_exc = exc
                if exc.errno == errno.EADDRINUSE:
                    continue
                raise
    if last_exc and last_exc.errno == errno.EADDRINUSE:
        raise BindInUseError(f"Address already in use: http://{host}:{port}")


@app.command("ack")
def ack_cmd(actor: str = "local"):
    """Print the required authorization acknowledgement text."""
    print(ACK_TEXT)
    print("\nSubmit it with: eviforge ack-set --text \"...\"")


@app.command("ack-set")
def ack_set(text: str = typer.Option(..., "--text"), actor: str = "local"):
    """Persist the authorization acknowledgement locally (required before use)."""
    from eviforge.api.routes.auth import AckRequest, ack as ack_api

    ack_api(AckRequest(text=text, actor=actor))
    print("[green]Acknowledgement stored.[/green]")


@app.command("ack-status")
def ack_status():
    """Show whether authorization acknowledgement has been completed."""
    SessionLocal = _session_factory()
    with SessionLocal() as session:
        ack = get_setting(session, "authorization_ack")
    print(json.dumps({"acknowledged": ack is not None, "required_text": ACK_TEXT}, indent=2))


@app.command("api")
def run_api(
    host: str | None = typer.Option(None, "--host", help="Bind host (defaults to EVIFORGE_BIND_HOST)."),
    port: int | None = typer.Option(None, "--port", min=1, max=65535, help="Bind port (defaults to EVIFORGE_BIND_PORT)."),
):
    """Run the API server (dev)."""
    import uvicorn

    settings = load_settings()
    bind_host = host or settings.bind_host
    bind_port = port or settings.bind_port

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.vault_dir.mkdir(parents=True, exist_ok=True)

    try:
        _assert_bind_available(bind_host, bind_port)
    except BindInUseError:
        print(f"[red]Port busy:[/red] http://{bind_host}:{bind_port}")
        print("Use: `eviforge api --port 8001` or stop the existing process.")
        raise typer.Exit(code=1)

    uvicorn.run(
        "eviforge.api.main:app",
        host=bind_host,
        port=bind_port,
        reload=False,
        log_level="info",
    )


@app.command("doctor")
def run_doctor_cmd():
    """Check availability of forensic tools and dependencies."""
    from eviforge.doctor import run_doctor

    report = run_doctor()
    print(f"[bold]Tools Doctor Report[/bold] (Overall: {'[green]OK[/green]' if report['ok'] else '[red]FAIL[/red]'})")

    for check in report["checks"]:
        color = "green" if check["ok"] else "red"
        print(f"[{color}] {check['name']:<20} : {check['details']} [/{color}]")

    if not report["ok"]:
        raise typer.Exit(code=1)


def main():
    app()


if __name__ == "__main__":
    main()
