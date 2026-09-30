"""Device: hardware, OS, storage and network facts."""

from PySide6.QtWidgets import QGridLayout, QWidget

from ... import sysinfo
from ...util import human
from .. import icons, theme
from ..widgets import Card, PageHeader, Pill, UsageBar, button, clear_layout, copy_button, hbox, label, run_async, \
    scroll, vbox

ICONS = {"System": "device", "Processor": "cpu", "Memory": "memory", "Graphics": "gpu", "Battery": "battery"}


class DevicePage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.info: dict = {}
        self.header = PageHeader("This device", "Loading…")
        refresh = self.header.add_action(button("Refresh", "updates"))
        refresh.clicked.connect(self.load)
        self.header.add_action(copy_button(self._as_text, "Copy all as text"))
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        body = QWidget()
        body.setLayout(vbox(self.header, self.grid, None, spacing=14, margins=(28, 24, 28, 24)))
        self.setLayout(vbox(scroll(body)))
        self._loaded = False

    def showEvent(self, e):
        if not self._loaded:
            self.load()
        super().showEvent(e)

    def load(self):
        self._loaded = True
        run_async(sysinfo.collect, on_done=self._show)

    def _as_text(self) -> str:
        lines = []
        for section, facts in self.info.items():
            if section.startswith("_"):
                continue
            lines.append(f"[{section}]")
            lines += [f"  {k}: {v}" for k, v in facts.items()]
        for d in self.info.get("_disks", []):
            lines.append(f"[Disk] {d['name']} {d['model']} {d['size']} {d['bus']}")
        return "\n".join(lines)

    def _facts_card(self, title: str, facts: dict) -> Card:
        card = Card(padding=18, spacing=8)
        ic = label()
        ic.setPixmap(icons.pixmap(ICONS.get(title, "device"), theme.current.accent, 18))
        card.add(hbox(ic, label(title, "sectionTitle"), None, spacing=8))
        for k, v in facts.items():
            key = label(k, "muted")
            key.setFixedWidth(118)
            card.add(hbox(key, label(str(v), wrap=True, select=True), spacing=10))
        card.add(None)
        return card

    def _show(self, info: dict):
        self.info = info
        s = info["System"]
        self.header.sub.setText(f"{s['Model']}  ·  {s['OS']}  ·  kernel {s['Kernel']}  ·  up {s['Uptime']}")
        clear_layout(self.grid)
        sections = [k for k in info if not k.startswith("_")]
        for i, name in enumerate(sections):
            self.grid.addWidget(self._facts_card(name, info[name]), i // 3, i % 3)
        row = (len(sections) + 2) // 3

        storage = Card("Storage")
        for d in info["_disks"]:
            storage.add(hbox(label(f"{d['model']}", "sectionTitle"), Pill("INFO", d["bus"].upper() or "DISK"), None,
                             label(d["size"], "muted"), spacing=8))
        for p in info["_partitions"]:
            bar = UsageBar(height=7)
            bar.set(p["percent"])
            storage.add(vbox(hbox(label(p["mount"]), label(f"{p['device']} · {p['fs']}", "faint"), None,
                                  label(f"{human(p['used'])} / {human(p['total'])}", "muted"), spacing=8),
                             bar, spacing=4))
        storage.add(None)
        self.grid.addWidget(storage, row, 0, 1, 2)

        net = Card("Network interfaces")
        for n in info["_interfaces"]:
            speed = f"{n['speed']} Mb/s" if n["speed"] > 0 else ""
            net.add(vbox(hbox(label(n["name"], "sectionTitle"), Pill("OK" if n["up"] else "INFO",
                                                                      "UP" if n["up"] else "DOWN"), None,
                              label(speed, "faint"), spacing=8),
                         label(f"{n['ipv4'] or 'no IPv4'}  ·  {n['mac']}", "muted", select=True), spacing=2))
        net.add(None)
        self.grid.addWidget(net, row, 2)
        for col in range(3):
            self.grid.setColumnStretch(col, 1)
