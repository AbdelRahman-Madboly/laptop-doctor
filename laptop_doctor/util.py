"""Small helpers shared by the checks, the CLI and the dashboard."""

import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()
MACHINE_DOCS = HOME / "machine-notes"
REPORTS = REPO / "reports"
ICON = REPO / "assets/laptop-doctor.svg"
ICON_PNG = REPO / "docs/icon.png"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "laptop-doctor"


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(args, timeout: float = 20, input: str | None = None) -> str:
    """Run a command and return stdout+stderr as text. Never raises."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           input=input, shell=isinstance(args, str))
        return (p.stdout + p.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return f"error: {e}"


def read(path, default: str = "") -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def human(n: float, suffix: str = "B") -> str:
    for unit in ("", "K", "M", "G", "T"):
        if abs(n) < 1024 or unit == "T":
            return f"{n:.0f} {unit}{suffix}" if unit == "" else f"{n:.1f} {unit}{suffix}"
        n /= 1024
    return f"{n:.1f} P{suffix}"


def dir_size(path) -> int:
    """Bytes actually used on disk (sparse files count what they occupy). Missing paths are 0."""
    path = Path(path).expanduser()
    if not path.exists():
        return 0
    out = run(["du", "-s", "--block-size=1", str(path)], timeout=120)
    try:
        return int(out.split()[0])
    except (ValueError, IndexError):
        return 0


def uptime_text(seconds: float) -> str:
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    parts = [f"{d}d"] if d else []
    if h or d:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)
