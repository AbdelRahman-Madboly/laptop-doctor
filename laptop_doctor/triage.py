"""Crash triage and update listing. Both return sections: (title, [lines])."""

import glob
import os
import re
import time
from pathlib import Path

from .checks import oom_kills
from .util import HOME, have, human, read, run, user_config

Section = tuple[str, list[str]]


def _tail(lines: list[str], n: int) -> list[str]:
    return lines[-n:] if len(lines) > n else lines


KERNEL_PROBLEM = re.compile(r"out of memory|NVRM: Xid|hung_task|soft lockup|BUG:|\bOops\b|segfault|"
                            r"I/O error|nvme.*(timeout|reset)", re.I)
# OOM kills get their own section; these are the noisy lines around each one (the process table dump)
OOM_NOISE = re.compile(r"Out of memory: Killed process|invoked oom-killer|oom-kill:|^\S+ +\d+ \S+ \S+ kernel: \[ *\d+\]")


def boots(n: int = 10) -> list[str]:
    # name the record types: without them the newest 20 lines are usually terminal logins
    return [line for line in run(["last", "-x", "-n", str(n), "reboot", "shutdown"]).splitlines()
            if line.startswith(("reboot", "shutdown"))]


def kernel_problems(kernel_log: str) -> list[str]:
    return [line for line in kernel_log.splitlines() if KERNEL_PROBLEM.search(line) and not OOM_NOISE.search(line)]


def crashes(days: int = 7) -> list[Section]:
    since = f"-{days}d"
    out: list[Section] = []

    out.append(("Boots (last 10; a reboot line with 'crash' or a gap without shutdown means an unclean stop)",
                boots()))

    cutoff = time.time() - days * 86400
    files = sorted(((os.path.getmtime(f), f) for f in glob.glob("/var/crash/*.crash")
                    if os.path.getmtime(f) > cutoff), reverse=True)
    out.append((f"Crash reports in /var/crash (last {days}d)",
                [f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(t))}  {Path(f).name}" for t, f in files]))

    # -k means the current boot only; _TRANSPORT=kernel spans every boot in the window.
    kern = run(["journalctl", "_TRANSPORT=kernel", "--since", since, "--no-pager", "-q", "-o", "short"], timeout=60)
    out.append((f"Out-of-memory kills (last {days}d; newest first, size is what the process held)",
                [f"{k.when}  {k.name:<16} {human(k.rss):>9}  started from {k.origin}"
                 for k in oom_kills(kern)[:15]]))
    out.append((f"Kernel: errors, GPU Xid and memory failures, hung tasks, soft lockups (last {days}d)",
                _tail(kernel_problems(kern), 25)))

    prev = run(["journalctl", "-b", "-1", "-p", "3", "--no-pager", "-q", "-o", "short"], timeout=60)
    out.append(("Previous boot: last error-level lines (what happened before the last stop)",
                _tail(prev.splitlines(), 15)))

    allj = run(["journalctl", "--since", since, "--no-pager", "-q", "-o", "short"], timeout=90)
    seg = re.compile(r"segfault|core dumped|dumped core", re.I)
    out.append((f"Application segfaults and core dumps (last {days}d)",
                _tail([line for line in allj.splitlines() if seg.search(line)], 15)))

    try:
        pstore = [p.name for p in Path("/sys/fs/pstore").iterdir()]
    except OSError:
        pstore = ["not readable"]
    out.append(("pstore (kernel panic dumps kept across reboot)", pstore))

    usr = run(["journalctl", "--user", "--since", since, "--no-pager", "-q", "-o", "short"], timeout=60)
    out.append(("User services that failed recently",
                _tail([line for line in usr.splitlines() if re.search(r"Failed with result|failed", line)], 10)))
    return out


def _ver(args, line=0) -> str:
    out = run(args, timeout=10).splitlines()
    if not out or out[0].startswith("error:"):
        return "not installed"
    return out[line] if line < len(out) else out[-1]


def updates() -> list[Section]:
    out: list[Section] = []
    apt = [line.split("/")[0] for line in run(["apt", "list", "--upgradable"], timeout=30).splitlines()
           if "upgradable" in line]
    stamp = Path("/var/lib/apt/periodic/update-success-stamp")
    cache = time.strftime("%Y-%m-%d", time.localtime(stamp.stat().st_mtime)) if stamp.exists() else "unknown"
    out.append((f"apt ({len(apt)} pending; cache as of {cache})",
                apt[:60] + ["apply: sudo apt update && sudo apt full-upgrade   "
                            "(watch nvidia-* and linux-* lines: driver and kernel updates)"]))
    out.append(("snap", run(["snap", "refresh", "--list"], timeout=30).splitlines()))
    if have("flatpak"):
        out.append(("flatpak", run(["flatpak", "remote-ls", "--updates"], timeout=60).splitlines() or ["none"]))
    tools = [
        ("node", _ver(["node", "--version"]) + " via nvm"),
        ("fvm", _ver(["fvm", "--version"])),
        ("gh", _ver(["gh", "--version"])),
        ("docker", _ver(["docker", "--version"])),
        ("gitleaks", _ver([str(HOME / "bin/gitleaks"), "version"])),
        ("trivy", _ver([str(HOME / "bin/trivy"), "--version"])),
    ]
    # extra tools from config.json: [name, command, args...]
    for entry in user_config().get("toolchain_versions") or []:
        if isinstance(entry, list) and len(entry) >= 2:
            tools.append((str(entry[0]), _ver([str(a) for a in entry[1:]])))
    out.append(("Toolchains", [f"{name:<10} {v}" for name, v in tools]))
    npm = run(["npm", "outdated", "-g", "--depth=0"], timeout=60) if have("npm") else ""
    out.append(("npm globals outdated", npm.splitlines() or ["none"]))
    return out


def reboot_pending() -> bool:
    return Path("/var/run/reboot-required").exists()


def os_version() -> str:
    for line in read("/etc/os-release").splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip('"')
    return ""
