import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PARAGON_FAMILY_FILE"] = os.path.join(tempfile.mkdtemp(prefix="family-"), "finish")  # never the real choice
os.environ["PR7HW_DATA"] = tempfile.mkdtemp(prefix="pr7hw-data-")      # never the real data folder


@pytest.fixture(scope="session")
def qapp(tmp_path_factory):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)           # never the real settings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path_factory.mktemp("settings")))
    app = QApplication.instance() or QApplication([])
    from pr7hw import theme
    theme.load_fonts()
    yield app
    app.clipboard().clear()


@pytest.fixture
def studio():
    """The made-up PC's answer, as wmi.read gives it (through the real parser)."""
    import sample_pc
    import json
    from pr7hw import wmi
    return wmi.read(run=lambda script: json.dumps(sample_pc.DATA))


LOCAL = {"features": {"MMX", "SSE2", "SSE3", "SSSE3", "SSE4.1", "SSE4.2", "AVX", "AVX2", "AVX-512", "FMA3", "AES-NI",
                      "BMI2", "RDRAND", "NX", "x86-64", "VT-x/AMD-V"},
         "caches": {1: 1 << 20, 2: 16 << 20, 3: 64 << 20}, "cpu_mhz": 5210.0, "mem_text": "21.4 GB of 63.1 GB (34 %)"}


class Fake:
    """Sensor sources standing in for the PC: values go up by one each sample."""

    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return [("CPU", "Total load", 30.0 + self.n, "percent"), ("CPU", "Clock", 5000.0 + self.n, "mhz"),
                ("GPU  ·  RTX 4080 SUPER", "Temperature", 60.0 + self.n, "temp"),
                ("Drives", "Samsung SSD 990 PRO 2TB  ·  read", 1e6 * self.n, "rate")]


@pytest.fixture
def window(qapp, studio):
    from pr7hw import sensors, settings
    from pr7hw.main_window import MainWindow
    for k, v in (("interval", 2), ("units", "c"), ("start_page", "summary")):
        settings.set(k, v)
    w = MainWindow(reader=lambda: studio, sampler=sensors.Sampler([Fake()]), local=lambda: dict(LOCAL), sync=True)
    w.said = []
    w.answers.update({"say": lambda kind, text: w.said.append((kind, text))})
    w.resize(1320, 860)
    w.show()
    w.refresh()
    yield w
    w.close()
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
