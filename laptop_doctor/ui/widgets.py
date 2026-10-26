"""Building blocks: cards, pills, gauges, charts, and a background task runner."""

import traceback
from typing import Callable, Sequence

from PySide6.QtCore import QObject, QPointF, QRectF, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QLayout, QPushButton, QScrollArea,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from . import icons, theme


# ---------------------------------------------------------------- background work
class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(object)


class Task(QRunnable):
    """Run fn(*args) on the thread pool. If fn accepts `progress`, it gets a callback."""

    _alive: set = set()   # keep Python wrappers alive until the signal fires

    def __init__(self, fn: Callable, *args, on_done=None, on_fail=None, on_progress=None, with_progress=False):
        super().__init__()
        self.fn, self.args, self.with_progress = fn, args, with_progress
        self.signals = _Signals()
        if on_done:
            self.signals.done.connect(on_done)
        if on_fail:
            self.signals.failed.connect(on_fail)
        if on_progress:
            self.signals.progress.connect(on_progress)
        # Released on the GUI thread once the last signal has been delivered. Dropping the last reference in
        # run() freed the signals object on the worker thread with its queued signal still pending, which
        # crashed the app inside Qt (segfaults on 2026-10-21 and 2026-10-23).
        self.signals.done.connect(self._release)
        self.signals.failed.connect(self._release)
        self.setAutoDelete(False)   # Python owns it; the pool must not delete it from the worker thread

    def _release(self, _=None):
        Task._alive.discard(self)

    def run(self):
        try:
            kwargs = {"progress": lambda *a: self.signals.progress.emit(a)} if self.with_progress else {}
            result = self.fn(*self.args, **kwargs)
        except Exception:
            self._emit(self.signals.failed, traceback.format_exc(limit=3))
        else:
            self._emit(self.signals.done, result)

    @staticmethod
    def _emit(sig, value):
        try:
            sig.emit(value)
        except RuntimeError:   # receiver went away (window rebuilt or app quitting)
            pass


def run_async(fn, *args, **kw) -> Task:
    t = Task(fn, *args, **kw)
    Task._alive.add(t)
    QThreadPool.globalInstance().start(t)
    return t


