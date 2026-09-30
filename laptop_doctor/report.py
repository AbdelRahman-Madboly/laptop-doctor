"""Daily Markdown reports in reports/YYYY-MM-DD.md (last 30 kept, not committed)."""

import json
import platform
import socket
import time
from pathlib import Path

from . import checks, triage
from .util import CONFIG_DIR, ICON_PNG, REPORTS, have, run

KEEP = 30
HISTORY = CONFIG_DIR / "history.jsonl"   # one line per check run, feeds the trend chart


def check_lines(summary: checks.Summary) -> list[str]:
    head = (f"laptop check  {time.strftime('%F %T', time.localtime(summary.when))}  "
            f"{socket.gethostname()}  kernel {platform.release()}")
    body = [f"{c.status:<5} {c.name:<10} {c.message}" + (f"  (fix: {c.fix})" if c.fix and c.status != "OK" else "")
            for c in summary.checks]
    return [head, *body, f"---- {summary.fails} fail, {summary.warns} warn  (score {summary.score})"]


def section_lines(sections) -> list[str]:
    out = []
    for title, lines in sections:
        out += [f"## {title}", *(lines or ["(none)"]), ""]
    return out


def record(summary: checks.Summary):
    """Append a compact row to the history log used by the dashboard's trend chart."""
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    row = {"t": int(summary.when), "score": summary.score, "status": summary.status,
           "checks": {c.name: c.status for c in summary.checks}}
    with HISTORY.open("a") as f:
        f.write(json.dumps(row) + "\n")
    lines = HISTORY.read_text().splitlines()
    if len(lines) > 2000:
        HISTORY.write_text("\n".join(lines[-2000:]) + "\n")


def history(limit: int = 400) -> list[dict]:
    try:
        rows = [json.loads(line) for line in HISTORY.read_text().splitlines()[-limit:]]
    except (OSError, ValueError):
        return []
    return rows


def write(summary: checks.Summary | None = None, days: int = 7) -> Path:
    summary = summary or checks.run_all()
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{time.strftime('%F')}.md"
    text = [f"# Laptop report {time.strftime('%F %T')}", "", "```", *check_lines(summary), "```", "",
            f"# Crash and error triage ({days} days)", "", "```", *section_lines(triage.crashes(days)), "```", ""]
    out.write_text("\n".join(text))
    for old in sorted(REPORTS.glob("*.md"))[:-KEEP]:
        old.unlink(missing_ok=True)
    record(summary)
    return out


def list_reports() -> list[Path]:
    return sorted(REPORTS.glob("*.md"), reverse=True) if REPORTS.is_dir() else []


def notify(title: str, body: str, critical: bool = False):
    if have("notify-send"):
        run(["notify-send", "-a", "Laptop Doctor", "-u", "critical" if critical else "normal",
             "-i", str(ICON_PNG), title, body])


def notify_problems(summary: checks.Summary):
    bad = [f"{c.status} {c.name}: {c.message}" for c in summary.checks if c.status != checks.OK][:6]
    if bad:
        notify("Laptop doctor", "\n".join(bad), critical=summary.fails > 0)
