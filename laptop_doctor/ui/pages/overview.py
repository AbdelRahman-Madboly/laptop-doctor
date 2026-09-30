"""Overview: health score, live KPIs, what needs attention, quick actions."""

import socket
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QWidget

from ... import checks, report
from ...util import human
from .. import icons, theme
from ..widgets import (AreaChart, Card, Dot, PageHeader, Pill, Ring, ScoreTrend, Sparkline, button,
                       clear_layout, copy_button, hbox, label, rate, scroll, short_rate, vbox)


class Kpi(Card):
    def __init__(self, title: str, icon: str, color_token: str = "accent", ymax: float | None = 100):
        super().__init__(padding=16, spacing=6)
        ic = label()
        ic.setPixmap(icons.pixmap(icon, theme.current.muted, 16))
        self.value = label("--", "kpiValue")
        self.detail = label("", "faint")
        self.spark = Sparkline(ymax=ymax)
        self.token = color_token
        self.add(hbox(ic, label(title.upper(), "kpiLabel"), None, spacing=6))
        self.add(self.value)
        self.add(self.detail)
        self.add(self.spark)

    def set(self, value: str, detail: str, series=None):
        self.value.setText(value)
        self.detail.setText(detail)
        if series is not None:
            self.spark.set_series([(series, self.token)])


