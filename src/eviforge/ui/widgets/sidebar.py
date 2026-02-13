from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class SidebarWidget(QFrame):
    case_selected = Signal(str)
    evidence_selected = Signal(str)
    module_selected = Signal(str)
    job_selected = Signal(str)
    new_case_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarPanel")

        self._all_cases: list[dict[str, Any]] = []
        self._all_evidence: list[dict[str, Any]] = []
        self._all_modules: list[dict[str, Any]] = []
        self._all_jobs: list[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("Workspace")
        title.setObjectName("PanelTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.new_case_btn = QPushButton("New Case")
        self.new_case_btn.clicked.connect(self.new_case_requested.emit)
        title_row.addWidget(self.new_case_btn)
        root.addLayout(title_row)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search cases/evidence/modules/jobs...")
        self.search.textChanged.connect(self._apply_search_filter)
        root.addWidget(self.search)

        self.case_list = self._build_section(root, "Cases")
        self.evidence_list = self._build_section(root, "Evidence")
        self.module_list = self._build_section(root, "Modules")
        self.job_list = self._build_section(root, "Jobs")

        self.case_list.currentItemChanged.connect(self._emit_case_selected)
        self.evidence_list.currentItemChanged.connect(self._emit_evidence_selected)
        self.module_list.currentItemChanged.connect(self._emit_module_selected)
        self.job_list.currentItemChanged.connect(self._emit_job_selected)

    def _build_section(self, root: QVBoxLayout, title: str) -> QListWidget:
        group = QGroupBox(title)
        group.setObjectName("SidebarSection")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 14, 8, 8)
        widget = QListWidget()
        widget.setSelectionMode(QListWidget.SingleSelection)
        layout.addWidget(widget)
        root.addWidget(group, 1)
        return widget

    def set_cases(self, items: list[dict[str, Any]]) -> None:
        self._all_cases = list(items or [])
        self._render_list(self.case_list, self._all_cases, label_fn=lambda c: f"{c['name']} [{c['id'][:8]}]")

    def set_evidence(self, items: list[dict[str, Any]]) -> None:
        self._all_evidence = list(items or [])
        self._render_list(self.evidence_list, self._all_evidence, label_fn=lambda e: f"{e['filename']} [{e['id'][:8]}]")

    def set_modules(self, items: list[dict[str, Any]]) -> None:
        self._all_modules = list(items or [])

        def _label(mod: dict[str, Any]) -> str:
            suffix = " (evidence)" if mod.get("requires_evidence") else ""
            return f"{mod['name']}{suffix}"

        self._render_list(self.module_list, self._all_modules, label_fn=_label)

    def set_jobs(self, items: list[dict[str, Any]]) -> None:
        self._all_jobs = list(items or [])

        def _label(job: dict[str, Any]) -> str:
            status = str(job.get("status") or "unknown")
            module = str(job.get("module") or "-")
            return f"{status:>9}  {module:<12} {job['id'][:8]}"

        self._render_list(self.job_list, self._all_jobs, label_fn=_label)

    def select_case_by_id(self, case_id: str | None) -> None:
        if not case_id:
            return
        self._select_by_id(self.case_list, case_id)

    def select_evidence_by_id(self, evidence_id: str | None) -> None:
        if not evidence_id:
            return
        self._select_by_id(self.evidence_list, evidence_id)

    def select_job_by_id(self, job_id: str | None) -> None:
        if not job_id:
            return
        self._select_by_id(self.job_list, job_id)

    def _render_list(self, widget: QListWidget, rows: list[dict[str, Any]], *, label_fn) -> None:
        selected_id = self._selected_id(widget)
        widget.blockSignals(True)
        widget.clear()
        for row in rows:
            item = QListWidgetItem(label_fn(row))
            item.setData(Qt.UserRole, row.get("id"))
            item.setToolTip(str(row))
            widget.addItem(item)
        widget.blockSignals(False)
        if selected_id:
            self._select_by_id(widget, selected_id)
        self._apply_search_filter(self.search.text())

    def _selected_id(self, widget: QListWidget) -> str | None:
        current = widget.currentItem()
        if not current:
            return None
        return current.data(Qt.UserRole)

    def _select_by_id(self, widget: QListWidget, row_id: str) -> None:
        for i in range(widget.count()):
            item = widget.item(i)
            if item.data(Qt.UserRole) == row_id:
                widget.setCurrentItem(item)
                return

    def _apply_search_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for widget in (self.case_list, self.evidence_list, self.module_list, self.job_list):
            for i in range(widget.count()):
                item = widget.item(i)
                hay = item.text().lower()
                item.setHidden(bool(needle) and needle not in hay)

    def _emit_case_selected(self, current: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if current:
            self.case_selected.emit(current.data(Qt.UserRole))

    def _emit_evidence_selected(self, current: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if current:
            self.evidence_selected.emit(current.data(Qt.UserRole))

    def _emit_module_selected(self, current: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if current:
            self.module_selected.emit(current.data(Qt.UserRole))

    def _emit_job_selected(self, current: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if current:
            self.job_selected.emit(current.data(Qt.UserRole))
