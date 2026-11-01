"""Health checks. Each returns a Check; none of them changes the system."""

import glob
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

import psutil

from . import cleanup
from .util import REPO, have, read, run, uptime_text, user_config

# thresholds
DISK_WARN, DISK_FAIL = 85, 93
SWAP_WARN_MB = 6000
TEMP_WARN = 90
BATTERY_WARN = 70
ERRORS_WARN = 200
APT_WARN = 30

OK, WARN, FAIL = "OK", "WARN", "FAIL"
RANK = {OK: 0, WARN: 1, FAIL: 2}


@dataclass
class Check:
    name: str
    status: str
    message: str
    fix: str = ""          # command or hint the user can act on
    title: str = ""        # human label for the dashboard

    def __post_init__(self):
        self.title = self.title or TITLES.get(self.name, self.name.title())

    def to_dict(self):
        return asdict(self)


TITLES = {
    "disk": "Disk space", "memory": "Memory & swap", "gpu": "NVIDIA GPU", "reboot": "Reboot",
    "units": "Systemd units", "errors": "Journal errors", "crashes": "Crashes",
    "backups": "Backups", "network": "Open ports", "battery": "Battery", "temps": "Temperature",
    "updates": "Updates",
}


def check_disk() -> Check:
    u = psutil.disk_usage("/")
    pct = round(u.percent)
    msg = f"/ {pct}% used, {u.free // 2**30}G free"
    if pct >= DISK_FAIL:
        return Check("disk", FAIL, msg, "laptop clean")
    if pct >= DISK_WARN:
        return Check("disk", WARN, msg, "laptop clean")
    return Check("disk", OK, msg)


def group_by_app(procs, n: int) -> list[tuple[int, str, int]]:
    """(rss, name) per process -> (total rss, name, process count) per app, largest first.
    Shared pages are counted once per process, so a many-process app like Chrome reads a little high."""
    total, count = Counter(), Counter()
    for rss, name in procs:
        total[name] += rss
        count[name] += 1
    return [(rss, name, count[name]) for name, rss in total.most_common(n)]


def top_memory(n: int = 3) -> list[tuple[int, str, int]]:
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        mi = p.info.get("memory_info")
        if mi:
            procs.append((mi.rss, p.info["name"] or "?"))
    return group_by_app(procs, n)


def app_label(name: str, count: int) -> str:
    return f"{name} x{count}" if count > 1 else name


def memory_fix(top) -> str:
    if cleanup.gradle_daemons():
        return "Optimize > stop idle Gradle/Kotlin daemons"
    if top:
        return f"close or restart {top[0][1]}, the largest user (Monitor page)"
    return ""


def check_memory() -> Check:
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    swap_mb = sw.used // 2**20
    apps = top_memory()
    top = ", ".join(f"{app_label(name, count)} {rss / 2**30:.1f}G" for rss, name, count in apps)
    msg = f"{vm.available // 2**20}M available, swap {swap_mb}M used; top: {top}"
    if swap_mb > SWAP_WARN_MB:
        return Check("memory", WARN, msg, memory_fix(apps))
    return Check("memory", OK, msg)


def gpu_query() -> tuple[str, dict]:
    """(error, fields). error is '' when nvidia-smi answered normally."""
    if not have("nvidia-smi"):
        return "nvidia-smi not found", {}
    keys = ["name", "driver_version", "temperature.gpu", "utilization.gpu", "memory.used",
            "memory.total", "power.draw", "clocks.gr", "pstate"]
    out = run(["nvidia-smi", f"--query-gpu={','.join(keys)}", "--format=csv,noheader,nounits"], timeout=8)
    if re.search(r"mismatch", out, re.I):
        return "driver/library mismatch: reboot needed before CUDA works", {}
    if re.search(r"failed|error", out, re.I) or not out:
        return out.splitlines()[0] if out else "no output", {}
    # A wedged GPU answers "[N/A]" for live fields; blank them so callers can float() safely.
    vals = ["" if "N/A" in v else v.strip() for v in out.splitlines()[0].split(",")]
    g = dict(zip(keys, vals))
    if not g.get("utilization.gpu") and not g.get("temperature.gpu"):
        return "GPU not responding (nvidia-smi reports N/A): reboot to recover", {}
    return "", g


