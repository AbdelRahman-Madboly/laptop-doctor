"""Reclaimable space. 'safe' items can be cleared from the app; the rest are shown for review.

Root-level cleanups are printed as commands, never run.
"""

import json
import re
import shutil
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import psutil

from .util import HOME, dir_size, have, human, run

SAFE, REVIEW, SUDO = "safe", "review", "sudo"


@dataclass
class Item:
    key: str
    title: str
    kind: str                 # SAFE, REVIEW or SUDO
    size: int = 0             # bytes; -1 when unknown
    detail: str = ""
    command: str = ""         # for SUDO items: what to run yourself
    path: str = ""            # for REVIEW items: what to open


GRADLE_RE = re.compile(r"GradleDaemon|KotlinCompileDaemon")


def gradle_daemons() -> list[psutil.Process]:
    out = []
    for p in psutil.process_iter(["name", "cmdline"]):
        cmd = " ".join(p.info.get("cmdline") or [])
        if (p.info.get("name") or "").startswith("java") and GRADLE_RE.search(cmd):
            out.append(p)
    return out


def _swap_of(p: psutil.Process) -> int:
    try:
        for line in Path(f"/proc/{p.pid}/status").read_text().splitlines():
            if line.startswith("VmSwap:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return 0


def stale_plugin_versions() -> list[Path]:
    """Editor assistant plugin cache dirs no longer referenced by installed_plugins.json."""
    home = HOME / ".assistant/plugins"
    try:
        data = json.loads((home / "installed_plugins.json").read_text())
        keep = {Path(e["installPath"]).resolve() for v in data["plugins"].values() for e in v}
    except (OSError, ValueError, KeyError):
        return []
    stale = []
    cache = home / "cache"
    if not cache.is_dir():
        return []
    for market in cache.iterdir():
        for plugin in (market.iterdir() if market.is_dir() else []):
            for version in (plugin.iterdir() if plugin.is_dir() else []):
                if version.is_dir() and version.resolve() not in keep:
                    stale.append(version)
    return stale


def _docker_reclaimable() -> str:
    if not have("docker"):
        return ""
    out = run(["docker", "system", "df", "--format", "{{.Type}} {{.Reclaimable}}"], timeout=20)
    return ", ".join(line for line in out.splitlines() if line.startswith(("Images", "Build")))


def scan(progress: Callable[[str], None] | None = None) -> list[Item]:
    def step(label):
        if progress:
            progress(label)

    items: list[Item] = []
    step("caches")
    items.append(Item("thumbnails", "Thumbnail cache", SAFE, dir_size("~/.cache/thumbnails"),
                      "~/.cache/thumbnails, rebuilt on demand"))
    items.append(Item("pip", "pip cache", SAFE, dir_size("~/.cache/pip"), "~/.cache/pip"))
    items.append(Item("npm", "npm cache", SAFE, dir_size("~/.npm/_cacache"), "~/.npm/_cacache"))
    daemons = gradle_daemons()
    items.append(Item("gradle", "Idle Gradle/Kotlin daemons", SAFE, sum(_swap_of(p) for p in daemons),
                      f"{len(daemons)} running; size is swap they hold, they restart on next build"))
    stale = stale_plugin_versions()
    items.append(Item("plugins", "Old Assistant plugin versions", SAFE, sum(dir_size(p) for p in stale),
                      f"{len(stale)} unreferenced version folder(s)"))
    dk = _docker_reclaimable()
    if dk:
        items.append(Item("docker", "Docker dangling images + build cache", SAFE, -1, dk))

    step("large folders")
    for key, title, path in [
        ("trash", "Trash", "~/.local/share/Trash"),
        ("downloads", "Downloads", "~/Downloads"),
        ("huggingface", "HuggingFace models", "~/.cache/huggingface"),
        ("conda", "Conda packages (conda clean --all)", "~/miniconda3/pkgs"),
        ("local-llm", "Local model files", "~/.local-models"),
        ("transcripts", "Assistant session transcripts", "~/.assistant/projects"),
    ]:
        size = dir_size(path)
        if size:
            items.append(Item(key, title, REVIEW, size, path, path=str(Path(path).expanduser())))

    step("system")
    items.append(Item("apt", "APT package cache", SUDO, dir_size("/var/cache/apt/archives"),
                      "and unused packages", "sudo apt autoremove --purge && sudo apt clean"))
    jsize = run(["journalctl", "--disk-usage"])
    m = re.search(r"([\d.]+)([GM])", jsize)
    jbytes = int(float(m.group(1)) * (2**30 if m.group(2) == "G" else 2**20)) if m else -1
    items.append(Item("journal", "System journal", SUDO, jbytes, "keep 300M",
                      "sudo journalctl --vacuum-size=300M"))
    disabled = [line.split() for line in run(["snap", "list", "--all"]).splitlines() if "disabled" in line]
    if disabled:
        items.append(Item("snaps", "Old snap revisions", SUDO, -1, f"{len(disabled)} disabled revision(s)",
                          "snap list --all | awk '/disabled/{print $1, $3}' | "
                          "while read n r; do sudo snap remove \"$n\" --revision=\"$r\"; done"))
    return items


def largest_home_dirs(n: int = 8) -> list[tuple[int, str]]:
    out = run(["du", "-x", "--block-size=1", "--max-depth=1", str(HOME)], timeout=180)
    rows = []
    for line in out.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1] != str(HOME):
            rows.append((int(parts[0]), parts[1]))
    return sorted(rows, reverse=True)[:n]


def _clear_dir_contents(path: Path):
    if not path.is_dir():
        return
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def apply(keys: list[str]) -> list[str]:
    """Clear the chosen SAFE items. Returns one log line per action."""
    log = []
    if "gradle" in keys:
        daemons = gradle_daemons()
        for p in daemons:
            try:
                p.send_signal(signal.SIGTERM)
            except psutil.Error:
                pass
        log.append(f"stopped {len(daemons)} idle Gradle/Kotlin daemon(s)")
    if "thumbnails" in keys:
        _clear_dir_contents(HOME / ".cache/thumbnails")
        log.append("thumbnail cache cleared")
    if "pip" in keys:
        if have("pip"):
            run(["pip", "cache", "purge", "-q"], timeout=120)
        else:
            _clear_dir_contents(HOME / ".cache/pip")
        log.append("pip cache purged")
    if "npm" in keys and have("npm"):
        run(["npm", "cache", "clean", "--force"], timeout=120)
        log.append("npm cache cleaned")
    if "plugins" in keys:
        stale = stale_plugin_versions()
        for d in stale:
            shutil.rmtree(d, ignore_errors=True)
        log.append(f"removed {len(stale)} old plugin version(s)")
    if "docker" in keys and have("docker"):
        run(["docker", "image", "prune", "-f"], timeout=300)
        run(["docker", "builder", "prune", "-f"], timeout=300)
        log.append("docker dangling images and build cache pruned")
    u = psutil.disk_usage("/")
    log.append(f"disk now {u.percent:.0f}% used, {human(u.free)} free")
    return log
