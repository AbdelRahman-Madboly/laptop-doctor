"""Design tokens and the Qt stylesheet. Dark 'instrument panel' by default, light on request."""

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    sidebar: str
    surface: str
    surface2: str
    border: str
    text: str
    muted: str
    faint: str
    accent: str
    accent_text: str
    ok: str
    warn: str
    fail: str
    blue: str
    purple: str
    pink: str
    grid: str


DARK = Palette(
    name="dark", bg="#0b0f14", sidebar="#0f141b", surface="#141a22", surface2="#1a212b",
    border="#232c38", text="#e6edf3", muted="#8b98a8", faint="#56606e",
    accent="#2dd4bf", accent_text="#04201c", ok="#3fb950", warn="#e3a008", fail="#f85149",
    blue="#58a6ff", purple="#bc8cff", pink="#f778ba", grid="#1d2530",
)

LIGHT = Palette(
    name="light", bg="#f4f6f9", sidebar="#ebeff4", surface="#ffffff", surface2="#f6f8fb",
    border="#dde3ea", text="#17202b", muted="#5b6878", faint="#98a3b0",
    accent="#0f9f8f", accent_text="#ffffff", ok="#1f883d", warn="#b07800", fail="#cf222e",
    blue="#0969da", purple="#8250df", pink="#bf3989", grid="#eaeef3",
)

current: Palette = DARK


def status_color(status: str) -> QColor:
    return QColor({"OK": current.ok, "WARN": current.warn, "FAIL": current.fail}.get(status, current.muted))


def c(name: str) -> QColor:
    return QColor(getattr(current, name))


def mono(size: float = 10, weight=QFont.Weight.Normal) -> QFont:
    f = QFont("Ubuntu Sans Mono")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def font(size: float = 10, weight=QFont.Weight.Normal) -> QFont:
    f = QFont("Ubuntu Sans")
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def stylesheet(p: Palette) -> str:
    return f"""
* {{ font-family: "Ubuntu Sans"; color: {p.text}; }}
QMainWindow, #root {{ background: {p.bg}; }}
QToolTip {{ background: {p.surface2}; color: {p.text}; border: 1px solid {p.border}; padding: 6px 8px; border-radius: 6px; }}

#sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
#brand {{ font-size: 13pt; font-weight: 800; letter-spacing: 0.2px; }}
#brandSub {{ color: {p.muted}; font-size: 8.5pt; }}
#navButton {{
    text-align: left; padding: 9px 12px; border: none; border-radius: 9px;
    color: {p.muted}; font-size: 10pt; font-weight: 600; background: transparent;
}}
#navButton:hover {{ background: {p.surface2}; color: {p.text}; }}
#navButton:checked {{ background: {p.surface2}; color: {p.text}; border-left: 3px solid {p.accent}; }}
#sideStatus {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; }}

#pageTitle {{ font-size: 19pt; font-weight: 800; letter-spacing: -0.3px; }}
#pageSub {{ color: {p.muted}; font-size: 10pt; }}
#sectionTitle {{ font-size: 11pt; font-weight: 700; }}
#muted {{ color: {p.muted}; }}
#faint {{ color: {p.faint}; font-size: 9pt; }}
#kpiValue {{ font-size: 20pt; font-weight: 800; font-family: "Ubuntu Sans Mono"; }}
#kpiLabel {{ color: {p.muted}; font-size: 9pt; font-weight: 700; letter-spacing: 0.6px; }}
#bigNumber {{ font-size: 28pt; font-weight: 800; letter-spacing: -0.5px; }}

#card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 14px; }}
#card[accent="OK"] {{ border-left: 3px solid {p.ok}; }}
#card[accent="WARN"] {{ border-left: 3px solid {p.warn}; }}
#card[accent="FAIL"] {{ border-left: 3px solid {p.fail}; }}
#inset {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 10px; }}

QPushButton {{
    background: {p.surface2}; border: 1px solid {p.border}; border-radius: 8px;
    padding: 7px 14px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {p.accent}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton:disabled {{ color: {p.faint}; border-color: {p.border}; }}
QPushButton#primary {{ background: {p.accent}; color: {p.accent_text}; border: none; }}
QPushButton#primary:hover {{ background: {p.accent}; border: 1px solid {p.text}; }}
QPushButton#primary:disabled {{ background: {p.border}; color: {p.faint}; }}
QPushButton#danger {{ color: {p.fail}; }}
QPushButton#danger:hover {{ border-color: {p.fail}; }}
QPushButton#ghost {{ background: transparent; border: none; color: {p.muted}; padding: 4px 8px; }}
QPushButton#ghost:hover {{ color: {p.accent}; }}

QLabel#pill {{ border-radius: 9px; padding: 2px 9px; font-size: 8.5pt; font-weight: 800; letter-spacing: 0.5px; }}
QLabel#pill[status="OK"] {{ background: rgba(63,185,80,0.16); color: {p.ok}; }}
QLabel#pill[status="WARN"] {{ background: rgba(227,160,8,0.18); color: {p.warn}; }}
QLabel#pill[status="FAIL"] {{ background: rgba(248,81,73,0.18); color: {p.fail}; }}
QLabel#pill[status="INFO"] {{ background: {p.surface2}; color: {p.muted}; }}
QLabel#code {{
    font-family: "Ubuntu Sans Mono"; background: {p.surface2}; border: 1px solid {p.border};
    border-radius: 6px; padding: 3px 7px; color: {p.text};
}}

QLineEdit, QSpinBox, QComboBox {{
    background: {p.surface2}; border: 1px solid {p.border}; border-radius: 8px; padding: 6px 10px;
    selection-background-color: {p.accent}; selection-color: {p.accent_text};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {p.accent}; }}
QComboBox QAbstractItemView {{ background: {p.surface2}; border: 1px solid {p.border}; selection-background-color: {p.border}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {p.faint}; background: {p.surface2}; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}

QTableView, QTreeView, QListWidget {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px;
    gridline-color: transparent; alternate-background-color: {p.surface2};
    selection-background-color: {p.border}; selection-color: {p.text}; outline: none;
}}
QListWidget::item {{ padding: 8px 10px; border-radius: 8px; }}
QListWidget::item:selected {{ background: {p.surface2}; border-left: 3px solid {p.accent}; }}
QHeaderView::section {{
    background: {p.surface}; color: {p.muted}; border: none; border-bottom: 1px solid {p.border};
    padding: 8px 10px; font-weight: 700; font-size: 8.5pt;
}}
QPlainTextEdit {{ font-family: "Ubuntu Sans Mono"; font-size: 9pt; }}
QTextBrowser, QPlainTextEdit {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; padding: 10px;
    selection-background-color: {p.accent}; selection-color: {p.accent_text};
}}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.faint}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{ background: {p.surface2}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 4px; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p.surface2}; }}
QMenu::item:disabled {{ color: {p.muted}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}
"""
