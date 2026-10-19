"""Crash triage and update listing. Both return sections: (title, [lines])."""

import glob
import os
import re
import time
from pathlib import Path

from .util import HOME, have, read, run

Section = tuple[str, list[str]]


def _tail(lines: list[str], n: int) -> list[str]:
    return lines[-n:] if len(lines) > n else lines


def crashes(days: int = 7) -> list[Section]:
    since = f"-{days}d"
    out: list[Section] = []

    boots = [line for line in run(["last", "-x", "-n", "20"]).splitlines()
             if line.startswith(("reboot", "shutdown"))][:10]
    out.append(("Boots (last 10; a reboot line with 'crash' or a gap without shutdown means an unclean stop)",
                boots))

    cutoff = time.time() - days * 86400
    files = sorted(((os.path.getmtime(f), f) for f in glob.glob("/var/crash/*.crash")
                    if os.path.getmtime(f) > cutoff), reverse=True)
    out.append((f"Crash reports in /var/crash (last {days}d)",
                [f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(t))}  {Path(f).name}" for t, f in files]))

    # -k means the current boot only; _TRANSPORT=kernel spans every boot in the window.
    kern = run(["journalctl", "_TRANSPORT=kernel", "--since", since, "--no-pager", "-q", "-o", "short"], timeout=60)
    pat = re.compile(r"out of memory|oom-kill|NVRM: Xid|hung_task|soft lockup|BUG:|Oops|segfault|"
                     r"I/O error|nvme.*(timeout|reset)", re.I)
    out.append((f"Kernel: errors, OOM, GPU Xid, hung tasks, soft lockups (last {days}d)",
                _tail([line for line in kern.splitlines() if pat.search(line)], 25)))

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
                            "(watch nvidia-* and linux-* lines: check driver and kernel notes first)"]))
    out.append(("snap", run(["snap", "refresh", "--list"], timeout=30).splitlines()))
    if have("flatpak"):
        out.append(("flatpak", run(["flatpak", "remote-ls", "--updates"], timeout=60).splitlines() or ["none"]))
    tools = [
        ("assistant", _ver(["assistant", "--version"]) + " (auto-updates)"),
        ("node", _ver(["node", "--version"]) + " via nvm"),
        ("fvm", _ver(["fvm", "--version"])),
        ("gh", _ver(["gh", "--version"])),
        ("docker", _ver(["docker", "--version"])),
        ("gitleaks", _ver([str(HOME / "bin/gitleaks"), "version"])),
        ("trivy", _ver([str(HOME / "bin/trivy"), "--version"])),
        ("local-llm", _ver(["local-llm", "--version"], line=-1)),
    ]
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
