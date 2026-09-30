"""Laptop Doctor desktop app: dashboard window plus a tray icon that keeps checking in the background."""

import os
import signal
import sys
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QMainWindow, QMenu, QPushButton,
                               QStackedWidget, QSystemTrayIcon, QWidget)

from .. import __version__, checks, cleanup, report
from . import icons, theme
from .pages.device import DevicePage
from .pages.health import HealthPage
from .pages.monitor import MonitorPage
from .pages.optimize import OptimizePage
from .pages.overview import OverviewPage
from .pages.reports import ReportsPage
from .pages.sections import crashes_page, updates_page
from .pages.settings import SettingsPage
from .state import State
from .widgets import Dot, hbox, label, run_async, vbox

APP_ID = "laptop-doctor"
SOCKET = f"{APP_ID}-{os.getuid()}"

NAV = [("overview", "Overview"), ("monitor", "Monitor"), ("health", "Health"), ("optimize", "Optimize"),
       ("crashes", "Crashes"), ("updates", "Updates"), ("device", "Device"), ("reports", "Reports"),
       ("settings", "Settings")]


class MainWindow(QMainWindow):
    def __init__(self, state: State, app: "DoctorApp"):
        super().__init__()
        self.state, self.app = state, app
        self.setWindowTitle("Laptop Doctor")
        self.setWindowIcon(icons.app_icon())
        self.resize(1440, 920)
        self.setMinimumSize(1100, 700)

        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {}
        overview = OverviewPage(state)
        overview.navigate.connect(self.go)
        overview.quick_clean.connect(self.quick_clean)
        settings = SettingsPage(state)
        settings.theme_changed.connect(app.set_theme)
        builders = {
            "overview": lambda: overview, "monitor": lambda: MonitorPage(state), "health": lambda: HealthPage(state),
            "optimize": lambda: OptimizePage(state), "crashes": crashes_page, "updates": updates_page,
            "device": lambda: DevicePage(state), "reports": lambda: ReportsPage(state), "settings": lambda: settings,
        }
        for key, _ in NAV:
            page = builders[key]()
            self.pages[key] = page
            self.stack.addWidget(page)

        root = QWidget()
        root.setObjectName("root")
        root.setLayout(hbox(self._sidebar(), self.stack, spacing=0))
        self.setCentralWidget(root)

        for i, (key, _) in enumerate(NAV[:9]):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda k=key: self.go(k))
        QShortcut(QKeySequence("Ctrl+R"), self, activated=state.run_checks)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=app.quit)

        state.checks_done.connect(self._side_status)
        if state.summary:
            self._side_status(state.summary)
            for key in ("overview", "health"):
                self.pages[key].on_summary(state.summary)

    def _sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(232)
        logo = label()
        logo.setPixmap(icons.app_icon().pixmap(36, 36))
        brand = vbox(label("Laptop Doctor", "brand"), label(f"v{__version__} · this machine", "brandSub"), spacing=0)
        lay = vbox(hbox(logo, brand, None, spacing=10), 18, spacing=4, margins=(16, 20, 16, 16))
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for i, (key, title) in enumerate(NAV):
            b = QPushButton(f"  {title}")
            b.setObjectName("navButton")
            b.setCheckable(True)
            b.setIcon(icons.nav_icon(key))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(f"Ctrl+{i + 1}")
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            self.nav.addButton(b)
            self.nav_buttons[key] = b
            lay.addWidget(b)
        lay.addStretch(1)

        card = QFrame()
        card.setObjectName("sideStatus")
        self.side_dot = Dot("INFO", 10)
        self.side_title = label("Checking…", "sectionTitle")
        self.side_sub = label("", "faint", wrap=True)
        card.setLayout(vbox(hbox(self.side_dot, self.side_title, None, spacing=8), self.side_sub,
                            spacing=4, margins=(14, 12, 14, 12)))
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mousePressEvent = lambda _e: self.go("health")
        lay.addWidget(card)
        side.setLayout(lay)
        self.nav_buttons["overview"].setChecked(True)
        return side

    def _side_status(self, s: checks.Summary):
        self.side_dot.set(s.status)
        self.side_title.setText(f"Health {s.score}")
        self.side_sub.setText(f"{s.fails} fail · {s.warns} warn\nchecked {time.strftime('%H:%M', time.localtime(s.when))}")

    def go(self, key: str):
        self.stack.setCurrentWidget(self.pages[key])
        self.nav_buttons[key].setChecked(True)

    def quick_clean(self):
        opt: OptimizePage = self.pages["optimize"]  # type: ignore[assignment]
        self.go("optimize")
        if opt.items:
            opt.clean_selected()

    def showEvent(self, e):
        self.state.set_foreground(True)
        super().showEvent(e)

    def hideEvent(self, e):
        self.state.set_foreground(False)
        super().hideEvent(e)

    def closeEvent(self, e):
        if self.state.settings["close_to_tray"] and QSystemTrayIcon.isSystemTrayAvailable() and not self.app.quitting:
            e.ignore()
            self.hide()
            if not self.app.told_about_tray:
                self.app.told_about_tray = True
                self.app.tray.showMessage("Laptop Doctor", "Still running in the tray. Quit from its menu.",
                                          icons.app_icon(), 4000)
        else:
            e.accept()
            self.app.quit()


