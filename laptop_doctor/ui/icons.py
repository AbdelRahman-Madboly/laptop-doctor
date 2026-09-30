"""Line icons (24px grid, stroke-based) tinted at runtime, plus the tray icon."""

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..util import ICON, REPO

TRAY = REPO / "assets/tray.svg"
from . import theme

PATHS = {
    "overview": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/>'
                '<rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "monitor": '<polyline points="3 12 7 12 10 4 14 20 17 12 21 12"/>',
    "health": '<path d="M12 21s-7.5-4.6-9.5-9.3C1 8 3.4 4.5 7 4.5c2.1 0 3.6 1.1 5 3 1.4-1.9 2.9-3 5-3 3.6 0 6 3.5 4.5 7.2C19.5 16.4 12 21 12 21z"/>',
    "optimize": '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/>',
    "crashes": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
               '<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "updates": '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><polyline points="21 3 21 9 15 9"/>',
    "device": '<rect x="3" y="4" width="18" height="12" rx="2"/><line x1="2" y1="20" x2="22" y2="20"/>',
    "reports": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
               '<polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1'
                'a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3'
                'l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0'
                ' 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3'
                'a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0'
                '-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "cpu": '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/>'
           '<path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
    "memory": '<rect x="2" y="7" width="20" height="10" rx="1.5"/><path d="M6 11v2M10 11v2M14 11v2M18 11v2M6 17v3M18 17v3"/>',
    "gpu": '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="9" cy="12" r="3"/><path d="M15 10h4M15 14h4"/>',
    "disk": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/><path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>',
    "temp": '<path d="M14 14.8V4a2 2 0 0 0-4 0v10.8a4 4 0 1 0 4 0z"/>',
    "battery": '<rect x="2" y="7" width="17" height="10" rx="2"/><line x1="22" y1="11" x2="22" y2="13"/>',
    "network": '<path d="M5 12.6a10 10 0 0 1 14 0"/><path d="M8.5 16a5 5 0 0 1 7 0"/><path d="M1.4 9a16 16 0 0 1 21.2 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>',
    "play": '<polygon points="6 4 20 12 6 20 6 4"/>',
    "broom": '<path d="M19 3 11 11"/><path d="M11 11c-3 0-6 2-7 6l3 1 1 3c4-1 6-4 6-7z"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "copy": '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "x": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "search": '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.6" y2="16.6"/>',
    "power": '<path d="M18.4 6.6a9 9 0 1 1-12.8 0"/><line x1="12" y1="2" x2="12" y2="12"/>',
}


def svg(name: str, color: str, stroke: float = 2) -> bytes:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>').encode()


def pixmap(name: str, color: str | QColor, size: int = 18, ratio: float = 2.0) -> QPixmap:
    if isinstance(color, QColor):
        color = color.name()
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    QSvgRenderer(QByteArray(svg(name, color))).render(p)
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str | QColor | None = None, size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color or theme.current.muted, size))


def nav_icon(name: str) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, theme.current.muted), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(pixmap(name, theme.current.accent), QIcon.Mode.Normal, QIcon.State.On)
    ic.addPixmap(pixmap(name, theme.current.text), QIcon.Mode.Active, QIcon.State.Off)
    return ic


def app_icon() -> QIcon:
    return QIcon(str(ICON))


def tray_icon(status: str) -> QIcon:
    """App glyph with a status dot: green OK, amber WARN, red FAIL, grey while unknown."""
    ic = QIcon()
    renderer = QSvgRenderer(str(TRAY))
    for size in (16, 22, 24, 32, 48, 64):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(p, QRectF(0, 0, size, size))
        r = size * 0.36
        dot = QRectF(size - r - 0.5, size - r - 0.5, r, r)
        color = QColor({"OK": "#3fb950", "WARN": "#e3a008", "FAIL": "#f85149"}.get(status, "#8b98a8"))
        p.setPen(QPen(QColor("#0b0f14"), max(1.0, size / 16)))
        p.setBrush(color)
        p.drawEllipse(dot)
        p.end()
        ic.addPixmap(pm)
    return ic