def check_gpu() -> Check:
    err, g = gpu_query()
    if err == "nvidia-smi not found":
        return Check("gpu", WARN, err)
    if err:
        return Check("gpu", FAIL, err, "reboot" if "mismatch" in err else "")
    return Check("gpu", OK, f"{g['name']}, driver {g['driver_version']}, {g['temperature.gpu']}C")


def check_reboot() -> Check:
    flag = Path("/var/run/reboot-required")
    if flag.exists():
        pkgs = sorted(set(read("/var/run/reboot-required.pkgs").split()))[:5]
        since = time.strftime("%Y-%m-%d", time.localtime(flag.stat().st_mtime))
        return Check("reboot", WARN, f"pending since {since} for: {' '.join(pkgs)}", "reboot")
    return Check("reboot", OK, f"not required; up {uptime_text(time.time() - psutil.boot_time())}")


def check_units() -> Check:
    sys_units = run(["systemctl", "--failed", "--no-legend", "--plain"]).split("\n")
    usr_units = run(["systemctl", "--user", "--failed", "--no-legend", "--plain"]).split("\n")
    sys_f = [line.split()[0] for line in sys_units if line.strip()]
    usr_f = [line.split()[0] for line in usr_units if line.strip()
             and not re.match(r"vte-spawn-.*\.scope$", line.split()[0])]
    if not sys_f and not usr_f:
        return Check("units", OK, "no failed system or user units")
    if not usr_f and all(u.endswith(".mount") for u in sys_f):
        return Check("units", WARN, f"stale mount units: {' '.join(sys_f)}", "sudo systemctl reset-failed")
    msg = "failed: " + " ".join(sys_f) + (f" (user) {' '.join(usr_f)}" if usr_f else "")
    return Check("units", FAIL, msg.strip(), "systemctl --failed; journalctl -u <unit>")


def check_errors() -> Check:
    lines = run(["journalctl", "-p", "3", "-b", "--no-pager", "-q", "-o", "short"], timeout=30).splitlines()
    idents = Counter()
    for line in lines:
        parts = line.split()
        if len(parts) > 4:
            idents[re.sub(r"\[.*", "", parts[4]).rstrip(":")] += 1
    top = " ".join(f"{k}({v})" for k, v in idents.most_common(4)) or "none"
    kern = run(["journalctl", "-k", "-p", "3", "-b", "--no-pager", "-q"], timeout=30)
    usb = len(re.findall(r"error -71|unable to enumerate USB", kern))
    if usb > 10:
        top += f"; {usb} USB enumeration errors (bad cable/device or port)"
    msg = f"{len(lines)} error-level journal lines this boot; top: {top}"
    return Check("errors", WARN if len(lines) > ERRORS_WARN else OK, msg,
                 "Crashes page / journalctl -p 3 -b" if len(lines) > ERRORS_WARN else "")


@dataclass
class OomKill:
    when: str     # "Oct 26 16:04"
    name: str
    rss: int      # bytes the killed process held
    origin: str   # what started it: terminal, Chrome, a service, ...


_KILLED = re.compile(r"^(\w+ +\d+ \d+:\d+):\d+ .*Killed process (\d+) \((.*)\) total-vm:\d+kB, anon-rss:(\d+)kB")
_MEMCG = re.compile(r"task_memcg=(\S+?),task=.*,pid=(\d+),")


def _origin(memcg: str) -> str:
    if "Terminal" in memcg or "vte-spawn" in memcg:
        return "terminal"
    if "chrome" in memcg:
        return "Chrome"
    if "code" in memcg.lower():
        return "VS Code"
    if memcg.endswith(".service"):
        return memcg.rsplit("/", 1)[-1].removesuffix(".service")
    return "desktop app"


