from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class DetailsInspectorWidget(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailsPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        title = QLabel("Inspector")
        title.setObjectName("PanelTitle")
        root.addWidget(title)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.decoded_table = self._build_kv_tab(self.tabs, "Decoded")
        self.raw_text = self._build_raw_tab(self.tabs, "Raw")
        self.meta_table = self._build_kv_tab(self.tabs, "Metadata")

    def _build_kv_tab(self, parent: QTabWidget, name: str) -> QTableWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Field", "Value", "Copy"])
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(False)
        table.setColumnWidth(0, 160)
        table.setColumnWidth(1, 300)
        table.setColumnWidth(2, 70)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        layout.addWidget(table)

        parent.addTab(page, name)
        return table

    def _build_raw_tab(self, parent: QTabWidget, name: str) -> QPlainTextEdit:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)

        bar = QHBoxLayout()
        bar.addStretch(1)
        copy_btn = QPushButton("Copy All")
        bar.addWidget(copy_btn)
        layout.addLayout(bar)

        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(text)

        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(text.toPlainText()))
        parent.addTab(page, name)
        return text

    def set_record(self, record: dict[str, Any] | None, *, context: dict[str, Any] | None = None) -> None:
        row = record or {}
        raw = json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True)
        self.raw_text.setPlainText(raw)

        decoded_pairs: list[tuple[str, str]] = []
        for key in sorted(row.keys()):
            value = row.get(key)
            if isinstance(value, (dict, list)):
                val = json.dumps(value, ensure_ascii=False, sort_keys=True)
            else:
                val = "" if value is None else str(value)
            decoded_pairs.append((str(key), val))

        self._set_kv_rows(self.decoded_table, decoded_pairs)

        now = datetime.utcnow().isoformat() + "Z"
        meta_pairs = [
            ("rendered_at", now),
            ("field_count", str(len(row.keys()))),
            ("byte_size", str(len(raw.encode("utf-8")))),
        ]
        for k, v in sorted((context or {}).items(), key=lambda kv: kv[0]):
            meta_pairs.append((str(k), "" if v is None else str(v)))

        self._set_kv_rows(self.meta_table, meta_pairs)

    def _set_kv_rows(self, table: QTableWidget, rows: list[tuple[str, str]]) -> None:
        table.setRowCount(len(rows))
        for row_idx, (key, value) in enumerate(rows):
            key_item = QTableWidgetItem(key)
            key_item.setData(Qt.UserRole, value)
            value_item = QTableWidgetItem(value)
            value_item.setToolTip(value)

            table.setItem(row_idx, 0, key_item)
            table.setItem(row_idx, 1, value_item)

            btn = QPushButton("Copy")
            btn.setMaximumWidth(60)
            btn.clicked.connect(lambda _checked=False, text=value: self._copy_to_clipboard(text))
            table.setCellWidget(row_idx, 2, btn)

        table.resizeRowsToContents()

    def _copy_to_clipboard(self, text: str) -> None:
        QApplication.clipboard().setText(text or "")
