"""Optimize: reclaim disk space and memory. Only user-level, reversible-by-rebuild items are cleared."""

import psutil
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QGridLayout, QMessageBox, QWidget

from ... import cleanup
from ...checks import top_memory
from ...util import HOME, human
from ..widgets import (Card, PageHeader, Pill, UsageBar, button, clear_layout, copy_button, hbox, label, run_async,
                       scroll, vbox)


def fmt(size: int) -> str:
    return human(size) if size >= 0 else "?"


class OptimizePage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.items: list[cleanup.Item] = []
        self.boxes: dict[str, QCheckBox] = {}
        self.header = PageHeader("Optimize", "Free disk space and memory. Nothing outside your home folder is touched.")
        self.scan_btn = self.header.add_action(button("Rescan", "search"))
        self.clean_btn = self.header.add_action(button("Clean selected", "broom", "primary"))
        self.scan_btn.clicked.connect(self.scan)
        self.clean_btn.clicked.connect(self.clean_selected)

        # disk summary
        disk = Card("Disk /")
        self.disk_big = label("--", "bigNumber")
        self.disk_sub = label("", "muted")
        self.disk_bar = UsageBar(height=10)
        self.selected_lbl = label("", "faint")
        disk.add(hbox(vbox(self.disk_big, self.disk_sub, spacing=0), None, self.selected_lbl))
        disk.add(self.disk_bar)

        self.safe = Card("Safe to clear")
        self.safe_list = vbox(spacing=10)
        self.safe.add(label("Caches that rebuild themselves. Tick and press Clean selected.", "faint"))
        self.safe.add(self.safe_list)
        self.safe.add(None)

        self.review = Card("Review by hand")
        self.review_list = vbox(spacing=10)
        self.review.add(label("Large folders worth a look. Never cleared automatically.", "faint"))
        self.review.add(self.review_list)
        self.review.add(None)

        self.sudo = Card("Needs sudo")
        self.sudo_list = vbox(spacing=10)
        self.sudo.add(label("Run these yourself in a terminal.", "faint"))
        self.sudo.add(self.sudo_list)
        self.sudo.add(None)

        self.home = Card("Largest folders in home")
        self.home_list = vbox(spacing=8)
        self.home.add(self.home_list)
        self.home.add(None)

        self.mem = Card("Memory hogs")
        self.mem_list = vbox(spacing=8)
        self.mem.add(self.mem_list)
        self.mem.add(None)

        self.log = Card("Last cleanup")
        self.log_lbl = label("Nothing cleaned in this session.", "muted", wrap=True, select=True)
        self.log.add(self.log_lbl)
        self.log.add(None)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(self.safe, 0, 0)
        grid.addWidget(self.review, 0, 1)
        grid.addWidget(self.sudo, 1, 0)
        grid.addWidget(self.home, 1, 1)
        grid.addWidget(self.mem, 2, 0)
        grid.addWidget(self.log, 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        body = QWidget()
        body.setLayout(vbox(self.header, disk, grid, None, spacing=14, margins=(28, 24, 28, 24)))
        self.setLayout(vbox(scroll(body)))
        self._scanned = False

    def showEvent(self, e):
        if not self._scanned:
            self.scan()
        self._update_disk()
        self._update_mem()
        super().showEvent(e)

    def _update_disk(self):
        u = psutil.disk_usage("/")
        self.disk_big.setText(f"{human(u.free)} free")
        self.disk_sub.setText(f"{u.percent:.0f}% of {human(u.total)} used")
        self.disk_bar.set(u.percent)

    def _update_mem(self):
        clear_layout(self.mem_list)
        vm = psutil.virtual_memory()
        for rss, name in top_memory(6):
            bar = UsageBar(height=6, color="blue")
            bar.set(rss * 100 / vm.total)
            self.mem_list.addLayout(vbox(hbox(label(name), None, label(human(rss), "faint")), bar, spacing=4))
        gd = cleanup.gradle_daemons()
        if gd:
            self.mem_list.addWidget(label(f"{len(gd)} Gradle/Kotlin daemon(s) idle: tick them under Safe to clear.",
                                          "faint", wrap=True))

    def scan(self):
        self._scanned = True
        self.scan_btn.setEnabled(False)
        self.clean_btn.setEnabled(False)
        self.header.sub.setText("Scanning… large folders can take a minute")
        for lay in (self.safe_list, self.review_list, self.sudo_list, self.home_list):
            if not lay.count():
                lay.addWidget(label("Measuring…", "faint"))
        run_async(cleanup.scan, on_done=self._scanned_items)
        run_async(cleanup.largest_home_dirs, 8, on_done=self._home_loaded)

    def _scanned_items(self, items):
        self.items = items
        self.scan_btn.setEnabled(True)
        self.clean_btn.setEnabled(True)
        self.header.sub.setText("Free disk space and memory. Nothing outside your home folder is touched.")
        for lay in (self.safe_list, self.review_list, self.sudo_list):
            clear_layout(lay)
        self.boxes.clear()
        for it in items:
            if it.kind == cleanup.SAFE:
                cb = QCheckBox(it.title)
                cb.setChecked(it.size != 0)
                cb.toggled.connect(self._update_selected)
                self.boxes[it.key] = cb
                self.safe_list.addLayout(vbox(hbox(cb, None, label(fmt(it.size), "sectionTitle")),
                                              label(it.detail, "faint", wrap=True), spacing=2))
            elif it.kind == cleanup.REVIEW:
                open_btn = button("Open", "folder", "ghost")
                open_btn.clicked.connect(lambda _=False, p=it.path: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
                self.review_list.addLayout(vbox(hbox(label(it.title), None, label(fmt(it.size), "sectionTitle"),
                                                     open_btn), label(it.detail, "faint"), spacing=2))
            else:
                self.sudo_list.addLayout(vbox(
                    hbox(label(it.title), Pill("INFO", fmt(it.size)), None, spacing=8),
                    hbox(label(it.command, "code", wrap=True, select=True), copy_button(lambda c=it.command: c),
                         spacing=4),
                    spacing=4))
        self._update_selected()

    def _home_loaded(self, rows):
        clear_layout(self.home_list)
        top = rows[0][0] if rows else 1
        for size, path in rows:
            bar = UsageBar(height=6, color="pink")
            bar.set(size * 100 / top)
            self.home_list.addLayout(vbox(hbox(label(path.replace(str(HOME), "~")),
                                               None, label(human(size), "faint")), bar, spacing=4))

    def _selected(self) -> list[str]:
        return [k for k, cb in self.boxes.items() if cb.isChecked()]

    def _update_selected(self):
        keys = set(self._selected())
        total = sum(max(0, it.size) for it in self.items if it.key in keys)
        self.selected_lbl.setText(f"{human(total)} selected to reclaim")
        self.clean_btn.setEnabled(bool(keys))

    def clean_selected(self, keys: list[str] | None = None, confirm: bool = True):
        keys = keys if keys is not None else self._selected()
        if not keys:
            return
        names = ", ".join(it.title for it in self.items if it.key in keys) or ", ".join(keys)
        if confirm and QMessageBox.question(self, "Clean", f"Clear: {names}?") != QMessageBox.StandardButton.Yes:
            return
        self.clean_btn.setEnabled(False)
        self.clean_btn.setText("Cleaning…")
        run_async(cleanup.apply, keys, on_done=self._cleaned)

    def _cleaned(self, log):
        self.clean_btn.setText("Clean selected")
        self.log_lbl.setText("\n".join(f"✓ {line}" for line in log))
        self.state.notice.emit("Cleanup done", log[-1], "OK")
        self._update_disk()
        self._update_mem()
        self.scan()
