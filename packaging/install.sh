#!/usr/bin/env bash
# Install (or update) Laptop Doctor for the current user. No root needed.
#   packaging/install.sh            app menu entry, desktop icon, start-in-tray at login, `laptop` on PATH
#   packaging/install.sh --remove   undo all of that (settings and reports are kept)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID=laptop-doctor
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"
ICONS="$DATA/icons/hicolor"
APPS="$DATA/applications"
AUTOSTART="$CONF/autostart/$APP_ID.desktop"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
LAUNCHER="$DESKTOP_DIR/Laptop Doctor.desktop"

say() { printf '\033[36m==>\033[0m %s\n' "$*"; }

if [ "$(id -u)" -eq 0 ]; then echo "Run as your normal user, not with sudo." >&2; exit 1; fi

if [ "${1:-}" = "--remove" ]; then
  pkill -f 'python -m laptop_doctor( gui)?$' 2>/dev/null || true
  rm -f "$APPS/$APP_ID.desktop" "$AUTOSTART" "$LAUNCHER" "$ICONS/scalable/apps/$APP_ID.svg"
  find "$ICONS" -name "$APP_ID.png" -delete 2>/dev/null || true
  update-desktop-database -q "$APPS" 2>/dev/null || true
  say "removed (settings in $CONF/laptop-doctor and reports/ kept; ~/.local/bin/laptop left in place)"
  exit 0
fi

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }

say "python environment"
(cd "$REPO" && uv sync --quiet)

if [ "${XDG_SESSION_TYPE:-}" != "wayland" ] && ! ldconfig -p | grep -q libxcb-cursor.so.0; then
  say "libxcb-cursor0 missing (Qt needs it on X11); fetching a private copy without root"
  echo "    (the system-wide fix is: sudo apt install libxcb-cursor0)"
  tmp=$(mktemp -d)
  (cd "$tmp" && apt download libxcb-cursor0 >/dev/null 2>&1 && dpkg-deb -x libxcb-cursor0_*.deb x) \
    && install -d "$REPO/.venv/extra-lib" \
    && cp -a "$tmp"/x/usr/lib/*/libxcb-cursor.so* "$REPO/.venv/extra-lib/" \
    || echo "    could not fetch it; run: sudo apt install libxcb-cursor0" >&2
  rm -rf "$tmp"
fi

say "icons"
"$REPO/.venv/bin/python" "$REPO/packaging/render_icons.py" "$ICONS"
install -Dm644 "$REPO/assets/$APP_ID.svg" "$ICONS/scalable/apps/$APP_ID.svg"
gtk-update-icon-cache -q -t -f "$ICONS" 2>/dev/null || true

say "app menu entry"
install -d "$APPS"
cat > "$APPS/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Laptop Doctor
GenericName=System Health Monitor
Comment=Health checks, live system monitor, cleanup and reports
Exec=$REPO/bin/laptop gui
Icon=$APP_ID
Terminal=false
Categories=System;Monitor;Utility;
Keywords=health;monitor;cpu;memory;gpu;disk;clean;crash;battery;
StartupWMClass=$APP_ID
StartupNotify=true
Actions=tray;

[Desktop Action tray]
Name=Start in tray only
Exec=$REPO/bin/laptop gui --background
DESKTOP
update-desktop-database -q "$APPS" 2>/dev/null || true

if [ -d "$DESKTOP_DIR" ]; then
  say "desktop icon in $DESKTOP_DIR"
  install -m 0755 "$APPS/$APP_ID.desktop" "$LAUNCHER"
  # GNOME's desktop icons only launch entries marked as trusted
  gio set "$LAUNCHER" metadata::trusted true 2>/dev/null || true
fi

say "start in the tray at login"
"$REPO/.venv/bin/python" -c "import sys; sys.path.insert(0, '$REPO'); from laptop_doctor.ui import autostart; autostart.set_enabled(True)"

say "laptop command"
install -d "$HOME/.local/bin"
ln -sfn "$REPO/bin/laptop" "$HOME/.local/bin/laptop"

if ! gnome-extensions list --enabled 2>/dev/null | grep -q appindicator; then
  echo "note: the tray icon needs the AppIndicator extension (Ubuntu ships it as ubuntu-appindicators@ubuntu.com)."
fi

say "done. Open 'Laptop Doctor' from the app grid, or run: laptop"
