"""Mock-up pictures of PR7-HW, drawn offscreen in the family theme (the PC is made up):
QT_SCALE_FACTOR=2 python tools/mockup.py OUT_DIR

1_summary.png   System Summary (HWiNFO's): the CPU with its cores, caches and features, the board, memory modules,
                graphics, drives and Windows, on one page (OBSIDIAN)
2_details.png   The details tree (Computer > CPU, Motherboard, Memory, Graphics, Drives, Network ...) and the chosen
                device's properties, as HWiNFO lists them (AURORA)
3_sensors.png   Sensors: live readings with Current / Min / Max / Average and a small graph each (OBSIDIAN)
"""
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, QRectF, QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen  # noqa: E402
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,  # noqa: E402
                               QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from pr7hw import theme, widgets  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/mockup")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
theme.load_fonts()
app.setFont(QFont("Inter", 10))


def style():
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.stylesheet())


def dim(text):
    lab = QLabel(text)
    lab.setProperty("role", "dim")
    return lab


def field(text):
    lab = QLabel(text.upper())
    lab.setProperty("role", "field")
    return lab


def toolbar():
    bar = QWidget()
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(16, 10, 16, 6)
    lay.setSpacing(6)
    groups = [[("home", "Summary"), ("list", "Details"), ("chart", "Sensors")],
              [("refresh", "Refresh"), ("save", "Report"), ("copy", "Copy")], [("gear", "Options")]]
    for i, group in enumerate(groups):
        if i:
            sep = QLabel()
            sep.setFixedSize(1, 40)
            sep.setStyleSheet(f"background: {theme.PANEL_EDGE};")
            lay.addSpacing(8)
            lay.addWidget(sep)
            lay.addSpacing(8)
        for icon, label in group:
            k = widgets.KeyButton(icon, label)
            k.setFixedSize(QSize(100, 62))
            lay.addWidget(k)
    lay.addStretch(1)
    return bar


def status(left, right):
    f = QFrame()
    f.setStyleSheet(f"QFrame {{ background: {theme.TAB_FRAME}; border-top: 1px solid {theme.PANEL_EDGE}; }}")
    lay = QHBoxLayout(f)
    lay.setContentsMargins(16, 6, 16, 6)
    lay.addWidget(dim(left))
    lay.addStretch(1)
    lay.addWidget(dim(right))
    return f


def window(body, status_bar):
    w = QWidget()
    w.setObjectName("win")
    w.setStyleSheet(f"QWidget#win {{ background: {theme.BACKGROUND}; }}")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(widgets.Header("HARDWARE"))
    lay.addWidget(toolbar())
    wrap = QWidget()
    wl = QVBoxLayout(wrap)
    wl.setContentsMargins(16, 6, 16, 8)
    wl.addWidget(body)
    lay.addWidget(wrap, 1)
    lay.addWidget(status_bar)
    w.resize(1320, 860)
    return w


def card(title, rows, extra=None):
    f = QFrame()
    f.setObjectName("card")
    f.setStyleSheet(f"QFrame#card {{ background: {theme.DOCK_TOP}; border: 1px solid {theme.PANEL_EDGE}; "
                    f"border-radius: 8px; }}")
    v = QVBoxLayout(f)
    v.setContentsMargins(14, 10, 14, 12)
    v.setSpacing(6)
    h = QLabel(title)
    h.setProperty("role", "heading")
    v.addWidget(h)
    g = QGridLayout()
    g.setHorizontalSpacing(14)
    g.setVerticalSpacing(4)
    for i, (k, val) in enumerate(rows):
        g.addWidget(field(k), i, 0, Qt.AlignmentFlag.AlignTop)
        lab = QLabel(val)
        lab.setWordWrap(True)
        g.addWidget(lab, i, 1)
    g.setColumnStretch(1, 1)
    v.addLayout(g)
    if extra is not None:
        v.addWidget(extra)
    v.addStretch(1)
    return f