class DoctorApp:
    def __init__(self, qapp: QApplication, background: bool):
        self.qapp = qapp
        self.quitting = False
        self.told_about_tray = False
        self.state = State()
        theme.current = theme.LIGHT if self.state.settings["theme"] == "light" else theme.DARK
        qapp.setStyleSheet(theme.stylesheet(theme.current))
        self.state.notice.connect(self.notify)
        self.state.checks_done.connect(self._tray_status)
        self.state.sampled.connect(self._tray_tooltip)

        self.tray = QSystemTrayIcon(icons.tray_icon("INFO"))
        self.tray.setToolTip("Laptop Doctor")
        self.tray.activated.connect(self._tray_click)
        self.tray.setContextMenu(self._tray_menu())
        self.tray.show()

        self.window = MainWindow(self.state, self)
        if not background or not QSystemTrayIcon.isSystemTrayAvailable():
            self.show()

        self.server = QLocalServer()
        QLocalServer.removeServer(SOCKET)
        self.server.listen(SOCKET)
        self.server.newConnection.connect(self._other_instance)

    # ---------------------------------------------------------------- tray
    def _tray_menu(self) -> QMenu:
        m = QMenu()
        self.m_status = QAction("Checking…")
        self.m_status.setEnabled(False)
        self.m_live = QAction("")
        self.m_live.setEnabled(False)
        m.addAction(self.m_status)
        m.addAction(self.m_live)
        m.addSeparator()
        m.addAction(icons.icon("overview", theme.current.text), "Open dashboard", self.show)
        m.addAction(icons.icon("monitor", theme.current.text), "System monitor", lambda: self.show("monitor"))
        m.addSeparator()
        m.addAction(icons.icon("play", theme.current.text), "Run health check now", self.state.run_checks)
        m.addAction(icons.icon("broom", theme.current.text), "Quick clean (safe caches)", self.quick_clean)
        m.addAction(icons.icon("file", theme.current.text), "Write today's report", self.write_report)
        m.addSeparator()
        m.addAction(icons.icon("power", theme.current.text), "Quit", self.quit)
        self._menu = m
        return m

    def _tray_click(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.window.isVisible() and self.window.isActiveWindow():
                self.window.hide()
            else:
                self.show()

    def _tray_status(self, s: checks.Summary):
        self.tray.setIcon(icons.tray_icon(s.status))
        self.m_status.setText(f"Health {s.score}  ·  {s.fails} fail, {s.warns} warn")

    def _tray_tooltip(self, s):
        text = f"CPU {s.cpu:.0f}%  ·  RAM {s.mem_pct:.0f}%  ·  " + (f"{s.cpu_temp:.0f}°C" if s.cpu_temp else "")
        self.m_live.setText(text)
        head = f"Laptop Doctor — health {self.state.summary.score}" if self.state.summary else "Laptop Doctor"
        self.tray.setToolTip(f"{head}\n{text}")

    def notify(self, title: str, body: str, status: str):
        if status == "OK" and self.window.isVisible():
            self.window.statusBar().showMessage(f"{title}: {body}", 6000)
            return
        if QSystemTrayIcon.supportsMessages():
            kind = {"FAIL": QSystemTrayIcon.MessageIcon.Critical,
                    "WARN": QSystemTrayIcon.MessageIcon.Warning}.get(status, QSystemTrayIcon.MessageIcon.Information)
            self.tray.showMessage(title, body, kind, 8000)
        else:
            report.notify(title, body, critical=status == "FAIL")

    # ---------------------------------------------------------------- actions
    def show(self, page: str | None = None):
        if page:
            self.window.go(page)
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def quick_clean(self):
        def job():
            items = cleanup.scan()
            return cleanup.apply([i.key for i in items if i.kind == cleanup.SAFE and i.size != 0])
        run_async(job, on_done=lambda log: self.notify("Quick clean done", log[-1], "INFO"))

    def write_report(self):
        run_async(report.write, self.state.summary, on_done=lambda p: self.notify("Report written", str(p), "INFO"))

    def set_theme(self, name: str):
        theme.current = theme.LIGHT if name == "light" else theme.DARK
        self.qapp.setStyleSheet(theme.stylesheet(theme.current))
        visible, page = self.window.isVisible(), self.window.stack.currentIndex()
        geo = self.window.saveGeometry()
        old = self.window
        self.window = MainWindow(self.state, self)
        self.window.restoreGeometry(geo)
        self.window.stack.setCurrentIndex(page)
        self.window.nav_buttons[NAV[page][0]].setChecked(True)
        self.tray.setContextMenu(self._tray_menu())
        old.hide()
        old.deleteLater()
        if visible:
            self.window.show()

    def _other_instance(self):
        conn = self.server.nextPendingConnection()
        conn.waitForReadyRead(500)
        msg = bytes(conn.readAll()).decode()
        conn.close()
        if msg != "background":
            self.show()

    def quit(self):
        self.quitting = True
        self.tray.hide()
        self.server.close()
        self.qapp.quit()


def _already_running(background: bool) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SOCKET)
    if sock.waitForConnected(300):
        sock.write(b"background" if background else b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def main(background: bool = False) -> int:
    QGuiApplication.setDesktopFileName(APP_ID)
    QApplication.setApplicationName("Laptop Doctor")
    QApplication.setApplicationVersion(__version__)
    qapp = QApplication(sys.argv[:1])
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setWindowIcon(icons.app_icon())
    if _already_running(background):
        return 0
    app = DoctorApp(qapp, background)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    keepalive = QTimer()           # lets Python handle Ctrl+C while Qt's loop runs
    keepalive.start(500)
    keepalive.timeout.connect(lambda: None)
    return qapp.exec()
