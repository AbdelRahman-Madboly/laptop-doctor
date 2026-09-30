"""Settings: background behaviour, notifications, start at login, theme."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QSpinBox, QWidget

from ... import __version__
from ...util import CONFIG_DIR, REPO
from .. import autostart
from ..widgets import Card, PageHeader, hbox, label, vbox


class SettingsPage(QWidget):
    theme_changed = Signal(str)

    def __init__(self, state):
        super().__init__()
        self.state = state
        s = state.settings
        header = PageHeader("Settings", f"Saved to {CONFIG_DIR / 'settings.json'}")

        bg = Card("Background")
        self.autostart = QCheckBox("Start in the tray when I log in")
        self.autostart.setChecked(autostart.enabled())
        self.autostart.toggled.connect(self._autostart)
        self.close_tray = QCheckBox("Closing the window keeps Laptop Doctor running in the tray")
        self.close_tray.setChecked(s["close_to_tray"])
        self.close_tray.toggled.connect(lambda v: state.update_settings(close_to_tray=v))
        self.interval = QSpinBox()
        self.interval.setRange(5, 720)
        self.interval.setSuffix(" min")
        self.interval.setValue(s["interval_min"])
        self.interval.valueChanged.connect(lambda v: state.update_settings(interval_min=v))
        self.daily = QCheckBox("Write the daily Markdown report on the first check of each day")
        self.daily.setChecked(s["daily_report"])
        self.daily.toggled.connect(lambda v: state.update_settings(daily_report=v))
        bg.add(self.autostart)
        bg.add(self.close_tray)
        bg.add(hbox(label("Run health checks every"), self.interval, None, spacing=10))
        bg.add(self.daily)

        notes = Card("Notifications")
        self.notify = QCheckBox("Notify me when a check turns WARN or FAIL")
        self.notify.setChecked(s["notify"])
        self.notify.toggled.connect(lambda v: state.update_settings(notify=v))
        notes.add(self.notify)
        notes.add(label("Only changes for the worse notify, so a known warning doesn't nag every run.", "faint"))

        look = Card("Appearance")
        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.theme.setCurrentText(s["theme"])
        self.theme.currentTextChanged.connect(self._theme)
        look.add(hbox(label("Theme"), self.theme, None, spacing=10))

        about = Card("About")
        about.add(label(f"Laptop Doctor {__version__}", "sectionTitle"))
        about.add(label(f"Source: {REPO}", "muted", select=True))
        about.add(label("Terminal: laptop check | crashes | clean | updates | report", "faint", select=True))

        self.setLayout(vbox(header, bg, notes, look, about, None, spacing=14, margins=(28, 24, 28, 24)))

    def _autostart(self, on: bool):
        autostart.set_enabled(on)
        self.state.update_settings(autostart=on)

    def _theme(self, name: str):
        self.state.update_settings(theme=name)
        self.theme_changed.emit(name)