# ---------------------------------------------------------------- layout helpers
def vbox(*widgets, spacing=12, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        _add(lay, w)
    return lay


def hbox(*widgets, spacing=12, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        _add(lay, w)
    return lay


def _add(lay, w):
    if w is None:
        lay.addStretch(1)
    elif isinstance(w, int):
        lay.addSpacing(w)
    elif isinstance(w, QLayout):
        lay.addLayout(w)
    else:
        lay.addWidget(w)


def label(text: str = "", name: str | None = None, wrap=False, select=False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    if select:
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lab


def button(text: str, icon: str | None = None, kind: str | None = None, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if icon:
        color = theme.current.accent_text if kind == "primary" else theme.current.text
        b.setIcon(icons.icon(icon, color, 16))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if tip:
        b.setToolTip(tip)
    return b


def copy_button(text_fn: Callable[[], str], tip="Copy command") -> QToolButton:
    b = QToolButton()
    b.setIcon(icons.icon("copy", theme.current.muted, 16))
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.setCursor(Qt.CursorShape.PointingHandCursor)

    def do():
        QApplication.clipboard().setText(text_fn())
        b.setIcon(icons.icon("check", theme.current.ok, 16))
    b.clicked.connect(do)
    return b


def scroll(widget: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(widget)
    return sa


class Card(QFrame):
    def __init__(self, title: str = "", accent: str | None = None, padding=18, spacing=10):
        super().__init__()
        self.setObjectName("card")
        if accent:
            self.setProperty("accent", accent)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding - 2, padding, padding)
        self.body.setSpacing(spacing)
        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        if title:
            self.title_label = label(title, "sectionTitle")
            self.header.addWidget(self.title_label)
            self.header.addStretch(1)
            self.body.addLayout(self.header)

    def add(self, w):
        _add(self.body, w)
        return w

    def set_accent(self, status: str):
        self.setProperty("accent", status)
        self.style().unpolish(self)
        self.style().polish(self)


class Pill(QLabel):
    def __init__(self, status: str = "INFO", text: str | None = None):
        super().__init__()
        self.setObjectName("pill")
        self.set(status, text)

    def set(self, status: str, text: str | None = None):
        self.setText(text or status)
        self.setProperty("status", status if status in ("OK", "WARN", "FAIL") else "INFO")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        self.sub = label(subtitle, "pageSub")
        text = vbox(label(title, "pageTitle"), self.sub, spacing=2)
        self.setLayout(hbox(text, None, self.actions, spacing=12))

    def add_action(self, w):
        self.actions.addWidget(w)
        return w


# ---------------------------------------------------------------- charts
def _aa(p: QPainter):
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)


class Ring(QWidget):
    """Circular gauge. value 0-100. Colour follows thresholds unless fixed."""

    def __init__(self, size=120, thickness=10, color: str | None = None, warn=75, fail=90,
                 center_font=18, caption=""):
        super().__init__()
        self.value, self.text, self.caption = 0.0, "--", caption
        self.fixed, self.warn, self.fail = color, warn, fail
        self.thickness, self.center_font = thickness, center_font
        self.setFixedSize(size, size)

    def set(self, value: float, text: str | None = None, caption: str | None = None):
        self.value = max(0.0, min(100.0, value))
        self.text = text if text is not None else f"{value:.0f}%"
        if caption is not None:
            self.caption = caption
        self.update()

    def color(self) -> QColor:
        if self.fixed:
            return theme.c(self.fixed)
        if self.value >= self.fail:
            return theme.c("fail")
        if self.value >= self.warn:
            return theme.c("warn")
        return theme.c("accent")

    def paintEvent(self, _):
        p = QPainter(self)
        _aa(p)
        t = self.thickness
        r = QRectF(t / 2 + 1, t / 2 + 1, self.width() - t - 2, self.height() - t - 2)
        pen = QPen(theme.c("grid"), t, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 225 * 16, -270 * 16)
        pen.setColor(self.color())
        p.setPen(pen)
        p.drawArc(r, 225 * 16, int(-270 * 16 * self.value / 100))
        p.setPen(theme.c("text"))
        p.setFont(theme.mono(self.center_font, QFont.Weight.Bold))
        box = QRectF(0, 0, self.width(), self.height())
        if self.caption:
            p.drawText(box.adjusted(0, -self.height() * 0.08, 0, 0), Qt.AlignmentFlag.AlignCenter, self.text)
            p.setPen(theme.c("muted"))
            p.setFont(theme.font(max(7.5, self.center_font * 0.42), QFont.Weight.DemiBold))
            p.drawText(box.adjusted(0, self.height() * 0.28, 0, 0), Qt.AlignmentFlag.AlignCenter, self.caption)
        else:
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, self.text)


class AreaChart(QWidget):
    """Rolling line/area chart for one or more series.

    series: list of (sequence, colour-token). ymax=None scales to the data.
    """

    def __init__(self, height=140, ymax: float | None = 100, fmt: Callable[[float], str] = lambda v: f"{v:.0f}%",
                 points=120, grid=True, fill=True, axis=True):
        super().__init__()
        self.series: list[tuple[Sequence[float], str]] = []
        self.ymax, self.fmt, self.points, self.grid, self.fill, self.axis = ymax, fmt, points, grid, fill, axis
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_series(self, series):
        self.series = series
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        _aa(p)
        left = 44 if self.axis else 2
        rect = QRectF(left, 6, self.width() - left - 4, self.height() - 12)
        top = self.ymax
        if top is None:
            top = max([max(s, default=0) for s, _ in self.series] + [1]) * 1.15
        if self.grid:
            p.setFont(theme.font(7.5))
            for i in range(5):
                y = rect.top() + rect.height() * i / 4
                p.setPen(QPen(theme.c("grid"), 1))
                p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
                if self.axis:
                    p.setPen(theme.c("faint"))
                    p.drawText(QRectF(0, y - 8, left - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                               self.fmt(top * (4 - i) / 4))
        for data, token in self.series:
            data = list(data)[-self.points:]
            if len(data) < 2:
                continue
            step = rect.width() / (self.points - 1)
            x0 = rect.right() - step * (len(data) - 1)
            path = QPainterPath()
            for i, v in enumerate(data):
                pt = QPointF(x0 + i * step, rect.bottom() - rect.height() * min(v, top) / top)
                path.moveTo(pt) if i == 0 else path.lineTo(pt)
            color = theme.c(token)
            if self.fill:
                area = QPainterPath(path)
                area.lineTo(rect.right(), rect.bottom())
                area.lineTo(x0, rect.bottom())
                area.closeSubpath()
                g = QLinearGradient(0, rect.top(), 0, rect.bottom())
                c1, c2 = QColor(color), QColor(color)
                c1.setAlpha(90)
                c2.setAlpha(0)
                g.setColorAt(0, c1)
                g.setColorAt(1, c2)
                p.fillPath(area, g)
            p.setPen(QPen(color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)


class Sparkline(AreaChart):
    def __init__(self, height=38, ymax: float | None = 100):
        super().__init__(height=height, ymax=ymax, points=60, grid=False, axis=False)
        self.setMaximumHeight(height)


class CoreBars(QWidget):
    """One vertical bar per logical CPU."""

    def __init__(self, height=110):
        super().__init__()
        self.values: list[float] = []
        self.setMinimumHeight(height)

    def set(self, values):
        self.values = values
        self.update()

    def paintEvent(self, _):
        if not self.values:
            return
        p = QPainter(self)
        _aa(p)
        n = len(self.values)
        gap = 5
        w = (self.width() - gap * (n - 1)) / n
        h = self.height() - 16
        p.setFont(theme.font(7))
        for i, v in enumerate(self.values):
            x = i * (w + gap)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.c("grid"))
            p.drawRoundedRect(QRectF(x, 0, w, h), 3, 3)
            bh = h * v / 100
            color = theme.c("fail") if v >= 90 else theme.c("warn") if v >= 70 else theme.c("accent")
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, h - bh, w, bh), 3, 3)
            p.setPen(theme.c("faint"))
            p.drawText(QRectF(x - 4, h + 2, w + 8, 14), Qt.AlignmentFlag.AlignCenter, str(i))


class UsageBar(QWidget):
    """Thin horizontal bar, colour by threshold."""

    def __init__(self, height=8, warn=85, fail=93, color: str | None = None):
        super().__init__()
        self.value, self.warn, self.fail, self.fixed = 0.0, warn, fail, color
        self.setFixedHeight(height)

    def set(self, value: float):
        self.value = max(0.0, min(100.0, value))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        _aa(p)
        r = self.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.c("grid"))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), r, r)
        if self.fixed:
            color = theme.c(self.fixed)
        else:
            color = theme.c("fail") if self.value >= self.fail else theme.c("warn") if self.value >= self.warn else theme.c("accent")
        p.setBrush(color)
        p.drawRoundedRect(QRectF(0, 0, max(self.height(), self.width() * self.value / 100), self.height()), r, r)