def oom_kills(kernel_log: str) -> list[OomKill]:
    """Kernel OOM-killer victims from journal text, newest first."""
    origins, kills = {}, []
    for line in kernel_log.splitlines():
        if m := _MEMCG.search(line):
            origins[m.group(2)] = _origin(m.group(1))
        elif m := _KILLED.search(line):
            when, pid, name, rss_kb = m.groups()
            kills.append(OomKill(" ".join(when.split()), name, int(rss_kb) * 1024, origins.get(pid, "unknown")))
    # a leap year, so Feb 29 parses; the journal line has no year of its own
    return sorted(kills, key=lambda k: time.strptime(f"2000 {k.when}", "%Y %b %d %H:%M"), reverse=True)


def oom_summary(kills: list[OomKill], n: int = 3) -> str:
    return ", ".join(f"{k.name} {k.rss / 2**30:.1f}G" for k in sorted(kills, key=lambda k: -k.rss)[:n])


def check_crashes() -> Check:
    week = time.time() - 7 * 86400
    crash_files = [f for f in glob.glob("/var/crash/*.crash") if os.path.getmtime(f) > week]
    # -k means the current boot only; _TRANSPORT=kernel spans every boot in the window.
    kern = run(["journalctl", "_TRANSPORT=kernel", "--since", "-7d", "--no-pager", "-q"], timeout=30)
    oomd = run(["journalctl", "-t", "systemd-oomd", "--since", "-7d", "--no-pager", "-q"], timeout=30)
    kills = oom_kills(kern)
    oom = len(kills) + len(re.findall(r"^\S+ \S+ \S+ \S+ systemd-oomd\[\d+\]: Killed ", oomd, re.M))
    last = run(["last", "-x"]).splitlines()
    unclean = max(0, sum(1 for line in last if line.startswith("reboot")
                         and ("still running" in line or "crash" in line)) - 1)
    msg = f"last 7d: {len(crash_files)} crash report(s), {oom} OOM kill(s); unclean boots in wtmp: {unclean}"
    if kills:
        msg += f"; biggest killed: {oom_summary(kills)}"
    if crash_files or oom:
        return Check("crashes", WARN, msg, "laptop crashes")
    return Check("crashes", OK, msg)


def check_backups(unit: str | None = None) -> Check:
    """Last result of the user's backup unit, named by `backup_unit` in config.json."""
    unit = unit or user_config().get("backup_unit")
    if not unit:
        return Check("backups", OK, "no backup unit configured (backup_unit in config.json)")
    unit = str(unit).removesuffix(".service")
    result = run(["systemctl", "--user", "show", f"{unit}.service", "-p", "Result", "--value"])
    last = run(["systemctl", "--user", "show", f"{unit}.service", "-p", "ExecMainExitTimestamp", "--value"])
    if not last:
        return Check("backups", WARN, f"{unit} has not run since login")
    if result != "success":
        return Check("backups", FAIL, f"{unit} last result: {result} ({last})",
                     f"journalctl --user -u {unit}")
    return Check("backups", OK, f"{unit} ok ({last})")


def known_ports() -> set[int]:
    ports = set()
    for line in read(REPO / "known-ports").splitlines():
        m = re.match(r"^(\d+)", line)
        if m:
            ports.add(int(m.group(1)))
    return ports


def exposed_ports() -> list[int]:
    ports = set()
    for line in run(["ss", "-Htln"]).splitlines():
        parts = line.split()
        if len(parts) >= 4:
            addr, _, port = parts[3].rpartition(":")
            if addr in ("0.0.0.0", "*", "[::]") and port.isdigit():
                ports.add(int(port))
    return sorted(ports - known_ports())


def check_network() -> Check:
    exposed = exposed_ports()
    if exposed:
        return Check("network", WARN, "listening on all interfaces, ports: " + " ".join(map(str, exposed)),
                     "add intended ones to known-ports")
    return Check("network", OK, "no services on 0.0.0.0")


