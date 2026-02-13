from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from eviforge.desktop_backend import DesktopBackend
from eviforge.ui.widgets.details_inspector import DetailsInspectorWidget
from eviforge.ui.widgets.events_table import EventsTableWidget
from eviforge.ui.widgets.filter_bar import FilterBar
from eviforge.ui.widgets.module_runner import ModuleRunnerDock
from eviforge.ui.widgets.sidebar import SidebarWidget
from eviforge.ui.widgets.status_panel import StatusPanel


class MainController(QObject):
    def __init__(
        self,
        *,
        parent,
        backend: DesktopBackend,
        sidebar: SidebarWidget,
        table: EventsTableWidget,
        details: DetailsInspectorWidget,
        filter_bar: FilterBar,
        module_runner: ModuleRunnerDock,
        status_panel: StatusPanel,
    ) -> None:
        super().__init__(parent)
        self.parent_window = parent
        self.backend = backend
        self.sidebar = sidebar
        self.table = table
        self.details = details
        self.filter_bar = filter_bar
        self.module_runner = module_runner
        self.status_panel = status_panel

        self.case_map: list[dict[str, Any]] = []
        self.evidence_map: list[dict[str, Any]] = []
        self.module_map: list[dict[str, Any]] = []
        self.job_map: list[dict[str, Any]] = []

        self.selected_case_id: str | None = None
        self.selected_evidence_id: str | None = None
        self.selected_module_name: str | None = None
        self.selected_job_id: str | None = None

        self.all_rows: list[dict[str, Any]] = []
        self.filtered_rows: list[dict[str, Any]] = []

    def initialize(self) -> None:
        self._connect_signals()
        self._load_modules()
        self.refresh_workspace()
        self._show_placeholder_rows()

    def _connect_signals(self) -> None:
        self.sidebar.case_selected.connect(self.on_case_selected)
        self.sidebar.evidence_selected.connect(self.on_evidence_selected)
        self.sidebar.module_selected.connect(self.on_module_selected)
        self.sidebar.job_selected.connect(self.on_job_selected)
        self.sidebar.new_case_requested.connect(self.create_case)

        self.table.row_selected.connect(self.on_row_selected)

        self.filter_bar.apply_requested.connect(self.apply_filter)
        self.filter_bar.clear_requested.connect(self.clear_filter)
        self.filter_bar.save_preset_requested.connect(self.save_filter_preset)

        self.module_runner.run_selected_requested.connect(self.run_selected_modules)

    def _status(self, text: str) -> None:
        self.status_panel.set_status(text)

    def refresh_workspace(self) -> None:
        try:
            self.case_map = self.backend.list_cases()
            self.sidebar.set_cases(self.case_map)
            if self.selected_case_id and any(c["id"] == self.selected_case_id for c in self.case_map):
                self.sidebar.select_case_by_id(self.selected_case_id)
            elif self.case_map:
                self.selected_case_id = self.case_map[0]["id"]
                self.sidebar.select_case_by_id(self.selected_case_id)
            else:
                self.selected_case_id = None
                self.evidence_map = []
                self.job_map = []
                self.sidebar.set_evidence([])
                self.sidebar.set_jobs([])

            self._load_profile_filter_presets()
            self._status("Workspace refreshed")
            self.status_panel.mark_updated_now()
        except Exception as exc:
            self._show_error("Refresh Failed", str(exc))

    def _load_modules(self) -> None:
        try:
            self.module_map = self.backend.available_modules()
            self.sidebar.set_modules(self.module_map)
            self.module_runner.set_modules(self.module_map)
        except Exception as exc:
            self._show_error("Module Load Failed", str(exc))

    def on_case_selected(self, case_id: str) -> None:
        self.selected_case_id = case_id
        self.selected_evidence_id = None
        self.selected_job_id = None
        self._refresh_evidence()
        self._refresh_jobs()
        case = next((c for c in self.case_map if c["id"] == case_id), None)
        if case:
            self.details.set_record(case, context={"kind": "case"})
            self._status(f"Case selected: {case['name']}")

    def on_evidence_selected(self, evidence_id: str) -> None:
        self.selected_evidence_id = evidence_id
        ev = next((e for e in self.evidence_map if e["id"] == evidence_id), None)
        if ev:
            self.details.set_record(ev, context={"kind": "evidence"})
            self._status(f"Evidence selected: {ev['filename']}")

    def on_module_selected(self, module_name: str) -> None:
        self.selected_module_name = module_name
        mod = next((m for m in self.module_map if m["name"] == module_name), None)
        if mod:
            self.details.set_record(mod, context={"kind": "module"})
            self._status(f"Module selected: {module_name}")

    def on_job_selected(self, job_id: str) -> None:
        self.selected_job_id = job_id
        job = next((j for j in self.job_map if j["id"] == job_id), None)
        if not job:
            return
        self.details.set_record(job, context={"kind": "job"})
        self._status(f"Job selected: {job['id'][:8]} ({job['status']})")
        self._load_rows_for_job(job)

    def on_row_selected(self, row: dict[str, Any]) -> None:
        self.details.set_record(
            row,
            context={
                "kind": "event",
                "filtered_rows": len(self.filtered_rows),
                "total_rows": len(self.all_rows),
            },
        )
        self.status_panel.set_selection_count(self.table.selected_count())

    def apply_filter(self, query: str) -> None:
        if not self.all_rows:
            self._status("No rows loaded to filter")
            return
        self.filtered_rows = self.backend.filter_rows(self.all_rows, query)
        self.table.set_rows(self.filtered_rows)
        self._status(f"Filter applied: {len(self.filtered_rows)} / {len(self.all_rows)} rows")
        self.status_panel.set_selection_count(0)
        self._update_time_range(self.filtered_rows)

    def clear_filter(self) -> None:
        if not self.all_rows:
            self.table.set_rows([])
            self.status_panel.set_selection_count(0)
            self._update_time_range([])
            return
        self.filtered_rows = list(self.all_rows)
        self.table.set_rows(self.filtered_rows)
        self._status(f"Filter cleared: {len(self.filtered_rows)} rows")
        self.status_panel.set_selection_count(0)
        self._update_time_range(self.filtered_rows)

    def save_filter_preset(self, query: str) -> None:
        name, ok = QInputDialog.getText(self.parent_window, "Save Filter Preset", "Preset name:")
        if not ok:
            return
        preset_name = (name or "").strip()
        if not preset_name:
            self._show_error("Invalid Preset", "Preset name cannot be empty.")
            return

        try:
            store = self.backend._load_profiles()
            active_name = str(store.get("active", "default"))
            profiles = store.setdefault("profiles", {})
            profile = dict(profiles.get(active_name, {}))
            presets = dict(profile.get("filter_presets", {}))
            presets[preset_name] = query
            profile["filter_presets"] = presets
            profiles[active_name] = profile
            self.backend.profile_path.write_text(
                json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self._load_profile_filter_presets()
            self._status(f"Preset saved: {preset_name}")
        except Exception as exc:
            self._show_error("Save Preset Failed", str(exc))

    def open_case(self) -> None:
        if not self.case_map:
            self.create_case()
            return
        if self.selected_case_id:
            self.sidebar.select_case_by_id(self.selected_case_id)
            return
        self.selected_case_id = self.case_map[0]["id"]
        self.sidebar.select_case_by_id(self.selected_case_id)

    def create_case(self) -> None:
        name, ok = QInputDialog.getText(self.parent_window, "New Case", "Case name:")
        if not ok:
            return
        case_name = (name or "").strip()
        if not case_name:
            self._show_error("Invalid Case", "Case name is required.")
            return
        try:
            created = self.backend.create_case(case_name, actor="desktop-qt")
            self.refresh_workspace()
            self.selected_case_id = created["id"]
            self.sidebar.select_case_by_id(created["id"])
            self._status(f"Case created: {created['name']}")
        except Exception as exc:
            self._show_error("Create Case Failed", str(exc))

    def import_evidence(self) -> None:
        if not self.selected_case_id:
            self._show_error("No Case", "Select a case first.")
            return

        path, _ = QFileDialog.getOpenFileName(self.parent_window, "Open Evidence")
        if not path:
            return

        try:
            ev = self.backend.ingest_evidence(self.selected_case_id, path, actor="desktop-qt")
            self._refresh_evidence()
            self.selected_evidence_id = ev["id"]
            self.sidebar.select_evidence_by_id(ev["id"])
            self._status(f"Evidence imported: {ev['filename']}")
        except Exception as exc:
            self._show_error("Import Failed", str(exc))

    def run_analysis(self) -> None:
        self.module_runner.show()
        self.module_runner.raise_()
        selected = self.module_runner.selected_modules()
        if selected:
            self.run_selected_modules(selected)
            return
        if self.selected_module_name:
            self.run_selected_modules([self.selected_module_name])

    def run_selected_modules(self, modules: list[str]) -> None:
        if not self.selected_case_id:
            self._show_error("No Case", "Select a case first.")
            return
        if not modules:
            self._show_error("No Modules", "Select at least one module.")
            return

        self.module_runner.clear_progress()
        submitted = 0
        for idx, module_name in enumerate(modules, start=1):
            mod = next((m for m in self.module_map if m["name"] == module_name), None)
            if not mod:
                continue
            if mod.get("requires_evidence") and not self.selected_evidence_id:
                self.module_runner.mark_progress(module_name, "blocked", 0)
                continue
            try:
                self.module_runner.mark_progress(module_name, "queued", 8)
                self.backend.submit_module(
                    self.selected_case_id,
                    module_name,
                    evidence_id=self.selected_evidence_id,
                    params={},
                    actor="desktop-qt",
                )
                self.module_runner.mark_progress(module_name, "submitted", 15)
                submitted += 1
            except Exception as exc:
                self.module_runner.mark_progress(module_name, f"error: {exc}", 0)

            self.status_panel.set_progress(int((idx / max(1, len(modules))) * 100))

        self._refresh_jobs()
        self._status(f"Submitted {submitted}/{len(modules)} module jobs")

    def export_results(self) -> None:
        if not self.filtered_rows:
            self._show_error("No Data", "No rows to export.")
            return

        target, _ = QFileDialog.getSaveFileName(
            self.parent_window,
            "Export Results",
            str(Path.home() / "eviforge_results.json"),
            "JSON (*.json);;CSV (*.csv)",
        )
        if not target:
            return

        try:
            path = self.backend.export_rows(self.filtered_rows, target)
            self._status(f"Exported {len(self.filtered_rows)} rows -> {path}")
        except Exception as exc:
            self._show_error("Export Failed", str(exc))

    def open_settings(self) -> None:
        profile_names = self.backend.list_profile_names()
        store = self.backend._load_profiles()
        current_profile = str(store.get("active", "default"))
        profile, ok = QInputDialog.getItem(
            self.parent_window,
            "Settings / Profile",
            "Active profile:",
            profile_names,
            editable=True,
            current=profile_names.index(current_profile) if current_profile in profile_names else 0,
        )
        if not ok:
            return

        mode, ok = QInputDialog.getItem(
            self.parent_window,
            "Execution Mode",
            "Job execution mode:",
            ["auto", "inline", "queue"],
            editable=False,
        )
        if not ok:
            return

        max_rows, ok = QInputDialog.getInt(
            self.parent_window,
            "Max Preview Rows",
            "Rows to preview from artifacts:",
            value=int(self.backend.get_active_profile().get("max_preview_rows", 2000)),
            minValue=100,
            maxValue=200000,
            step=100,
        )
        if not ok:
            return

        try:
            self.backend.save_profile(
                profile,
                {
                    "job_execution": mode,
                    "max_preview_rows": int(max_rows),
                },
                set_active=True,
            )
            os.environ["EVIFORGE_JOB_EXECUTION"] = mode
            self._load_profile_filter_presets()
            self._status(f"Profile saved: {profile} ({mode})")
        except Exception as exc:
            self._show_error("Settings Save Failed", str(exc))

    def open_live_capture_info(self) -> None:
        QMessageBox.information(
            self.parent_window,
            "Live Capture",
            (
                "Live capture is optional and explicit-only in EviForge.\n\n"
                "Use external packet tools (e.g., tshark) with legal authorization, then import resulting PCAP files into a case."
            ),
        )

    def poll_jobs(self) -> None:
        if not self.selected_case_id:
            return
        prev = {j["id"]: j.get("status") for j in self.job_map}
        self._refresh_jobs()

        for job in self.job_map:
            old = prev.get(job["id"])
            status = str(job.get("status") or "")
            if old != status:
                module = str(job.get("module") or "unknown")
                pct = self._status_to_progress(status)
                self.module_runner.mark_progress(module, status.lower(), pct)
                self.status_panel.set_progress(pct)

        if self.selected_job_id:
            current = next((j for j in self.job_map if j["id"] == self.selected_job_id), None)
            if current and str(current.get("status")) in {"COMPLETED", "FAILED"}:
                self._load_rows_for_job(current)

    def _status_to_progress(self, status: str) -> int:
        mapping = {
            "PENDING": 15,
            "RUNNING": 60,
            "COMPLETED": 100,
            "FAILED": 100,
        }
        return mapping.get(status, 0)

    def _refresh_evidence(self) -> None:
        if not self.selected_case_id:
            self.evidence_map = []
            self.sidebar.set_evidence([])
            return
        self.evidence_map = self.backend.list_evidence(self.selected_case_id)
        self.sidebar.set_evidence(self.evidence_map)
        if self.selected_evidence_id:
            self.sidebar.select_evidence_by_id(self.selected_evidence_id)

    def _refresh_jobs(self) -> None:
        if not self.selected_case_id:
            self.job_map = []
            self.sidebar.set_jobs([])
            return
        old_selected = self.selected_job_id
        self.job_map = self.backend.list_jobs(self.selected_case_id)
        self.sidebar.set_jobs(self.job_map)
        if old_selected:
            self.sidebar.select_job_by_id(old_selected)

    def _load_rows_for_job(self, job: dict[str, Any]) -> None:
        status = str(job.get("status") or "")
        if status not in {"COMPLETED", "FAILED"}:
            self._status("Job still running; waiting for results")
            return

        output_files = job.get("output_files") or []
        if not output_files or not self.selected_case_id:
            self._show_placeholder_rows()
            self._status("Job has no output rows")
            return

        try:
            rows = self.backend.read_artifact_rows(self.selected_case_id, str(output_files[0]))
            self.all_rows = list(rows)
            self.filtered_rows = list(rows)
            self.table.set_rows(self.filtered_rows)
            self.status_panel.set_selection_count(0)
            self._update_time_range(self.filtered_rows)
            self._status(f"Loaded {len(rows)} rows from {output_files[0]}")
        except Exception as exc:
            self._show_error("Load Artifacts Failed", str(exc))

    def _show_placeholder_rows(self) -> None:
        rows = [
            {
                "timestamp": "2026-02-06T00:01:13Z",
                "source": "pcap",
                "event": "dns_query",
                "query": "example.org",
                "severity": "low",
            },
            {
                "timestamp": "2026-02-06T00:02:00Z",
                "source": "triage",
                "event": "suspicious_extension",
                "file": "invoice.js",
                "severity": "high",
            },
            {
                "timestamp": "2026-02-06T00:03:42Z",
                "source": "yara",
                "event": "rule_match",
                "rule": "suspicious_powershell",
                "severity": "medium",
            },
        ]
        self.all_rows = rows
        self.filtered_rows = rows
        self.table.set_rows(rows)
        self.status_panel.set_selection_count(0)
        self._update_time_range(rows)

    def _update_time_range(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            self.status_panel.set_time_range(None, None)
            return

        values: list[str] = []
        for row in rows:
            for key in ("timestamp", "ts", "time", "created_at"):
                if key in row and row[key]:
                    values.append(str(row[key]))
                    break

        if not values:
            self.status_panel.set_time_range(None, None)
            return

        values.sort()
        self.status_panel.set_time_range(values[0], values[-1])

    def _load_profile_filter_presets(self) -> None:
        try:
            profile = self.backend.get_active_profile()
            presets = profile.get("filter_presets")
            if not isinstance(presets, dict):
                presets = {}
            if not presets:
                presets = {
                    "Failed Jobs": "status:FAILED",
                    "Completed Jobs": "status:COMPLETED",
                    "Suspicious": "is_suspicious:true",
                }
            self.filter_bar.set_presets({str(k): str(v) for k, v in presets.items()})
        except Exception:
            self.filter_bar.set_presets({})

    def _show_error(self, title: str, message: str) -> None:
        self._status(f"{title}: {message}")
        QMessageBox.critical(self.parent_window, title, message)
