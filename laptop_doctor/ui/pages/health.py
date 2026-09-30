"""Health: every check as a card with its status, finding and suggested fix."""

import time

from PySide6.QtWidgets import QGridLayout, QProgressBar, QWidget

from ... import checks
from .. import icons, theme
from ..widgets import Card, PageHeader, Pill, button, clear_layout, copy_button, hbox, label, scroll, vbox

ICONS = {"disk": "disk", "memory": "memory", "gpu": "gpu", "reboot": "power", "units": "settings",
         "errors": "crashes", "crashes": "crashes", "backups": "folder", "network": "network",
         "battery": "battery", "temps": "temp", "updates": "updates"}


class HealthPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.header = PageHeader("Health checks", "Read-only. Fixes that need root are shown for you to run.")
        self.run_btn = self.header.add_action(button("Run checks", "play", "primary"))
        self.run_btn.clicked.connect(state.run_checks)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(6)
        self.progress.hide()
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        body = QWidget()
        body.setLayout(vbox(self.header, self.progress, self.grid, None, spacing=14, margins=(28, 24, 28, 24)))
        self.setLayout(vbox(scroll(body)))
        state.checks_started.connect(self.on_started)
        state.checks_progress.connect(self.on_progress)
        state.checks_done.connect(self.on_summary)
        state.checks_failed.connect(self.on_failed)

    def on_started(self):
        self.run_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()

    def on_progress(self, i, n):
        self.progress.setMaximum(n)
        self.progress.setValue(i)

    def on_failed(self, err: str):
        self.run_btn.setEnabled(True)
        self.progress.hide()
        self.header.sub.setText(f"Check run failed: {err}")

    def on_summary(self, s: checks.Summary):
        self.run_btn.setEnabled(True)
        self.progress.hide()
        self.header.sub.setText(f"{s.fails} fail · {s.warns} warn · {len(s.checks) - s.fails - s.warns} ok  ·  "
                                f"checked {time.strftime('%H:%M:%S', time.localtime(s.when))}")
        clear_layout(self.grid)
        ordered = sorted(s.checks, key=lambda c: -checks.RANK[c.status])
        for i, c in enumerate(ordered):
            card = Card(accent=c.status, padding=16, spacing=6)
            ic = label()
            ic.setPixmap(icons.pixmap(ICONS.get(c.name, "health"), theme.status_color(c.status), 18))
            card.add(hbox(ic, label(c.title, "sectionTitle"), None, Pill(c.status), spacing=8))
            card.add(label(c.message, "muted", wrap=True, select=True))
            if c.fix and c.status != checks.OK:
                card.add(hbox(label(c.fix, "code", select=True), copy_button(lambda f=c.fix: f), None, spacing=4))
            card.add(None)
            self.grid.addWidget(card, i // 3, i % 3)
        for col in range(3):
            self.grid.setColumnStretch(col, 1)
