"""Live system monitor: CPU, cores, memory, GPU, disk and network charts, and processes."""

import os
import signal

import psutil
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QGridLayout, QHeaderView, QLineEdit, QMessageBox, QTableView,
                               QWidget)

from ...metrics import processes
from ...util import human
from .. import theme
from ..widgets import (AreaChart, Card, CoreBars, PageHeader, Ring, button, hbox, label, rate, run_async,
                       scroll, short_rate, vbox)

COLUMNS = [("Process", "name"), ("PID", "pid"), ("User", "user"), ("CPU %", "cpu"), ("Memory", "rss"),
           ("Status", "status"), ("Command", "cmd")]


class ProcModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section][0].upper()
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        row = self.rows[index.row()]
        key = COLUMNS[index.column()][1]
        v = row[key]
        if role == Qt.ItemDataRole.DisplayRole:
            if key == "cpu":
                return f"{v:.1f}"
            if key == "rss":
                return human(v)
            return str(v)
        if role == Qt.ItemDataRole.UserRole:   # sort key
            return v
        if role == Qt.ItemDataRole.TextAlignmentRole and key in ("cpu", "rss", "pid"):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole and key == "cpu" and v >= 50:
            return theme.c("warn")
        if role == Qt.ItemDataRole.ToolTipRole and key == "cmd":
            return v
        return None


class MonitorPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        header = PageHeader("System monitor", "Live, sampled every second")

        # CPU
        cpu = Card("Processor")
        self.cpu_now = label("", "faint")
        cpu.header.addWidget(self.cpu_now)
        self.cpu_chart = AreaChart(height=150)
        self.cores = CoreBars(height=90)
        cpu.add(self.cpu_chart)
        cpu.add(label("PER THREAD", "kpiLabel"))
        cpu.add(self.cores)

        # memory
        mem = Card("Memory")
        self.mem_now = label("", "faint")
        mem.header.addWidget(self.mem_now)
        self.mem_ring = Ring(size=110, caption="RAM")
        self.swap_ring = Ring(size=110, caption="SWAP", warn=40, fail=70)
        self.mem_chart = AreaChart(height=110)
        mem.add(hbox(None, self.mem_ring, self.swap_ring, None, spacing=18))
        mem.add(self.mem_chart)

        # GPU
        gpu = Card("Graphics")
        self.gpu_name = label("", "faint")
        gpu.header.addWidget(self.gpu_name)
        self.gpu_ring = Ring(size=110, caption="LOAD", color="purple")
        self.vram_ring = Ring(size=110, caption="VRAM", color="blue")
        self.gpu_facts = label("", "muted", wrap=True)
        self.gpu_chart = AreaChart(height=110)
        gpu.add(hbox(None, self.gpu_ring, self.vram_ring, None, spacing=18))
        gpu.add(self.gpu_facts)
        gpu.add(self.gpu_chart)

        # disk + network
        disk = Card("Disk activity")
        self.disk_now = label("", "faint")
        disk.header.addWidget(self.disk_now)
        self.disk_chart = AreaChart(height=130, ymax=None, fmt=short_rate)
        disk.add(self.disk_chart)
        net = Card("Network")
        self.net_now = label("", "faint")
        net.header.addWidget(self.net_now)
        self.net_chart = AreaChart(height=130, ymax=None, fmt=short_rate)
        net.add(self.net_chart)
        temp = Card("Temperatures")
        self.temp_now = label("", "faint")
        temp.header.addWidget(self.temp_now)
        self.temp_chart = AreaChart(height=130, ymax=105, fmt=lambda v: f"{v:.0f}°")
        temp.add(self.temp_chart)

        # processes
        procs = Card("Processes")
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by name, user or command")
        self.filter.setClearButtonEnabled(True)
        self.filter.setFixedWidth(280)
        self.end_btn = button("End task", "x", tip="Send SIGTERM (asks the process to quit)")
        self.kill_btn = button("Force kill", "power", "danger", tip="Send SIGKILL")
        self.end_btn.clicked.connect(lambda: self._signal(signal.SIGTERM))
        self.kill_btn.clicked.connect(lambda: self._signal(signal.SIGKILL))
        procs.header.addWidget(self.filter)
        procs.header.addWidget(self.end_btn)
        procs.header.addWidget(self.kill_btn)
        self.model = ProcModel()
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.filter.textChanged.connect(self.proxy.setFilterFixedString)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setMinimumHeight(420)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(True)
        for col, w in enumerate((200, 70, 90, 70, 90, 80)):
            self.table.setColumnWidth(col, w)
        procs.add(self.table)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(cpu, 0, 0, 1, 2)
        grid.addWidget(mem, 0, 2)
        grid.addWidget(gpu, 0, 3)
        grid.addWidget(disk, 1, 0)
        grid.addWidget(net, 1, 1)
        grid.addWidget(temp, 1, 2, 1, 2)
        for col in range(4):
            grid.setColumnStretch(col, 1)

        body = QWidget()
        body.setLayout(vbox(header, grid, procs, spacing=14, margins=(28, 24, 28, 24)))
        self.setLayout(vbox(scroll(body)))

        self.proc_timer = QTimer(self)
        self.proc_timer.timeout.connect(self.refresh_procs)
        state.sampled.connect(self.on_sample)
        self._loading = False

    def showEvent(self, e):
        self.refresh_procs()
        self.proc_timer.start(2500)
        super().showEvent(e)

    def hideEvent(self, e):
        self.proc_timer.stop()
        super().hideEvent(e)

    def refresh_procs(self):
        if self._loading:
            return
        self._loading = True
        run_async(processes, on_done=self._procs_loaded)

    def _procs_loaded(self, rows):
        self._loading = False
        sel = self._selected_pid()
        self.model.set_rows(rows)
        if sel is not None:
            for r in range(self.proxy.rowCount()):
                if self.proxy.index(r, 1).data(Qt.ItemDataRole.UserRole) == sel:
                    self.table.selectRow(r)
                    break

    def _selected_pid(self):
        idx = self.table.selectionModel().selectedRows(1) if self.table.selectionModel() else []
        return idx[0].data(Qt.ItemDataRole.UserRole) if idx else None

    def _signal(self, sig):
        pid = self._selected_pid()
        if pid is None:
            return
        try:
            name = psutil.Process(pid).name()
        except psutil.Error:
            return
        verb = "Force kill" if sig == signal.SIGKILL else "End"
        if QMessageBox.question(self, verb, f"{verb} {name} (PID {pid})?") != QMessageBox.StandardButton.Yes:
            return
        try:
            os.kill(pid, sig)
        except OSError as e:
            QMessageBox.warning(self, verb, f"Could not signal {name}: {e.strerror}")
        self.refresh_procs()

    def on_sample(self, s):
        if not self.isVisible():
            return
        h = self.state.sampler.history
        self.cpu_chart.set_series([(h["cpu"], "accent")])
        self.cores.set(s.per_cpu)
        self.cpu_now.setText(f"{s.cpu:.0f}%  ·  {s.freq_mhz / 1000:.2f} GHz  ·  load {s.load[0]:.2f} "
                             f"{s.load[1]:.2f} {s.load[2]:.2f}")
        self.mem_ring.set(s.mem_pct)
        self.swap_ring.set(s.swap_pct)
        self.mem_chart.set_series([(h["mem"], "blue")])
        self.mem_now.setText(f"{human(s.mem_used)} / {human(s.mem_total)}  ·  swap {human(s.swap_used)}")
        g = s.gpu
        if g:
            used, total = float(g.get("memory.used") or 0), float(g.get("memory.total") or 1)
            self.gpu_ring.set(float(g.get("utilization.gpu") or 0))
            self.vram_ring.set(used * 100 / total)
            self.gpu_name.setText(g.get("name", ""))
            self.gpu_facts.setText(f"{g.get('temperature.gpu')}°C  ·  {g.get('power.draw')} W  ·  "
                                   f"{g.get('clocks.gr')} MHz  ·  {g.get('pstate')}  ·  "
                                   f"{used:.0f} / {total:.0f} MiB")
        else:
            self.gpu_ring.set(0, "--")
            self.vram_ring.set(0, "--")
            self.gpu_facts.setText(s.gpu_error or "No NVIDIA data")
        self.gpu_chart.set_series([(h["gpu"], "purple")])
        self.disk_chart.set_series([(h["read"], "blue"), (h["write"], "pink")])
        self.disk_now.setText(f"read {rate(s.disk_read)}  ·  write {rate(s.disk_write)}")
        self.net_chart.set_series([(h["down"], "accent"), (h["up"], "purple")])
        self.net_now.setText(f"▼ {rate(s.net_down)}  ·  ▲ {rate(s.net_up)}")
        self.temp_chart.set_series([(h["temp"], "warn")])
        gt = f"  ·  GPU {g.get('temperature.gpu')}°C" if g else ""
        self.temp_now.setText(f"CPU {s.cpu_temp:.0f}°C{gt}" if s.cpu_temp else "no sensor")
