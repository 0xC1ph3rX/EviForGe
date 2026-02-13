from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ModuleRunnerDock(QDockWidget):
    run_selected_requested = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__("Module Runner", parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )

        body = QWidget()
        self.setWidget(body)

        root = QVBoxLayout(body)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        panel = QFrame()
        panel.setObjectName("ModuleRunnerPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("Select Modules")
        title.setObjectName("SectionTitle")
        panel_layout.addWidget(title)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search modules...")
        self.search.textChanged.connect(self._apply_filter)
        panel_layout.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Module", "Needs Evidence"])
        self.tree.setRootIsDecorated(False)
        panel_layout.addWidget(self.tree, 1)

        run_row = QHBoxLayout()
        self.run_btn = QPushButton("Run Selected")
        self.run_btn.clicked.connect(self._emit_run_selected)
        self.clear_btn = QPushButton("Clear Checks")
        self.clear_btn.clicked.connect(self._clear_checks)
        run_row.addWidget(self.run_btn)
        run_row.addWidget(self.clear_btn)
        run_row.addStretch(1)
        panel_layout.addLayout(run_row)

        root.addWidget(panel, 1)

        progress_title = QLabel("Module Progress")
        progress_title.setObjectName("SectionTitle")
        root.addWidget(progress_title)

        self.progress_table = QTableWidget(0, 3)
        self.progress_table.setHorizontalHeaderLabels(["Module", "Status", "Progress"])
        self.progress_table.verticalHeader().setVisible(False)
        self.progress_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.progress_table.setSelectionMode(QTableWidget.NoSelection)
        self.progress_table.setColumnWidth(0, 150)
        self.progress_table.setColumnWidth(1, 110)
        self.progress_table.setColumnWidth(2, 120)
        root.addWidget(self.progress_table, 1)

        self._module_rows: dict[str, int] = {}

    def set_modules(self, modules: list[dict[str, Any]]) -> None:
        selected = set(self.selected_modules())
        self.tree.clear()
        for mod in modules or []:
            name = str(mod.get("name") or "")
            item = QTreeWidgetItem([name, "yes" if mod.get("requires_evidence") else "no"])
            item.setData(0, Qt.UserRole, name)
            state = Qt.Checked if name in selected else Qt.Unchecked
            item.setCheckState(0, state)
            self.tree.addTopLevelItem(item)
        self.tree.sortItems(0, Qt.AscendingOrder)

    def selected_modules(self) -> list[str]:
        out: list[str] = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                name = item.data(0, Qt.UserRole)
                if name:
                    out.append(str(name))
        return out

    def mark_progress(self, module: str, status: str, percent: int) -> None:
        if module not in self._module_rows:
            row = self.progress_table.rowCount()
            self.progress_table.insertRow(row)
            self.progress_table.setItem(row, 0, QTableWidgetItem(module))
            self.progress_table.setItem(row, 1, QTableWidgetItem(status))
            pb = QProgressBar()
            pb.setRange(0, 100)
            pb.setValue(max(0, min(100, percent)))
            self.progress_table.setCellWidget(row, 2, pb)
            self._module_rows[module] = row
            return

        row = self._module_rows[module]
        status_item = self.progress_table.item(row, 1)
        if status_item:
            status_item.setText(status)
        pb = self.progress_table.cellWidget(row, 2)
        if isinstance(pb, QProgressBar):
            pb.setValue(max(0, min(100, percent)))

    def clear_progress(self) -> None:
        self.progress_table.setRowCount(0)
        self._module_rows = {}

    def _emit_run_selected(self) -> None:
        modules = self.selected_modules()
        if modules:
            self.run_selected_requested.emit(modules)

    def _clear_checks(self) -> None:
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setCheckState(0, Qt.Unchecked)

    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            name = item.text(0).lower()
            item.setHidden(bool(needle) and needle not in name)
