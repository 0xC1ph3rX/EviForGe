from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar


class StatusPanel(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusPanel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(12)

        self.state_label = QLabel("Ready")
        self.state_label.setObjectName("SubtleLabel")
        layout.addWidget(self.state_label, 2)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedWidth(240)
        layout.addWidget(self.progress)

        self.selection_label = QLabel("Selected: 0")
        self.selection_label.setObjectName("SubtleLabel")
        layout.addWidget(self.selection_label)

        self.range_label = QLabel("Time Range: n/a")
        self.range_label.setObjectName("SubtleLabel")
        layout.addWidget(self.range_label)

    def set_status(self, text: str) -> None:
        self.state_label.setText(text)

    def set_progress(self, value: int) -> None:
        self.progress.setValue(max(0, min(100, value)))

    def set_selection_count(self, count: int) -> None:
        self.selection_label.setText(f"Selected: {count}")

    def set_time_range(self, start: str | None, end: str | None) -> None:
        if not start and not end:
            self.range_label.setText("Time Range: n/a")
            return
        s = start or "?"
        e = end or "?"
        self.range_label.setText(f"Time Range: {s} -> {e}")

    def mark_updated_now(self) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.state_label.setText(f"Ready (updated {ts})")
