from __future__ import annotations

import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)


_VALID_FILTER_RE = re.compile(r"^[\w\s:./@\-\[\]\(\)\"'=,]*$")


class FilterBar(QFrame):
    apply_requested = Signal(str)
    clear_requested = Signal()
    save_preset_requested = Signal(str)
    preset_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FilterBar")

        self._preset_map: dict[str, str] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        label = QLabel("Display Filter")
        label.setObjectName("SectionTitle")
        layout.addWidget(label)

        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(190)
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        layout.addWidget(self.preset_combo)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Example: status:FAILED module:yara")
        self.input.textChanged.connect(self._validate)
        self.input.returnPressed.connect(self._emit_apply)
        layout.addWidget(self.input, 1)

        self.feedback = QLabel("ready")
        self.feedback.setObjectName("SubtleLabel")
        layout.addWidget(self.feedback)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._emit_apply)
        layout.addWidget(self.apply_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._emit_clear)
        layout.addWidget(self.clear_btn)

        self.save_btn = QPushButton("Save Preset")
        self.save_btn.clicked.connect(self._emit_save)
        layout.addWidget(self.save_btn)

        self.set_presets({
            "Failed Jobs": "status:FAILED",
            "Completed Jobs": "status:COMPLETED",
            "Suspicious": "is_suspicious:true",
        })
        self._validate(self.input.text())

    def set_presets(self, presets: dict[str, str]) -> None:
        self._preset_map = dict(sorted((presets or {}).items(), key=lambda kv: kv[0].lower()))
        current = self.preset_combo.currentText()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("Custom")
        for name in self._preset_map.keys():
            self.preset_combo.addItem(name)
        idx = self.preset_combo.findText(current)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        else:
            self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)

    def current_query(self) -> str:
        return self.input.text().strip()

    def set_query(self, query: str) -> None:
        self.input.setText((query or "").strip())

    def is_query_valid(self) -> bool:
        q = self.current_query()
        return not q or bool(_VALID_FILTER_RE.fullmatch(q))

    def _validate(self, text: str) -> None:
        q = (text or "").strip()
        if not q:
            self.feedback.setText("no filter")
            self.feedback.setStyleSheet("color:#8eb6dd;")
            self.input.setProperty("valid", "")
            self._refresh_line_edit_style()
            return

        if not _VALID_FILTER_RE.fullmatch(q):
            self.feedback.setText("invalid characters")
            self.feedback.setStyleSheet("color:#ff6f88;")
            self.input.setProperty("valid", "false")
            self._refresh_line_edit_style()
            return

        self.feedback.setText("valid")
        self.feedback.setStyleSheet("color:#31d89a;")
        self.input.setProperty("valid", "true")
        self._refresh_line_edit_style()

    def _refresh_line_edit_style(self) -> None:
        self.input.style().unpolish(self.input)
        self.input.style().polish(self.input)
        self.input.update()

    def _emit_apply(self) -> None:
        if not self.is_query_valid():
            return
        self.apply_requested.emit(self.current_query())

    def _emit_clear(self) -> None:
        self.input.clear()
        self.clear_requested.emit()

    def _emit_save(self) -> None:
        if not self.is_query_valid() or not self.current_query():
            return
        self.save_preset_requested.emit(self.current_query())

    def _on_preset_changed(self, name: str) -> None:
        if not name or name == "Custom":
            return
        query = self._preset_map.get(name, "")
        self.set_query(query)
        self.preset_selected.emit(query)