class ScoreTrend(QWidget):
    """Health score over time with status-coloured dots."""

    def __init__(self, height=120):
        super().__init__()
        self.rows: list[dict] = []
        self.setMinimumHeight(height)

    def set(self, rows):
        self.rows = rows[-60:]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        _aa(p)
        rect = QRectF(8, 10, self.width() - 16, self.height() - 20)
        for i in range(3):
            y = rect.top() + rect.height() * i / 2
            p.setPen(QPen(theme.c("grid"), 1))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        if len(self.rows) < 2:
            p.setPen(theme.c("faint"))
            p.setFont(theme.font(9))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Trend appears after a few check runs")
            return
        n = len(self.rows)
        pts = [QPointF(rect.left() + rect.width() * i / (n - 1),
                       rect.bottom() - rect.height() * r["score"] / 100) for i, r in enumerate(self.rows)]
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        p.setPen(QPen(theme.c("accent"), 2))
        p.drawPath(path)
        for pt, r in zip(pts, self.rows):
            p.setPen(QPen(theme.c("surface"), 2))
            p.setBrush(theme.status_color(r["status"]))
            p.drawEllipse(pt, 4, 4)


class Dot(QWidget):
    def __init__(self, status="INFO", size=10):
        super().__init__()
        self.status = status
        self.setFixedSize(size, size)

    def set(self, status):
        self.status = status
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        _aa(p)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.status_color(self.status))
        p.drawEllipse(QRectF(0, 0, self.width(), self.height()))


def clear_layout(lay):
    while lay.count():
        item = lay.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


def rate(v: float) -> str:
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if v < 1024 or unit == "GB/s":
            return f"{v:.0f} {unit}" if unit == "B/s" else f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} GB/s"


def short_rate(v: float) -> str:
    for unit in ("B", "K", "M", "G"):
        if v < 1024 or unit == "G":
            return f"{v:.0f}{unit}"
        v /= 1024
    return f"{v:.0f}G"
