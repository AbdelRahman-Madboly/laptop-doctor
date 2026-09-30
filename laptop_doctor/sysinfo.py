"""Static facts about the machine for the Device page. Collected once, cheap to refresh."""

import os
import platform
import re
import socket
import time

import psutil

from .checks import battery_info, gpu_query
from .util import have, human, read, run, uptime_text


def _dmi(field: str) -> str:
    return read(f"/sys/class/dmi/id/{field}")


def _os_release() -> str:
    for line in read("/etc/os-release").splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip('"')
    return platform.system()


def _cpu_model() -> str:
    for line in read("/proc/cpuinfo").splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()
    return platform.processor()


def _gpus() -> list[str]:
    out = run(["lspci"], timeout=5)
    gpus = []
    for line in out.splitlines():
        if re.search(r"VGA|3D controller|Display controller", line):
            gpus.append(re.sub(r"^\S+\s+[^:]+:\s*", "", line))
    return gpus


def _disks() -> list[dict]:
    out = run(["lsblk", "-d", "-n", "-b", "-o", "NAME,MODEL,SIZE,TRAN,ROTA"], timeout=5)
    disks = []
    for line in out.splitlines():
        parts = line.split()
        if not parts or parts[0].startswith(("loop", "zram", "sr")):
            continue
        name, size = parts[0], next((p for p in parts if p.isdigit() and len(p) > 6), "0")
        model = " ".join(p for p in parts[1:] if p != size and p not in ("nvme", "sata", "usb", "0", "1"))
        tran = next((p for p in parts if p in ("nvme", "sata", "usb")), "")
        disks.append({"name": name, "model": model or "?", "size": human(int(size)), "bus": tran})
    return disks


def _partitions() -> list[dict]:
    parts = []
    for p in psutil.disk_partitions():
        if p.fstype in ("squashfs", "tmpfs", "overlay") or p.mountpoint.startswith(("/snap", "/var/snap")):
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        parts.append({"mount": p.mountpoint, "device": p.device, "fs": p.fstype,
                      "total": u.total, "used": u.used, "percent": u.percent})
    return parts


def _interfaces() -> list[dict]:
    stats = psutil.net_if_stats()
    out = []
    for name, addrs in psutil.net_if_addrs().items():
        if name == "lo" or name.startswith(("veth", "br-", "docker")):
            continue
        ipv4 = next((a.address for a in addrs if a.family == socket.AF_INET), "")
        mac = next((a.address for a in addrs if a.family == psutil.AF_LINK), "")
        st = stats.get(name)
        out.append({"name": name, "ipv4": ipv4, "mac": mac, "up": bool(st and st.isup),
                    "speed": st.speed if st else 0})
    return sorted(out, key=lambda i: (not i["up"], i["name"]))


def _display_server() -> str:
    session = os.environ.get("XDG_SESSION_TYPE", "?")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "?").replace("ubuntu:", "")
    return f"{desktop} on {session.title()}"


def collect() -> dict:
    freq = psutil.cpu_freq()
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    gpu_err, gpu = gpu_query()
    info: dict = {
        "System": {
            "Hostname": socket.gethostname(),
            "Model": f"{_dmi('sys_vendor')} {_dmi('product_name')}".strip(),
            "Board": _dmi("board_name"),
            "BIOS": f"{_dmi('bios_version')} ({_dmi('bios_date')})",
            "OS": _os_release(),
            "Kernel": platform.release(),
            "Desktop": _display_server(),
            "Uptime": uptime_text(time.time() - psutil.boot_time()),
            "Booted": time.strftime("%Y-%m-%d %H:%M", time.localtime(psutil.boot_time())),
        },
        "Processor": {
            "Model": _cpu_model(),
            "Cores": f"{psutil.cpu_count(logical=False)} physical, {psutil.cpu_count()} threads",
            "Max clock": f"{freq.max / 1000:.2f} GHz" if freq and freq.max else "?",
            "Architecture": platform.machine(),
            "Governor": read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", "?"),
            "Power profile": run(["powerprofilesctl", "get"], timeout=3) if have("powerprofilesctl") else "?",
        },
        "Memory": {
            "RAM": human(vm.total),
            "Swap": human(sw.total),
        },
        "Graphics": {f"GPU {i + 1}": g for i, g in enumerate(_gpus())},
    }
    if gpu:
        info["Graphics"]["NVIDIA driver"] = gpu["driver_version"]
        info["Graphics"]["VRAM"] = f"{int(gpu['memory.total'])} MiB"
    elif gpu_err:
        info["Graphics"]["NVIDIA driver"] = gpu_err
    bi = battery_info()
    if bi:
        info["Battery"] = {
            "Health": f"{bi['health']}%  ({bi['full_wh']:.1f} of {bi['design_wh']:.1f} Wh)",
            "Cycles": str(bi["cycles"]),
            "Status": f"{bi['status']}, {bi['capacity']}%",
            "Chemistry": bi["technology"],
            "Manufactured": bi["manufactured"],
        }
    info["_disks"] = _disks()
    info["_partitions"] = _partitions()
    info["_interfaces"] = _interfaces()
    return info