def battery_info() -> dict:
    b = Path("/sys/class/power_supply/BAT0")
    kind = "charge" if (b / "charge_full").exists() else "energy"
    full, design = read(b / f"{kind}_full"), read(b / f"{kind}_full_design")
    if not full or not design:
        return {}
    return {
        "health": int(full) * 100 // int(design),
        "cycles": read(b / "cycle_count", "?"),
        "status": read(b / "status"),
        "capacity": int(read(b / "capacity", "0") or 0),
        "technology": read(b / "technology"),
        "manufactured": f"{read(b / 'manufacture_year')}-{read(b / 'manufacture_month').zfill(2)}",
        "full_wh": int(full) / 1e6 * (int(read(b / "voltage_min_design", "1000000")) / 1e6 if kind == "charge" else 1),
        "design_wh": int(design) / 1e6 * (int(read(b / "voltage_min_design", "1000000")) / 1e6 if kind == "charge" else 1),
    }


def check_battery() -> Check | None:
    bi = battery_info()
    if not bi:
        return None
    msg = f"health {bi['health']}%, {bi['cycles']} cycles ({bi['status']}, {bi['capacity']}% charge)"
    return Check("battery", WARN if bi["health"] < BATTERY_WARN else OK, msg)


def cpu_package_temp() -> float | None:
    temps = psutil.sensors_temperatures()
    for entry in temps.get("coretemp", []):
        if entry.label.startswith("Package"):
            return entry.current
    for entries in temps.values():
        if entries:
            return entries[0].current
    return None


def check_temps() -> Check | None:
    t = cpu_package_temp()
    if t is None:
        return None
    return Check("temps", WARN if t >= TEMP_WARN else OK, f"CPU package {t:.0f}C")


def pending_updates() -> tuple[int, int]:
    apt = run(["apt", "list", "--upgradable"], timeout=30).count("upgradable from")
    snap_out = run(["snap", "refresh", "--list"], timeout=30).splitlines()
    snap = max(0, len(snap_out) - 1) if snap_out and not snap_out[0].startswith("All snaps") else 0
    return apt, snap


def check_updates() -> Check:
    apt, snap = pending_updates()
    msg = f"apt {apt}, snap {snap} pending"
    if apt > APT_WARN:
        return Check("updates", WARN, msg, "sudo apt update && sudo apt full-upgrade")
    return Check("updates", OK, msg)


ALL = [check_disk, check_memory, check_gpu, check_reboot, check_units, check_errors,
       check_crashes, check_backups, check_network, check_battery, check_temps, check_updates]


@dataclass
class Summary:
    checks: list[Check] = field(default_factory=list)
    when: float = field(default_factory=time.time)

    @property
    def fails(self):
        return sum(c.status == FAIL for c in self.checks)

    @property
    def warns(self):
        return sum(c.status == WARN for c in self.checks)

    @property
    def status(self):
        return FAIL if self.fails else WARN if self.warns else OK

    @property
    def score(self) -> int:
        """0-100 health score: each warning costs 6 points, each failure 18."""
        return max(0, 100 - 6 * self.warns - 18 * self.fails)


def _safe(fn) -> Check | None:
    try:
        return fn()
    except Exception as e:  # a broken check must not hide the others
        return Check(fn.__name__.removeprefix("check_"), WARN, f"check failed: {e}")


def run_all(progress=None) -> Summary:
    """Run every check side by side (the updates check alone waits seconds on the network); keep ALL's order."""
    out = Summary()
    with ThreadPoolExecutor(max_workers=len(ALL)) as pool:
        futures = [pool.submit(_safe, fn) for fn in ALL]
        for done, _ in enumerate(as_completed(futures), 1):
            if progress:
                progress(done, len(ALL))
    out.checks = [c for c in (f.result() for f in futures) if c]
    return out
