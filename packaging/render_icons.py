"""Render assets/laptop-doctor.svg to the PNG sizes the desktop and notifications use."""

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

REPO = Path(__file__).resolve().parent.parent


def render(svg: Path, size: int, out: Path):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(svg)).render(p, QRectF(0, 0, size, size))
    p.end()
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))


if __name__ == "__main__":
    app = QGuiApplication(["render", "-platform", "offscreen"])
    icons_root = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    svg = REPO / "assets/laptop-doctor.svg"
    render(svg, 256, REPO / "docs/icon.png")
    if icons_root:
        for size in (16, 24, 32, 48, 64, 128, 256, 512):
            render(svg, size, icons_root / f"{size}x{size}/apps/laptop-doctor.png")
