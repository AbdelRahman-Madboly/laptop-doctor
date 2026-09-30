"""Shared app state: live samples, the latest health summary, and user settings."""

import json
import time

from PySide6.QtCore import QObject, QTimer, Signal

from .. import checks, report
from ..metrics import Sample, Sampler
from ..util import CONFIG_DIR
from .widgets import run_async

SETTINGS = CONFIG_DIR / "settings.json"
DEFAULTS = {
    "autostart": True,          # start hidden in the tray at login
    "interval_min": 30,         # background health check
    "notify": True,             # desktop notice when something turns WARN/FAIL
    "close_to_tray": True,
    "theme": "dark",
    "daily_report": True,       # write reports/YYYY-MM-DD.md on the first check of the day
}


def load_settings() -> dict:
    try:
        return {**DEFAULTS, **json.loads(SETTINGS.read_text())}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(s: dict):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s, indent=2))


class State(QObject):
    sampled = Signal(object)            # Sample
    checks_started = Signal()
    checks_progress = Signal(int, int)
    checks_done = Signal(object)        # checks.Summary
    checks_failed = Signal(str)
    notice = Signal(str, str, str)      # title, body, status  (tray shows it)

    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.sampler = Sampler()
        self.sample: Sample | None = None
        self.summary: checks.Summary | None = None
        self.running = False
        self._prev_status: dict[str, str] = {}
        self._last_report_day = time.strftime("%F") if report.list_reports() and \
            report.list_reports()[0].stem == time.strftime("%F") else ""

        self.tick = QTimer(self)
        self.tick.timeout.connect(self._sample)
        self.tick.start(1000)

        self.check_timer = QTimer(self)
        self.check_timer.timeout.connect(self.run_checks)
        self.apply_interval()
        QTimer.singleShot(1500, self.run_checks)

    # live sampling: 1 Hz while the window is open, every 5 s from the tray
    def set_foreground(self, visible: bool):
        self.tick.setInterval(1000 if visible else 5000)

    def _sample(self):
        self.sample = self.sampler.sample()
        self.sampled.emit(self.sample)

    def apply_interval(self):
        self.check_timer.start(max(5, int(self.settings["interval_min"])) * 60 * 1000)

    def update_settings(self, **kw):
        self.settings.update(kw)
        save_settings(self.settings)
        if "interval_min" in kw:
            self.apply_interval()

    def run_checks(self):
        if self.running:
            return
        self.running = True
        self.checks_started.emit()
        run_async(checks.run_all, on_done=self._checks_done, on_fail=self._checks_failed,
                  on_progress=lambda pr: self.checks_progress.emit(*pr), with_progress=True)

    def _checks_failed(self, err: str):
        self.running = False
        self.checks_failed.emit(err.splitlines()[-1])
        self.notice.emit("Health check failed", err.splitlines()[-1], "FAIL")

    def _checks_done(self, summary: checks.Summary):
        self.running = False
        self.summary = summary
        report.record(summary)
        today = time.strftime("%F")
        if self.settings["daily_report"] and self._last_report_day != today:
            self._last_report_day = today
            run_async(report.write, summary)
        # notify only on things that got worse since the previous run
        if self.settings["notify"]:
            worse = [c for c in summary.checks if c.status != checks.OK
                     and checks.RANK[c.status] > checks.RANK.get(self._prev_status.get(c.name, "OK"), 0)]
            if worse:
                body = "\n".join(f"{c.status} {c.title}: {c.message}" for c in worse[:5])
                self.notice.emit("Laptop Doctor", body, summary.status)
        self._prev_status = {c.name: c.status for c in summary.checks}
        self.checks_done.emit(summary)
