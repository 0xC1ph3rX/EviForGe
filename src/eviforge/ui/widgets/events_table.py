from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QFrame, QHeaderView, QLabel, QTableView, QVBoxLayout


class EventsTableWidget(QFrame):
    row_selected = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CenterPanel")

        self._rows: list[dict[str, Any]] = []
        self._columns: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Analysis Events")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self.table = QTableView()
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setShowGrid(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionsClickable(True)

        self.model = QStandardItemModel(self)
        self.table.setModel(self.model)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        layout.addWidget(self.table, 1)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self._rows = list(rows or [])
        self.model.clear()

        if not self._rows:
            self._columns = []
            return

        cols: list[str] = []
        for row in self._rows[:300]:
            for key in row.keys():
                if key not in cols:
                    cols.append(key)
        self._columns = cols[:14]

        self.model.setHorizontalHeaderLabels(self._columns)

        for row in self._rows:
            items: list[QStandardItem] = []
            for col in self._columns:
                raw = row.get(col)
                text = self._cell(raw)
                item = QStandardItem(text)
                item.setEditable(False)
                item.setData(raw, Qt.UserRole)
                items.append(item)
            self.model.appendRow(items)

        self.table.resizeColumnsToContents()

    def selected_count(self) -> int:
        idx = self.table.selectionModel().selectedRows()
        return len(idx)

    def total_count(self) -> int:
        return len(self._rows)

    def _on_selection_changed(self, *_args) -> None:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        row_idx = sel[0].row()
        if 0 <= row_idx < len(self._rows):
            self.row_selected.emit(self._rows[row_idx])

    def _cell(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            s = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            s = str(value)
        if len(s) > 260:
            return s[:257] + "..."
        return s
