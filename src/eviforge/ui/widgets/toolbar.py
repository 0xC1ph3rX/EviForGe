from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QStyle, QToolBar


class TopToolbar(QToolBar):
    open_case_requested = Signal()
    import_evidence_requested = Signal()
    live_capture_requested = Signal()
    run_analysis_requested = Signal()
    export_requested = Signal()
    settings_requested = Signal()
    refresh_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Main Toolbar", parent)
        self.setMovable(False)
        self.setFloatable(False)

        self._add_action(
            "Open Case",
            QStyle.SP_DirOpenIcon,
            self.open_case_requested.emit,
            "Open currently selected case workspace",
        )
        self._add_action(
            "Open Evidence",
            QStyle.SP_DialogOpenButton,
            self.import_evidence_requested.emit,
            "Import evidence file into selected case",
        )
        self._add_action(
            "Live Capture",
            QStyle.SP_ComputerIcon,
            self.live_capture_requested.emit,
            "Optional explicit packet capture workflow",
        )
        self._add_action(
            "Run Analysis",
            QStyle.SP_MediaPlay,
            self.run_analysis_requested.emit,
            "Run selected forensic module(s)",
        )
        self._add_action(
            "Export",
            QStyle.SP_DialogSaveButton,
            self.export_requested.emit,
            "Export filtered results",
        )
        self._add_action(
            "Settings",
            QStyle.SP_FileDialogDetailedView,
            self.settings_requested.emit,
            "Profiles and runtime preferences",
        )
        self._add_action(
            "Refresh",
            QStyle.SP_BrowserReload,
            self.refresh_requested.emit,
            "Refresh cases, evidence, jobs",
        )

    def _add_action(self, text: str, icon_enum, callback, tip: str) -> QAction:
        icon = self.style().standardIcon(icon_enum)
        action = QAction(icon, text, self)
        action.setToolTip(tip)
        action.triggered.connect(callback)
        self.addAction(action)
        return action
