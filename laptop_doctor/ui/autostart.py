"""XDG autostart entry so the tray app starts hidden at login."""

import os
from pathlib import Path

from ..util import HOME, REPO

ENTRY = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "autostart/laptop-doctor.desktop"


def desktop_entry(background: bool) -> str:
    exe = REPO / "bin/laptop"
    return f"""[Desktop Entry]
Type=Application
Name=Laptop Doctor
GenericName=System Health Monitor
Comment=Health checks, live system monitor, cleanup and reports
Exec={exe} gui{' --background' if background else ''}
Icon=laptop-doctor
Terminal=false
Categories=System;Monitor;Utility;
Keywords=health;monitor;cpu;memory;gpu;disk;clean;crash;
StartupWMClass=laptop-doctor
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=20
"""


def enabled() -> bool:
    return ENTRY.exists()


def set_enabled(on: bool):
    if on:
        ENTRY.parent.mkdir(parents=True, exist_ok=True)
        ENTRY.write_text(desktop_entry(background=True))
    else:
        ENTRY.unlink(missing_ok=True)
