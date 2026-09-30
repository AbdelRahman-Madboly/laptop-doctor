"""Reports: daily Markdown reports, browsable and regenerable."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QSplitter, QTextBrowser, QWidget

from ... import report
from ...util import REPORTS
from .. import theme
from ..widgets import PageHeader, button, run_async, vbox


class ReportsPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.header = PageHeader("Reports", f"One per day in {REPORTS}, last {report.KEEP} kept")
        folder = self.header.add_action(button("Open folder", "folder"))
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(REPORTS))))
        self.gen = self.header.add_action(button("Generate now", "file", "primary"))
        self.gen.clicked.connect(self.generate)
        self.list = QListWidget()
        self.list.setFixedWidth(220)
        self.list.currentItemChanged.connect(self._open)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.list)
        split.addWidget(self.view)
        split.setStretchFactor(1, 1)
        split.setHandleWidth(12)
        self.setLayout(vbox(self.header, split, spacing=14, margins=(28, 24, 28, 24)))

    def showEvent(self, e):
        self.reload()
        super().showEvent(e)

    def reload(self, select: str | None = None):
        current = select or (self.list.currentItem().data(Qt.ItemDataRole.UserRole) if self.list.currentItem() else None)
        self.list.clear()
        for path in report.list_reports():
            it = QListWidgetItem(path.stem)
            it.setData(Qt.ItemDataRole.UserRole, str(path))
            self.list.addItem(it)
            if str(path) == current:
                self.list.setCurrentItem(it)
        if not self.list.currentItem() and self.list.count():
            self.list.setCurrentRow(0)
        if not self.list.count():
            self.view.setMarkdown("No reports yet. Press **Generate now**.")

    def _open(self, item):
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        try:
            text = open(path).read()
        except OSError as e:
            text = f"Could not read {path}: {e}"
        self.view.document().setDefaultStyleSheet(
            f"pre, code {{ font-family: 'Ubuntu Sans Mono'; color: {theme.current.text}; }}"
            f"h1 {{ font-size: 16pt; }}")
        self.view.setMarkdown(text)

    def generate(self):
        self.gen.setEnabled(False)
        self.gen.setText("Writing…")
        run_async(report.write, self.state.summary, on_done=self._generated)

    def _generated(self, path):
        self.gen.setEnabled(True)
        self.gen.setText("Generate now")
        self.reload(str(path))