def chips(names, on):
    w = QWidget()
    lay = QGridLayout(w)
    lay.setContentsMargins(0, 6, 0, 0)
    lay.setSpacing(4)
    for i, n in enumerate(names):
        lab = QLabel(n)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lit = n in on
        lab.setStyleSheet(f"QLabel {{ background: {theme.qss_gradient() if lit else theme.BUTTON}; color: "
                          f"{'#FFFFFF' if lit else theme.TEXT_DIM}; border-radius: 4px; padding: 3px 6px; "
                          f"font-size: 10.5px; font-weight: 600; }}")
        lay.addWidget(lab, i // 7, i % 7)
    return w


def shoot(widget, name):
    widget.show()
    app.processEvents()
    widget.grab().save(str(out / name))
    widget.close()


# ------------------------------------------------------------------ 1: summary
theme.set_finish("obsidian")
style()
body = QWidget()
grid = QGridLayout(body)
grid.setContentsMargins(0, 0, 0, 0)
grid.setSpacing(10)
features = ["MMX", "SSE4.2", "AVX", "AVX2", "AVX-512", "FMA3", "SHA", "AES-NI", "BMI2", "VT-x/AMD-V", "SMT", "x86-64",
            "RDRAND", "NX"]
cpu = card("AMD Ryzen 9 7950X 16-Core Processor", [
    ("Cores / threads", "16 / 32"), ("Clock", "4.5 GHz base  ·  5.7 GHz boost  ·  now 5.21 GHz"),
    ("Caches", "L1 1 MB  ·  L2 16 MB  ·  L3 64 MB"), ("Socket", "AM5  ·  170 W"),
    ("Family", "Family 25, model 97, stepping 2  ·  AuthenticAMD"), ("Microcode", "0x0A601206")],
    chips(features, set(features) - {"MMX", "VT-x/AMD-V"} | {"VT-x/AMD-V"}))
board = card("ASUS ROG STRIX X670E-E GAMING WIFI", [
    ("Chipset", "AMD X670E"), ("BIOS", "American Megatrends 2613  ·  2026-08-14  ·  UEFI, Secure Boot on"),
    ("TPM", "2.0 (firmware)")])
memory = card("Memory  ·  64 GB DDR5", [
    ("Modules", "2 × 32 GB  ·  4 slots, 2 used"), ("Speed", "6000 MT/s  ·  CL30"),
    ("DIMM A2", "G.Skill F5-6000J3040G32G  ·  32 GB"), ("DIMM B2", "G.Skill F5-6000J3040G32G  ·  32 GB"),
    ("In use", "21.4 GB of 63.1 GB (34 %)")])
gpu = card("NVIDIA GeForce RTX 4080 SUPER", [
    ("Memory", "16 GB"), ("Driver", "32.0.15.6614  ·  2026-11-04"), ("Display", "3840 × 2160 at 144 Hz  ·  DELL U3225QE"),
    ("Second display", "2560 × 1440 at 60 Hz  ·  LG 27QN880")])
drives = card("Drives", [
    ("Disk 0", "Samsung SSD 990 PRO 2TB  ·  NVMe  ·  healthy  ·  41 °C"),
    ("Disk 1", "WD_BLACK SN850X 4000GB  ·  NVMe  ·  healthy  ·  44 °C"),
    ("Disk 2", "ST8000VN004  ·  HDD 7200 rpm  ·  healthy  ·  36 °C"),
    ("Volumes", "C: 1.86 TB (612 GB free)  ·  D: 3.64 TB  ·  E: 7.28 TB")])
osc = card("Windows 11 Pro 24H2", [
    ("Build", "26100.2454  ·  x64"), ("Computer", "STUDIO-PC"), ("Up for", "3 days 4 h"),
    ("Network", "Intel Wi-Fi 7 BE200  ·  Realtek 2.5 GbE (connected, 2.5 Gb/s)")])
grid.addWidget(cpu, 0, 0, 2, 1)
grid.addWidget(board, 0, 1)
grid.addWidget(memory, 1, 1)
grid.addWidget(gpu, 2, 0)
grid.addWidget(drives, 2, 1)
grid.addWidget(osc, 3, 0, 1, 2)
grid.setColumnStretch(0, 1)
grid.setColumnStretch(1, 1)
shoot(window(body, status("SYSTEM SUMMARY  ·  read 1.2 s ago", "Administrator: yes (drive temperatures and SPD shown)")),
      "1_summary.png")

# ------------------------------------------------------------------ 2: details
theme.set_finish("aurora")
style()
split = QSplitter()
tree = QTreeWidget()
tree.setHeaderHidden(True)
tree.setIconSize(QSize(18, 18))
root = QTreeWidgetItem(["STUDIO-PC"])
root.setIcon(0, widgets.line_icon("desktop", theme.LED_ORANGE, 18))
tree.addTopLevelItem(root)
sections = [("Central processor", "app", ["AMD Ryzen 9 7950X"]), ("Motherboard", "drive", ["ROG STRIX X670E-E", "BIOS"]),
            ("Memory", "table", ["DIMM A2", "DIMM B2"]), ("Graphics", "screen", ["RTX 4080 SUPER", "AMD Radeon (iGPU)"]),
            ("Monitors", "desktop", ["DELL U3225QE", "LG 27QN880"]),
            ("Drives", "drive", ["Samsung SSD 990 PRO 2TB", "WD_BLACK SN850X 4000GB", "ST8000VN004"]),
            ("Network", "network", ["Realtek 2.5GbE", "Intel Wi-Fi 7 BE200"]), ("Audio", "volume", ["Realtek USB Audio",
                                                                                                 "NVIDIA HD Audio"]),
            ("USB", "usb", ["4 controllers, 11 devices"]), ("Windows", "window", ["Windows 11 Pro 24H2"])]
chosen = None
for name, icon, kids in sections:
    it = QTreeWidgetItem([name])
    it.setIcon(0, widgets.line_icon(icon, None, 18))
    root.addChild(it)
    for k in kids:
        c = QTreeWidgetItem([k])
        it.addChild(c)
        if k == "Samsung SSD 990 PRO 2TB":
            chosen = c
tree.expandAll()
tree.setCurrentItem(chosen)
props = QTreeWidget()
props.setHeaderLabels(["PROPERTY", "VALUE"])
props.setRootIsDecorated(True)
groups = [("Drive", [("Model", "Samsung SSD 990 PRO 2TB"), ("Serial number", "S7KHNJ0X123456A"),
                     ("Firmware", "4B2QJXD7"), ("Capacity", "2.00 TB (2,000,398,934,016 bytes)"),
                     ("Interface", "NVMe  ·  PCIe 4.0 x4"), ("Media", "SSD"), ("Partition style", "GPT"),
                     ("Partitions", "EFI 100 MB  ·  MSR 16 MB  ·  C: 1.86 TB  ·  Recovery 750 MB")]),
          ("Health (S.M.A.R.T.)", [("Status", "Healthy"), ("Temperature", "41 °C  (highest seen 63 °C)"),
                                   ("Wear", "3 % used"), ("Written", "48.2 TB"), ("Read", "71.9 TB"),
                                   ("Power on", "6,412 hours  ·  1,284 starts"), ("Unsafe shutdowns", "37"),
                                   ("Media errors", "0")])]
for g, rows in groups:
    gi = QTreeWidgetItem([g.upper()])
    f = gi.font(0)
    f.setWeight(QFont.Weight.DemiBold)
    gi.setFont(0, f)
    props.addTopLevelItem(gi)
    for k, v in rows:
        gi.addChild(QTreeWidgetItem([k, v]))
props.expandAll()
props.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
split.addWidget(tree)
split.addWidget(props)
split.setSizes([380, 900])
shoot(window(split, status("DRIVES  ·  Samsung SSD 990 PRO 2TB", "Ctrl+C copies the property  ·  Report saves it all")),
      "2_details.png")


# ------------------------------------------------------------------ 3: sensors
class Spark(QWidget):
    def __init__(self, values, top):
        super().__init__()
        self.values, self.top = values, top
        self.setFixedHeight(26)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 3, -2, -3)
        n = len(self.values)
        path = QPainterPath()
        for i, v in enumerate(self.values):
            pt = QPointF(r.left() + r.width() * i / (n - 1), r.bottom() - r.height() * min(1, v / self.top))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        fill = QPainterPath(path)
        fill.lineTo(r.right(), r.bottom())
        fill.lineTo(r.left(), r.bottom())
        c = QColor(theme.LED_ORANGE)
        c.setAlphaF(.16)
        p.fillPath(fill, c)
        p.setPen(QPen(QColor(theme.LED_ORANGE), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


theme.set_finish("obsidian")
style()
sens = QTreeWidget()
sens.setHeaderLabels(["SENSOR", "CURRENT", "MIN", "MAX", "AVERAGE", "LAST 2 MINUTES"])
sens.setIconSize(QSize(16, 16))


def wave(base, amp, k=1.0, n=60):
    return [max(0, base + amp * math.sin(i / 4 * k) + amp * .4 * math.sin(i * 1.7 * k)) for i in range(n)]


readings = [
    ("CPU  ·  AMD Ryzen 9 7950X", "app", [
        ("Total load", "38 %", "2 %", "100 %", "27 %", wave(38, 18), 100),
        ("Clock (average core)", "5.21 GHz", "3.02 GHz", "5.74 GHz", "4.88 GHz", wave(5.0, .4, 2), 6),
        ("Temperature (ACPI thermal zone)", "54 °C", "38 °C", "71 °C", "50 °C", wave(54, 6, .7), 100),
        ("Processes  ·  threads", "312  ·  4,861", "298", "341", "309", wave(312, 10, .5), 400)]),
    ("Memory", "table", [("In use", "21.4 GB", "19.8 GB", "38.1 GB", "23.2 GB", wave(21, 2, .3), 64),
                         ("Load", "34 %", "31 %", "60 %", "37 %", wave(34, 3, .3), 100)]),
    ("GPU  ·  RTX 4080 SUPER", "screen", [
        ("Load", "71 %", "0 %", "99 %", "44 %", wave(70, 22, 1.3), 100),
        ("Temperature", "63 °C", "34 °C", "71 °C", "55 °C", wave(62, 4, .5), 100),
        ("Video memory", "9.6 GB", "1.1 GB", "12.4 GB", "6.9 GB", wave(9.6, 1, .4), 16)]),
    ("Drives", "drive", [("Samsung 990 PRO  ·  temperature", "41 °C", "36 °C", "52 °C", "42 °C", wave(41, 3, .4), 80),
                         ("Samsung 990 PRO  ·  read", "412 MB/s", "0 B/s", "6.81 GB/s", "88 MB/s", wave(400, 380, 2),
                          1200),
                         ("ST8000VN004  ·  temperature", "36 °C", "33 °C", "38 °C", "35 °C", wave(36, 1, .3), 80)]),
    ("Network  ·  Realtek 2.5GbE", "network", [("Download", "18.4 MB/s", "0 B/s", "281 MB/s", "6.2 MB/s",
                                                wave(18, 16, 1.6), 60),
                                               ("Upload", "0.9 MB/s", "0 B/s", "38.0 MB/s", "0.4 MB/s",
                                                wave(1, .9, 1.9), 5)])]
for g, icon, rows in readings:
    gi = QTreeWidgetItem([g])
    gi.setIcon(0, widgets.line_icon(icon, theme.LED_ORANGE, 16))
    f = gi.font(0)
    f.setWeight(QFont.Weight.DemiBold)
    gi.setFont(0, f)
    sens.addTopLevelItem(gi)
    for name, cur, lo, hi, avg, vals, top in rows:
        it = QTreeWidgetItem([name, cur, lo, hi, avg, ""])
        for c in range(1, 5):
            it.setTextAlignment(c, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it.setForeground(1, QColor(theme.LED_ORANGE))
        gi.addChild(it)
        sens.setItemWidget(it, 5, Spark(vals, top))
sens.expandAll()
h = sens.header()
h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
for c in range(1, 5):
    h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
h.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
shoot(window(sens, status("SENSORS  ·  every 2 s  ·  running 14 min", "Reset Min / Max  ·  Log to CSV")),
      "3_sensors.png")
print("ok", out)