class OverviewPage(QWidget):
    navigate = Signal(str)
    quick_clean = Signal()

    def __init__(self, state):
        super().__init__()
        self.state = state
        header = PageHeader(self._greeting(), self._machine())
        self.header = header
        self.run_btn = header.add_action(button("Run health check", "play", "primary"))
        self.run_btn.clicked.connect(state.run_checks)

        # hero: score ring + status text + attention list
        self.score = Ring(size=150, thickness=12, center_font=26, caption="HEALTH")
        self.score.set(0, "--")
        self.status_title = label("Checking…", "pageTitle")
        self.status_sub = label("", "muted", wrap=True)
        self.counts = hbox(spacing=6)
        self.last_run = label("", "faint")
        clean_btn = button("Quick clean", "broom", tip="Clear safe user caches")
        clean_btn.clicked.connect(self.quick_clean.emit)
        report_btn = button("Write report", "file")
        report_btn.clicked.connect(self._write_report)
        details_btn = button("All checks", "health")
        details_btn.clicked.connect(lambda: self.navigate.emit("health"))
        hero = Card(padding=22)
        hero.add(hbox(self.score,
                      vbox(self.status_title, self.status_sub, self.counts, 10,
                           hbox(details_btn, clean_btn, report_btn, None, spacing=8), self.last_run, None, spacing=6),
                      spacing=24))
        hero.add(None)

        self.attention = Card("Needs attention")
        self.attention_list = vbox(spacing=8)
        self.attention.add(self.attention_list)
        self.attention.add(None)

        # KPI row
        self.k_cpu = Kpi("CPU", "cpu")
        self.k_mem = Kpi("Memory", "memory", "blue")
        self.k_gpu = Kpi("GPU", "gpu", "purple")
        self.k_temp = Kpi("CPU temp", "temp", "warn", ymax=105)
        self.k_disk = Kpi("Disk /", "disk", "pink")
        self.k_bat = Kpi("Battery", "battery", "ok")
        kpis = QGridLayout()
        kpis.setSpacing(12)
        for i, k in enumerate((self.k_cpu, self.k_mem, self.k_gpu, self.k_temp, self.k_disk, self.k_bat)):
            kpis.addWidget(k, 0, i)

        # charts row
        net = Card("Network")
        self.net_legend = label("", "faint")
        net.header.addWidget(self.net_legend)
        self.net_chart = AreaChart(height=150, ymax=None, fmt=short_rate)
        net.add(self.net_chart)
        trend = Card("Health score trend")
        self.trend = ScoreTrend(height=150)
        trend.add(self.trend)

        top = QGridLayout()
        top.setSpacing(12)
        top.addWidget(hero, 0, 0)
        top.addWidget(self.attention, 0, 1)
        top.setColumnStretch(0, 3)
        top.setColumnStretch(1, 2)
        bottom = QGridLayout()
        bottom.setSpacing(12)
        bottom.addWidget(net, 0, 0)
        bottom.addWidget(trend, 0, 1)
        bottom.setColumnStretch(0, 3)
        bottom.setColumnStretch(1, 2)

        body = QWidget()
        body.setLayout(vbox(header, top, kpis, bottom, None, spacing=14, margins=(28, 24, 28, 24)))
        self.setLayout(vbox(scroll(body)))

        state.sampled.connect(self.on_sample)
        state.checks_started.connect(self.on_started)
        state.checks_done.connect(self.on_summary)
        state.checks_failed.connect(self.on_failed)
        self.trend.set(report.history())

    def _greeting(self):
        h = time.localtime().tm_hour
        part = "Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening"
        return f"{part}"

    @staticmethod
    def _machine() -> str:
        from ...sysinfo import _dmi, _os_release
        return f"{_dmi('sys_vendor')} {_dmi('product_name')}  ·  {_os_release()}  ·  {socket.gethostname()}"

    def _write_report(self):
        from ..widgets import run_async
        run_async(report.write, self.state.summary,
                  on_done=lambda p: self.state.notice.emit("Report written", str(p), "OK"))

    def on_started(self):
        self.run_btn.setEnabled(False)
        self.run_btn.setText("Checking…")

    def on_failed(self, err: str):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Run health check")
        self.status_title.setText("Check failed")
        self.status_sub.setText(err)

    def on_summary(self, s: checks.Summary):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Run health check")
        self.score.set(s.score, str(s.score))
        self.score.fixed = {"OK": "ok", "WARN": "warn", "FAIL": "fail"}[s.status]
        self.status_title.setText({"OK": "All systems healthy", "WARN": "Mostly healthy",
                                   "FAIL": "Needs your attention"}[s.status])
        bad = [c for c in s.checks if c.status != checks.OK]
        self.status_sub.setText(f"{len(s.checks) - len(bad)} of {len(s.checks)} checks passing on "
                                f"{socket.gethostname()}.")
        clear_layout(self.counts)
        for status, n in (("FAIL", s.fails), ("WARN", s.warns), ("OK", len(s.checks) - len(bad))):
            if n:
                self.counts.addWidget(Pill(status, f"{n} {status}"))
        self.counts.addStretch(1)
        self.last_run.setText(f"Last check {time.strftime('%H:%M', time.localtime(s.when))}  ·  "
                              f"every {self.state.settings['interval_min']} min in the background")
        clear_layout(self.attention_list)
        bad.sort(key=lambda c: -checks.RANK[c.status])
        if not bad:
            self.attention_list.addWidget(label("Nothing to fix right now.", "muted"))
        for c in bad[:4]:
            row = vbox(spacing=3)
            row.addLayout(hbox(Dot(c.status), label(c.title, "sectionTitle"), None, Pill(c.status), spacing=8))
            msg = label(c.message, "muted", wrap=True)
            row.addWidget(msg)
            if c.fix:
                code = label(c.fix, "code", select=True)
                row.addLayout(hbox(code, copy_button(lambda f=c.fix: f), None, spacing=4))
            self.attention_list.addLayout(row)
        if len(bad) > 4:
            more = button(f"{len(bad) - 4} more on the Health page", kind="ghost")
            more.clicked.connect(lambda: self.navigate.emit("health"))
            self.attention_list.addLayout(hbox(more, None))
        self.trend.set(report.history())

    def on_sample(self, s):
        h = self.state.sampler.history
        self.k_cpu.set(f"{s.cpu:.0f}%", f"{s.freq_mhz / 1000:.1f} GHz · load {s.load[0]:.1f}", h["cpu"])
        self.k_mem.set(f"{s.mem_pct:.0f}%", f"{human(s.mem_used)} of {human(s.mem_total)} · swap {human(s.swap_used)}",
                       h["mem"])
        if s.gpu:
            self.k_gpu.set(f"{s.gpu.get('utilization.gpu', '0')}%",
                           f"{s.gpu.get('temperature.gpu', '?')}°C · {s.gpu.get('memory.used', '?')} MiB", h["gpu"])
        else:
            self.k_gpu.set("n/a", s.gpu_error[:42] or "no NVIDIA data", h["gpu"])
        self.k_temp.set(f"{s.cpu_temp:.0f}°C" if s.cpu_temp else "n/a", "CPU package", h["temp"])
        self.k_disk.set(f"{s.disk_pct:.0f}%", f"R {rate(s.disk_read)} · W {rate(s.disk_write)}", h["write"])
        b = s.battery
        if b:
            self.k_bat.set(f"{b['capacity']}%", f"{b['status']} · health {b['health']}%")
        self.net_chart.set_series([(h["down"], "accent"), (h["up"], "purple")])
        self.net_legend.setText(f"<span style='color:{theme.current.accent}'>▼ {rate(s.net_down)}</span>"
                                f"&nbsp;&nbsp;<span style='color:{theme.current.purple}'>▲ {rate(s.net_up)}</span>")
        self.net_legend.setTextFormat(Qt.TextFormat.RichText)
