"""Screenshots of the real PR7-HW window on the made-up PC of tools/sample_pc.py, offscreen:
QT_SCALE_FACTOR=2 python tools/screenshots.py OUT_DIR

summary.png          System Summary (OBSIDIAN)
details_aurora.png   the details tree, a drive's properties and health (AURORA)
sensors.png          Sensors after two minutes of made-up readings (OBSIDIAN)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ["PARAGON_FAMILY_FILE"] = os.path.join(tempfile.mkdtemp(), "finish")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())

import sample_pc  # noqa: E402
from pr7hw import sensors, theme, wmi  # noqa: E402
from pr7hw.main_window import MainWindow  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
theme.load_fonts()
app.setFont(QFont("Inter", 10))
data = wmi.read(run=lambda s: json.dumps(sample_pc.DATA))
LOCAL = {"features": {"MMX", "SSE2", "SSE3", "SSSE3", "SSE4.1", "SSE4.2", "AVX", "AVX2", "AVX-512", "FMA3", "AES-NI",
                      "BMI2", "RDRAND", "NX", "x86-64", "VT-x/AMD-V"},
         "caches": {1: 1 << 20, 2: 16 << 20, 3: 64 << 20}, "cpu_mhz": 5210.0, "mem_text": "21.4 GB of 63.1 GB (34 %)"}


class Made:
    """Two minutes of made-up readings, like the mock-up's."""

    def __init__(self):
        self.i = 0

    def __call__(self):
        self.i += 1
        i = self.i

        def w(base, amp, k=1.0):
            return max(0.0, base + amp * math.sin(i / 4 * k) + amp * .4 * math.sin(i * 1.7 * k))
        return [("CPU", "Total load", min(100, w(38, 18)), "percent"), ("CPU", "Busiest core", min(100, w(71, 25)), "percent"),
                ("CPU", "Clock", w(5000, 300, 2) * 1.0, "mhz"), ("CPU", "Processes", round(w(312, 8, .5)), "count"),
                ("Memory", "In use", w(21.4, 2, .3) * 2 ** 30, "bytes"), ("Memory", "Load", w(34, 3, .3), "percent"),
                ("GPU 1  ·  NVIDIA GeForce RTX 4080 SUPER", "Load", min(100, w(70, 22, 1.3)), "percent"),
                ("GPU 1  ·  NVIDIA GeForce RTX 4080 SUPER", "Temperature", w(62, 4, .5), "temp"),
                ("GPU 1  ·  NVIDIA GeForce RTX 4080 SUPER", "Video memory", w(9.6, 1, .4) * 2 ** 30, "bytes"),
                ("Motherboard", "Temperature (ACPI thermal zone TZ00)", w(54, 6, .7), "temp"),
                ("Drives", "Samsung SSD 990 PRO 2TB  ·  read", w(400, 380, 2) * 1e6, "rate"),
                ("Drives", "Samsung SSD 990 PRO 2TB  ·  temperature", w(41, 3, .4), "temp"),
                ("Network  ·  Ethernet", "Download", w(18, 16, 1.6) * 1e6, "rate"),
                ("Network  ·  Ethernet", "Upload", w(1, .9, 1.9) * 1e6, "rate")]


sampler = sensors.Sampler([Made()])
for _ in range(sensors.HISTORY - 1):
    sampler.sample()
w = MainWindow(reader=lambda: data, sampler=sampler, local=lambda: dict(LOCAL), sync=True)
w.resize(1320, 860)
w.show()
w.refresh()


def shoot(name):
    app.processEvents()
    w.grab().save(str(out / name))


theme.set_finish("obsidian")
w.set_finish("obsidian")
w.show_page("summary")
shoot("summary.png")
w.set_finish("aurora")
w.show_page("details")
top = w.tree.topLevelItem(0)
drives = next(top.child(i) for i in range(top.childCount()) if top.child(i).text(0) == "Drives")
w.tree.setCurrentItem(drives.child(0))
shoot("details_aurora.png")
w.set_finish("obsidian")
w.show_page("sensors")
shoot("sensors.png")
w.close()
print("ok", out)
