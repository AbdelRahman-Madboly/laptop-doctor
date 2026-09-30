"""Live samples for the monitor: CPU, memory, GPU, disk and network rates, temperatures."""

import time
from collections import deque
from dataclasses import dataclass, field

import psutil

from .checks import battery_info, cpu_package_temp, gpu_query

HISTORY = 120  # samples kept per series (2 minutes at 1 Hz)


@dataclass
class Sample:
    t: float
    cpu: float
    per_cpu: list[float]
    freq_mhz: float
    mem_pct: float
    mem_used: int
    mem_total: int
    swap_pct: float
    swap_used: int
    disk_pct: float
    disk_read: float      # bytes/s
    disk_write: float
    net_down: float       # bytes/s
    net_up: float
    cpu_temp: float | None
    load: tuple
    gpu: dict = field(default_factory=dict)
    gpu_error: str = ""
    battery: dict = field(default_factory=dict)
    on_ac: bool = True


class Sampler:
    """Call sample() once a second. Keeps a rolling history for sparklines."""

    def __init__(self):
        psutil.cpu_percent(percpu=True)
        self._disk = psutil.disk_io_counters()
        self._net = psutil.net_io_counters()
        self._t = time.monotonic()
        self._gpu_every = 0
        self._gpu_cache = ("", {})
        self.history: dict[str, deque] = {k: deque(maxlen=HISTORY) for k in
                                          ("cpu", "mem", "gpu", "down", "up", "read", "write", "temp")}
        self.last: Sample | None = None

    def sample(self) -> Sample:
        now = time.monotonic()
        dt = max(now - self._t, 1e-3)
        per = psutil.cpu_percent(percpu=True)
        disk, net = psutil.disk_io_counters(), psutil.net_io_counters()
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        freq = psutil.cpu_freq()
        # nvidia-smi costs ~50 ms; every 3 s is plenty for a dashboard.
        if self._gpu_every <= 0:
            self._gpu_cache = gpu_query()
            self._gpu_every = 3
        self._gpu_every -= 1
        gpu_err, gpu = self._gpu_cache
        ac = psutil.sensors_battery()
        s = Sample(
            t=time.time(), cpu=sum(per) / len(per), per_cpu=per,
            freq_mhz=freq.current if freq else 0,
            mem_pct=vm.percent, mem_used=vm.total - vm.available, mem_total=vm.total,
            swap_pct=sw.percent, swap_used=sw.used,
            disk_pct=psutil.disk_usage("/").percent,
            disk_read=(disk.read_bytes - self._disk.read_bytes) / dt if disk and self._disk else 0,
            disk_write=(disk.write_bytes - self._disk.write_bytes) / dt if disk and self._disk else 0,
            net_down=(net.bytes_recv - self._net.bytes_recv) / dt,
            net_up=(net.bytes_sent - self._net.bytes_sent) / dt,
            cpu_temp=cpu_package_temp(), load=psutil.getloadavg(),
            gpu=gpu, gpu_error=gpu_err, battery=battery_info(),
            on_ac=bool(ac.power_plugged) if ac else True,
        )
        self._disk, self._net, self._t = disk, net, now
        h = self.history
        h["cpu"].append(s.cpu)
        h["mem"].append(s.mem_pct)
        h["gpu"].append(float(gpu.get("utilization.gpu", 0) or 0) if gpu else 0)
        h["down"].append(s.net_down)
        h["up"].append(s.net_up)
        h["read"].append(s.disk_read)
        h["write"].append(s.disk_write)
        h["temp"].append(s.cpu_temp or 0)
        self.last = s
        return s


PROC_ATTRS = ["pid", "name", "username", "cpu_percent", "memory_info", "status", "cmdline", "create_time"]


def processes(limit: int = 200) -> list[dict]:
    """Top processes by CPU then memory. cpu_percent is relative to the previous call."""
    rows = []
    for p in psutil.process_iter(PROC_ATTRS):
        i = p.info
        mi = i.get("memory_info")
        rows.append({
            "pid": i["pid"], "name": i["name"] or "?", "user": i.get("username") or "?",
            "cpu": (i.get("cpu_percent") or 0) / (psutil.cpu_count() or 1),
            "rss": mi.rss if mi else 0, "status": i.get("status", ""),
            "cmd": " ".join(i.get("cmdline") or [])[:300],
        })
    rows.sort(key=lambda r: (r["cpu"], r["rss"]), reverse=True)
    return rows[:limit]
