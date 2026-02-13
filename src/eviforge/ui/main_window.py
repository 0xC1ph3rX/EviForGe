from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from eviforge.desktop_backend import DesktopBackend
from eviforge.ui.controllers.main_controller import MainController
from eviforge.ui.widgets.details_inspector import DetailsInspectorWidget
from eviforge.ui.widgets.events_table import EventsTableWidget
from eviforge.ui.widgets.filter_bar import FilterBar
from eviforge.ui.widgets.module_runner import ModuleRunnerDock
from eviforge.ui.widgets.sidebar import SidebarWidget
from eviforge.ui.widgets.status_panel import StatusPanel
from eviforge.ui.widgets.toolbar import TopToolbar


class MainWindow(QMainWindow):
    def __init__(self, backend: DesktopBackend, *, qss_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("EviForge Desktop - DFIR Analysis Console")
        self.resize(1600, 920)
        self.setMinimumSize(1200, 760)

        self.backend = backend
        if qss_path and qss_path.exists():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))

        root = QWidget()
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        self.toolbar = TopToolbar(self)
        root_layout.addWidget(self.toolbar)

        self.filter_bar = FilterBar(self)
        root_layout.addWidget(self.filter_bar)

        self.splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(self.splitter, 1)

        self.sidebar = SidebarWidget(self)
        self.center_table = EventsTableWidget(self)
        self.details = DetailsInspectorWidget(self)

        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.center_table)
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 23)
        self.splitter.setStretchFactor(1, 54)
        self.splitter.setStretchFactor(2, 23)
        self.splitter.setSizes([360, 860, 380])

        self.status_panel = StatusPanel(self)
        root_layout.addWidget(self.status_panel)

        self.module_runner = ModuleRunnerDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.module_runner)
        self.module_runner.hide()

        self.controller = MainController(
            parent=self,
            backend=self.backend,
            sidebar=self.sidebar,
            table=self.center_table,
            details=self.details,
            filter_bar=self.filter_bar,
            module_runner=self.module_runner,
            status_panel=self.status_panel,
        )
        self._connect_actions()
        self.controller.initialize()

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1800)
        self.poll_timer.timeout.connect(self.controller.poll_jobs)
        self.poll_timer.start()

    def _connect_actions(self) -> None:
        self.toolbar.open_case_requested.connect(self.controller.open_case)
        self.toolbar.import_evidence_requested.connect(self.controller.import_evidence)
        self.toolbar.live_capture_requested.connect(self.controller.open_live_capture_info)
        self.toolbar.run_analysis_requested.connect(self.controller.run_analysis)
        self.toolbar.export_requested.connect(self.controller.export_results)
        self.toolbar.settings_requested.connect(self.controller.open_settings)
        self.toolbar.refresh_requested.connect(self.controller.refresh_workspace)
