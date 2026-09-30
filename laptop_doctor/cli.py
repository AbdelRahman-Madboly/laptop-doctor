"""Terminal interface. Same commands as the original bash `laptop` script."""

import os
import subprocess
import sys

import psutil

from . import checks, cleanup, report, triage
from .util import MACHINE_DOCS, human

USAGE = """laptop <command>

  (no command)    open the dashboard (same as 'laptop gui')
  gui [--background]  dashboard; --background starts hidden in the tray
  check           health summary (disk, memory, GPU, reboot, units, errors, crashes, backups, network, battery, temps)
  crashes [days]  crash and error triage for the last N days (default 7)
  clean           show what can be reclaimed; 'clean --apply' clears safe user-level caches only
  updates         list pending updates across apt, snap, flatpak, toolchains
  report          write check + crashes to reports/YYYY-MM-DD.md; '--notify' pops a desktop notice on problems
  snapshot        run the full software inventory scan (machine-notes/scan.sh)
"""


def tray_running() -> bool:
    """True when the dashboard/tray process is up (`laptop` or `laptop gui`)."""
    for p in psutil.process_iter(["cmdline", "pid"]):
        cmd = p.info.get("cmdline") or []
        if p.info["pid"] == os.getpid() or "laptop_doctor" not in cmd:
            continue
        rest = cmd[cmd.index("laptop_doctor") + 1:]
        if not rest or rest[0] == "gui":
            return True
    return False


def cmd_check() -> int:
    s = checks.run_all()
    print("\n".join(report.check_lines(s)))
    report.record(s)
    return 0


def cmd_crashes(days: int) -> int:
    print("\n".join(report.section_lines(triage.crashes(days))))
    return 0


def cmd_clean(apply: bool) -> int:
    items = cleanup.scan()
    fmt = lambda it: human(it.size) if it.size >= 0 else "?"  # noqa: E731
    groups = [(cleanup.SAFE, "User-level (safe; 'laptop clean --apply' clears these)"),
              (cleanup.REVIEW, "Review by hand (not cleared automatically)"),
              (cleanup.SUDO, "Needs sudo (run yourself with: ! <command>)")]
    for kind, title in groups:
        print(f"## {title}")
        for it in (i for i in items if i.kind == kind):
            if kind == cleanup.SUDO:
                print(f"  {it.command:<54} # {it.title} {fmt(it)}")
            else:
                print(f"  {it.title:<40} {fmt(it):>9}  {it.detail}")
        if kind == cleanup.REVIEW:
            print("  largest dirs in home:")
            for size, path in cleanup.largest_home_dirs(7):
                print(f"    {human(size):>9}  {path}")
        print()
    if apply:
        print("## Applying user-level cleanup")
        for line in cleanup.apply([i.key for i in items if i.kind == cleanup.SAFE]):
            print(f"  {line}")
    return 0


def cmd_updates() -> int:
    print("\n".join(report.section_lines(triage.updates())))
    return 0


def cmd_report(notify: bool) -> int:
    s = checks.run_all()
    path = report.write(s)
    print(f"wrote {path}")
    if notify and not tray_running():   # the tray app sends its own notices
        report.notify_problems(s)
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "gui"
    arg = argv[1] if len(argv) > 1 else ""
    if cmd == "gui":
        from .ui.app import main as gui_main
        return gui_main(background=arg == "--background")
    if cmd == "check":
        return cmd_check()
    if cmd == "crashes":
        return cmd_crashes(int(arg) if arg.isdigit() else 7)
    if cmd == "clean":
        return cmd_clean(arg == "--apply")
    if cmd == "updates":
        return cmd_updates()
    if cmd == "report":
        return cmd_report(arg == "--notify")
    if cmd == "snapshot":
        return subprocess.call(["bash", str(MACHINE_DOCS / "scan.sh")])
    print(USAGE)
    return 0 if cmd in ("-h", "--help", "help") else 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
