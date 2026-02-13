from __future__ import annotations

from eviforge.ui.app import run_desktop_app


def main() -> None:
    code = run_desktop_app()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
