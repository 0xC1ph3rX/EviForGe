from __future__ import annotations

import sys
from pathlib import Path


def run_desktop_app() -> int:
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("PySide6"):
            print(
                "PySide6 is required for the redesigned desktop UI.\n"
                "Install with: pip install PySide6\n"
                "Or: pip install -e '.[desktop]'"
            )
            return 1
        raise

    from eviforge.desktop_backend import DesktopBackend
    from eviforge.ui.main_window import MainWindow

    QApplication.setAttribute(QGuiApplication.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setApplicationName("EviForge Desktop")
    app.setOrganizationName("EviForge")
    app.setStyle("Fusion")

    backend = DesktopBackend()
    qss_path = Path(__file__).resolve().parent / "themes" / "cyber_neon.qss"
    window = MainWindow(backend=backend, qss_path=qss_path)
    window.show()

    return app.exec()
