"""Pages that show text sections: crash triage and updates."""

from PySide6.QtWidgets import QComboBox, QPlainTextEdit, QWidget

from ... import triage
from .. import theme
from ..widgets import Card, PageHeader, Pill, button, clear_layout, label, run_async, scroll, vbox


class SectionsPage(QWidget):
    def __init__(self, title: str, subtitle: str, loader, with_days=False):
        super().__init__()
        self.loader, self.with_days = loader, with_days
        self.header = PageHeader(title, subtitle)
        self.subtitle = subtitle
        if with_days:
            self.days = QComboBox()
            for d in (1, 3, 7, 14, 30):
                self.days.addItem(f"Last {d} day{'s' if d > 1 else ''}", d)
            self.days.setCurrentIndex(2)
            self.days.currentIndexChanged.connect(self.load)
            self.header.add_action(self.days)
        self.refresh = self.header.add_action(button("Refresh", "updates", "primary"))
        self.refresh.clicked.connect(self.load)
        self.list = vbox(spacing=12)
        body = QWidget()
        body.setLayout(vbox(self.header, self.list, None, spacing=14, margins=(28, 24, 28, 24)))
        self.setLayout(vbox(scroll(body)))
        self._loaded = False

    def showEvent(self, e):
        if not self._loaded:
            self.load()
        super().showEvent(e)

    def load(self):
        self._loaded = True
        self.refresh.setEnabled(False)
        self.header.sub.setText("Reading the journal…" if self.with_days else "Asking package managers…")
        args = (self.days.currentData(),) if self.with_days else ()
        run_async(self.loader, *args, on_done=self._show)

    def _show(self, sections):
        self.refresh.setEnabled(True)
        self.header.sub.setText(self.subtitle)
        clear_layout(self.list)
        for title, lines in sections:
            lines = [ln for ln in lines if ln.strip()]
            card = Card(padding=16, spacing=8)
            card.header.addWidget(label(title, "sectionTitle", wrap=True), 1)
            card.header.addWidget(Pill("INFO" if not lines else "WARN" if self._is_bad(title) else "INFO",
                                       f"{len(lines)} line{'s' if len(lines) != 1 else ''}"))
            card.body.addLayout(card.header)
            if lines:
                text = QPlainTextEdit("\n".join(lines))
                text.setReadOnly(True)
                text.setFont(theme.mono(9))
                text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
                text.setFixedHeight(min(320, 26 + 17 * len(lines)))
                card.add(text)
            else:
                card.add(label("Nothing found.", "faint"))
            self.list.addWidget(card)

    @staticmethod
    def _is_bad(title: str) -> bool:
        return any(w in title for w in ("Crash reports", "Kernel", "segfaults", "failed"))


def crashes_page():
    return SectionsPage("Crashes & errors", "Boots, crash reports, OOM kills, GPU Xid, lockups, previous-boot errors",
                        triage.crashes, with_days=True)


def updates_page():
    return SectionsPage("Updates", "apt, snap, flatpak, toolchains and npm globals. Apply them yourself.",
                        triage.updates)
