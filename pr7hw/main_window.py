"""PR7-HW's window: System Summary, the details tree and Sensors, the way HWiNFO shows them (the mock-up's pages).

Windows is asked once at the start (wmi.read: one PowerShell run, a few seconds) on a thread; the sensors are sampled
every few seconds on a thread too (nvidia-smi and the drives' health counters take a moment). `sync = True` runs both
inline (tests); `reader` (-> wmi data) and `sampler` are injectable. Every question goes through `_ask(kind)`
(tests: `answers`), every message through `_say`."""

from __future__ import annotations

import os
import sys
import threading
import time

import psutil
from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QKeySequence, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSplitter, QStackedWidget, QStyledItemDelegate, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from . import __version__, cpuinfo, finish, hardware, sensors, settings, theme, widgets, wmi

PAGES = ("summary", "details", "sensors")
INTERVALS = (1, 2, 5, 10)
KEY_ROLE = Qt.ItemDataRole.UserRole + 1


def _dim(text: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setProperty("role", "dim")
    return lab


def _field(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setProperty("role", "field")
    return lab


def local_info() -> dict:
    """What Python reads itself: caches and features (cpuinfo), the clock now and memory in use (psutil)."""
    vm = psutil.virtual_memory()
    f = psutil.cpu_freq()
    used = vm.total - vm.available
    return {"features": cpuinfo.features(), "caches": cpuinfo.caches(), "cpu_mhz": f.current if f else None,
            "mem_text": f"{hardware.mem(used)} of {hardware.mem(vm.total)} ({vm.percent:.0f} %)",
            "computer": os.environ.get("COMPUTERNAME", "")}


class _Bridge(QObject):
    read = Signal(object, object)          # wmi data, local info
    sampled = Signal()


class Spark(QStyledItemDelegate):
    """The LAST 2 MINUTES column: a reading's history as a filled line (newest on the right)."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def paint(self, p: QPainter, option, index):
        key = index.data(KEY_ROLE)
        r = self.window.sampler.readings.get(key) if key else None
        if r is None or len(r.values) < 2:
            return
        vals = list(r.values)
        if r.kind == "percent":
            low, top = 0.0, 100.0
        else:                       # HWiNFO's way: each graph spans its own range, so a 41-45 °C wobble shows
            low, top = min(vals), max(vals)
            pad = (top - low) * 0.15 or max(abs(top) * 0.05, 1.0)
            low, top = (max(0.0, low - pad) if r.kind in ("rate", "bytes") and low - pad < 0 else low - pad), top + pad
        box = QRectF(option.rect).adjusted(4, 5, -4, -5)
        n = sensors.HISTORY
        path = QPainterPath()
        start = n - len(vals)
        for i, v in enumerate(vals):
            pt = QPointF(box.left() + box.width() * (start + i) / (n - 1),
                         box.bottom() - box.height() * max(0.0, min(1.0, (v - low) / (top - low))))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        fill = QPainterPath(path)
        fill.lineTo(box.right(), box.bottom())
        fill.lineTo(box.left() + box.width() * start / (n - 1), box.bottom())
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(theme.LED_ORANGE)
        c.setAlphaF(.16)
        p.fillPath(fill, c)
        p.setPen(QPen(QColor(theme.LED_ORANGE), 1.4))     # a line with no brush (PR7-SM's lesson: no chord fill)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.restore()


class OptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        form = QFormLayout()
        self.interval = QComboBox()
        for s in INTERVALS:
            self.interval.addItem(f"Every {s} s", s)
        self.interval.setCurrentIndex(max(0, self.interval.findData(settings.get_int("interval", 2))))
        self.units = QComboBox()
        self.units.addItem("Celsius (°C)", "c")
        self.units.addItem("Fahrenheit (°F)", "f")
        self.units.setCurrentIndex(1 if settings.get("units", "c") == "f" else 0)
        self.start = QComboBox()
        for p in PAGES:
            self.start.addItem(p.title(), p)
        self.start.setCurrentIndex(max(0, self.start.findData(settings.get("start_page", "summary"))))
        from . import update_ui
        self.updates = QComboBox()
        self.updates.addItem("Check for updates once a day", True)
        self.updates.addItem("Don't check for updates", False)
        self.updates.setCurrentIndex(0 if update_ui.auto_enabled() else 1)
        form.addRow(_field("Sensors"), self.interval)
        form.addRow(_field("Temperatures"), self.units)
        form.addRow(_field("Start with"), self.start)
        form.addRow(_field("Updates"), self.updates)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        b = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        lay.addWidget(b)

    def save(self):
        settings.set("interval", self.interval.currentData())
        settings.set("units", self.units.currentData())
        settings.set("start_page", self.start.currentData())
        from . import update_ui
        update_ui.set_auto(bool(self.updates.currentData()))


class MainWindow(QMainWindow):
    def __init__(self, reader=None, sampler: sensors.Sampler | None = None, local=None, sync: bool = False):
        super().__init__()
        self.answers: dict = {}
        self.said: list = []
        self.sync = sync
        self.reader = reader or wmi.read
        self.local_reader = local or local_info
        self.data: dict = {}
        self.local: dict = {}
        self.root: hardware.Node | None = None
        self.cards: list[hardware.Card] = []
        self.sampler = sampler
        self.loading = False
        self._sampling = False
        self.bridge = _Bridge()
        self.bridge.read.connect(self._have_data)
        self.bridge.sampled.connect(self._show_sensors)
        self.setWindowTitle("Paragon PR7-HW" + ("  (Administrator)" if sensors.is_admin() else ""))
        self.resize(1320, 860)
        self._build()
        self._menus()
        self.restyle()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.show_page(settings.get("start_page", "summary") if settings.get("start_page", "summary") in PAGES
                       else "summary")

    # ================================================================ building
    def _build(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = widgets.Header("HARDWARE")
        lay.addWidget(self.header)
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 10, 16, 6)
        bl.setSpacing(6)
        self.keys: dict[str, widgets.KeyButton] = {}
        groups = [[("summary", "home", "Summary", lambda: self.show_page("summary")),
                   ("details", "list", "Details", lambda: self.show_page("details")),
                   ("sensors", "chart", "Sensors", lambda: self.show_page("sensors"))],
                  [("refresh", "refresh", "Refresh", self.refresh), ("report", "save", "Report", self.save_report),
                   ("copy", "copy", "Copy", self.copy)],
                  [("admin", "key", "As Admin", self.as_admin), ("options", "gear", "Options", self.options)]]
        for i, group in enumerate(groups):
            if i:
                sep = QLabel()
                sep.setObjectName("sep")
                sep.setFixedSize(1, 40)
                bl.addSpacing(8)
                bl.addWidget(sep)
                bl.addSpacing(8)
            for key, icon, label, slot in group:
                k = widgets.KeyButton(icon, label)
                k.setFixedSize(QSize(100, 62))
                k.clicked.connect(lambda _=False, s=slot: s())
                bl.addWidget(k)
                self.keys[key] = k
        self.keys["admin"].setVisible(sys.platform == "win32" and not sensors.is_admin())
        bl.addStretch(1)
        lay.addWidget(bar)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._summary_page())
        self.pages.addWidget(self._details_page())
        self.pages.addWidget(self._sensors_page())
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(16, 6, 16, 8)
        wl.addWidget(self.pages)
        lay.addWidget(wrap, 1)
        foot = QFrame()
        foot.setObjectName("foot")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(16, 6, 16, 6)
        self.status = _dim("")
        fl.addWidget(self.status, 1)
        self.state = _dim("")
        fl.addWidget(self.state)
        lay.addWidget(foot)

    def _summary_page(self):
        self.summary_scroll = QScrollArea()
        self.summary_scroll.setWidgetResizable(True)
        self.summary_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.summary_body = QWidget()
        self.summary_body.setObjectName("summary")
        self.summary_grid = QGridLayout(self.summary_body)
        self.summary_grid.setContentsMargins(0, 0, 0, 0)
        self.summary_grid.setSpacing(10)
        self.summary_scroll.setWidget(self.summary_body)
        self.card_widgets: list[QFrame] = []
        return self.summary_scroll

    def _details_page(self):
        split = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.currentItemChanged.connect(lambda *_: self.show_node())
        self.props = QTreeWidget()
        self.props.setHeaderLabels(["PROPERTY", "VALUE"])
        self.props.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.props.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        split.addWidget(self.tree)
        split.addWidget(self.props)
        split.setSizes([380, 900])
        self.split = split
        return split

    def _sensors_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.reset_button = QPushButton("RESET MIN / MAX")
        self.reset_button.clicked.connect(self.reset_sensors)
        self.log_button = QPushButton("LOG TO CSV")
        self.log_button.setCheckable(True)
        self.log_button.clicked.connect(lambda on: self.toggle_log(on))
        top.addWidget(self.reset_button)
        top.addWidget(self.log_button)
        top.addStretch(1)
        self.sensor_note = _dim("")
        top.addWidget(self.sensor_note)
        lay.addLayout(top)
        self.sens = QTreeWidget()
        self.sens.setHeaderLabels(["SENSOR", "CURRENT", "MIN", "MAX", "AVERAGE", "LAST 2 MINUTES"])
        self.sens.setIconSize(QSize(16, 16))
        self.sens.setItemDelegateForColumn(5, Spark(self))
        self.sens.setUniformRowHeights(True)
        h = self.sens.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(1, 5):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.sens_items: dict = {}
        self.sens_groups: dict = {}
        lay.addWidget(self.sens, 1)
        return w

    def _act(self, menu, text, slot, keys=None, key=None, checkable=False):
        a = QAction(text, self)
        if keys:
            a.setShortcuts([QKeySequence(k) for k in (keys if isinstance(keys, (list, tuple)) else [keys])])
        a.setCheckable(checkable)
        a.triggered.connect(lambda *_: slot())
        menu.addAction(a)
        if key:
            self.acts[key] = a
        return a

    def _menus(self):
        self.acts: dict[str, QAction] = {}
        mb = self.menuBar()
        m = mb.addMenu("&File")
        self._act(m, "Save Report…", self.save_report, "Ctrl+S", "report")
        self._act(m, "Log Sensors to CSV…", lambda: self.toggle_log(not bool(self.sampler and self.sampler.log_path)),
                  None, "log")
        m.addSeparator()
        self._act(m, "Exit", self.close, "Alt+F4")
        m = mb.addMenu("&Edit")
        self._act(m, "Copy", self.copy, "Ctrl+C", "copy")
        m = mb.addMenu("&View")
        group = QActionGroup(self)
        for i, p in enumerate(PAGES):
            a = self._act(m, p.title(), lambda p=p: self.show_page(p), f"Ctrl+{i + 1}", f"page_{p}", True)
            group.addAction(a)
        m.addSeparator()
        self._act(m, "Refresh", self.refresh, "F5", "refresh")
        fm = m.addMenu("Finish")
        self.finish_acts = {}
        fg = QActionGroup(self)
        for name in ("obsidian", "aurora"):
            a = self._act(fm, name.upper(), lambda n=name: self.set_finish(n), checkable=True)
            fg.addAction(a)
            self.finish_acts[name] = a
        m = mb.addMenu("&Sensors")
        self._act(m, "Reset Min / Max", self.reset_sensors, "Ctrl+R", "reset")
        m = mb.addMenu("&Tools")
        self._act(m, "Restart as Administrator", self.as_admin, None, "admin").setEnabled(
            sys.platform == "win32" and not sensors.is_admin())
        self._act(m, "Options…", self.options, None, "options")
        m = mb.addMenu("&Help")
        self._act(m, "Check for Updates…", self.check_updates, None, "updates")
        self._act(m, "About PR7-HW", lambda: self._say("info", f"Paragon PR7-HW {__version__}\nHardware information, "
                                                               "the way HWiNFO and CPU-Z show it."))

    # ================================================================ look
    def restyle(self):
        app = QApplication.instance()
        if app is not None:
            app.setPalette(theme.palette())
            app.setStyleSheet(theme.stylesheet())
        self.centralWidget().setStyleSheet(
            f"QWidget#central {{ background: {theme.BACKGROUND}; }} QLabel#sep {{ background: {theme.PANEL_EDGE}; }} "
            f"QWidget#summary {{ background: {theme.BACKGROUND}; }} "
            f"QFrame#foot {{ background: {theme.TAB_FRAME}; border-top: 1px solid {theme.PANEL_EDGE}; }} "
            f"QFrame#card {{ background: {theme.DOCK_TOP}; border: 1px solid {theme.PANEL_EDGE}; border-radius: 8px; }} "
            # the theme leaves tree selection to a painted band; these plain trees use the tables' soft gradient band
            f"QTreeView::item:selected {{ background: {theme.qss_gradient(theme.LIT, 0.22)}; }} "
            f"QTreeView::branch:selected {{ background: transparent; }} "
            f"QTreeView {{ selection-background-color: transparent; }}")    # Qt's own fill of the indent
        self.header.update()
        for name, a in getattr(self, "finish_acts", {}).items():
            a.setChecked(name == theme.FINISH)
        if self.cards:
            self._fill_summary()
        self.sens.viewport().update()

    def set_finish(self, name: str):
        theme.set_finish(name)
        finish.set(theme.FINISH)
        settings.set("finish", theme.FINISH)
        self.restyle()

    # ================================================================ reading the hardware
    def refresh(self):
        """Ask Windows again (a few seconds, on a thread)."""
        if self.loading:
            return
        self.loading = True
        self.status.setText("Reading the hardware…")

        def work():
            try:
                data = self.reader()
            except Exception:  # noqa: BLE001 - shown as "nothing found", the sensors still run
                data = {}
            try:
                local = self.local_reader()
            except Exception:  # noqa: BLE001
                local = {}
            self.bridge.read.emit(data, local)
        if self.sync:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()

    def _have_data(self, data: dict, local: dict):
        self.loading = False
        self.data, self.local = data or {}, local or {}
        self.root = hardware.build(self.data, self.local)
        self.cards = hardware.summary(self.data, self.local)
        self._fill_summary()
        self._fill_tree()
        self.read_at = time.time()
        if self.sampler is None:
            gpus = sorted((g for g in wmi.rows(self.data.get("gpu")) if isinstance(g, dict)),
                          key=lambda g: -(hardware.gpu_memory(self.data, g) or 0))
            disk_names = {f"PhysicalDrive{d['index']}": d["model"] for d in hardware.disks(self.data) if d["model"]}
            self.sampler = sensors.Sampler(sensors.default_sources([hardware.clean(g.get("Name")) for g in gpus],
                                                                   disk_names))
        if not self.timer.isActive():
            self.tick()
            self.timer.start(settings.get_int("interval", 2) * 1000)
        self._sync()

    def _fill_summary(self):
        for w in self.card_widgets:
            self.summary_grid.removeWidget(w)
            w.deleteLater()
        self.card_widgets = []
        places = {"cpu": (0, 0, 2, 1), "board": (0, 1, 1, 1), "memory": (1, 1, 1, 1), "gpu": (2, 0, 1, 1),
                  "drives": (2, 1, 1, 1), "windows": (3, 0, 1, 2)}
        for c in self.cards:
            w = self._card(c)
            self.card_widgets.append(w)
            self.summary_grid.addWidget(w, *places.get(c.section, (4, 0, 1, 2)))
        self.summary_grid.setColumnStretch(0, 1)
        self.summary_grid.setColumnStretch(1, 1)

    def _card(self, c: hardware.Card) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        v = QVBoxLayout(f)
        v.setContentsMargins(14, 10, 14, 12)
        v.setSpacing(6)
        h = QLabel(c.title)
        h.setProperty("role", "heading")
        h.setWordWrap(True)
        v.addWidget(h)
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(4)
        for i, (k, val) in enumerate(c.rows):
            g.addWidget(_field(k), i, 0, Qt.AlignmentFlag.AlignTop)
            lab = QLabel(val)
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            g.addWidget(lab, i, 1)
        g.setColumnStretch(1, 1)
        v.addLayout(g)
        if c.chips:
            chips = QWidget()
            cl = QGridLayout(chips)
            cl.setContentsMargins(0, 6, 0, 0)
            cl.setSpacing(4)
            for i, (name, on) in enumerate(c.chips):
                lab = QLabel(name)
                lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lab.setToolTip(f"{name}: {'supported' if on else 'not supported'}")
                lab.setStyleSheet(f"QLabel {{ background: {theme.qss_gradient() if on else theme.BUTTON}; color: "
                                  f"{'#FFFFFF' if on else theme.TEXT_DIM}; border-radius: 4px; padding: 3px 6px; "
                                  f"font-size: 10.5px; font-weight: 600; }}")
                cl.addWidget(lab, i // 6, i % 6)
            v.addWidget(chips)
        v.addStretch(1)
        return f

    def _fill_tree(self):
        current = self.tree.currentItem().text(0) if self.tree.currentItem() else None
        self.tree.clear()
        self.node_of: dict = {}
        chosen = None

        def add(node: hardware.Node, parent):
            nonlocal chosen
            it = QTreeWidgetItem([node.name])
            it.setIcon(0, widgets.line_icon(node.icon, theme.LED_ORANGE if parent is None else None, 18))
            self.node_of[id(it)] = node
            it.setData(0, KEY_ROLE, id(it))
            if parent is None:
                self.tree.addTopLevelItem(it)
            else:
                parent.addChild(it)
            if node.name == current:
                chosen = it
            for c in node.children:
                add(c, it)
            return it
        top = add(self.root, None)
        self.tree.expandAll()
        self.tree.setCurrentItem(chosen or top)

    def node(self) -> hardware.Node | None:
        it = self.tree.currentItem()
        return self.node_of.get(it.data(0, KEY_ROLE)) if it is not None else None

    def show_node(self):
        n = self.node()
        self.props.clear()
        if n is None:
            return
        groups = n.groups
        if not groups and n.children:              # a section: what's in it, one line each
            groups = [(n.name.upper(), [(c.name, joined_first(c)) for c in n.children])]
        for g, rows in groups:
            gi = QTreeWidgetItem([g.upper()])
            f = gi.font(0)
            f.setWeight(QFont.Weight.DemiBold)
            gi.setFont(0, f)
            gi.setFirstColumnSpanned(False)
            self.props.addTopLevelItem(gi)
            for k, v in rows:
                gi.addChild(QTreeWidgetItem([k, v]))
        self.props.expandAll()
        self._sync()

    # ================================================================ sensors
    def tick(self):
        if self.sampler is None or self._sampling:
            return
        self._sampling = True

        def work():
            try:
                self.sampler.sample()
            finally:
                self.bridge.sampled.emit()
        if self.sync:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()

    def _show_sensors(self):
        self._sampling = False
        f = settings.get("units", "c") == "f"
        icons = {"CPU": "app", "Memory": "table", "GPU": "screen", "Drives": "drive", "Network": "network",
                 "Battery": "app", "Motherboard": "drive", "Temperatures": "chart"}
        for group, readings in self.sampler.groups():
            gi = self.sens_groups.get(group)
            if gi is None:
                gi = QTreeWidgetItem([group])
                icon = next((v for k, v in icons.items() if group.startswith(k)), "chart")
                gi.setIcon(0, widgets.line_icon(icon, theme.LED_ORANGE, 16))
                font = gi.font(0)
                font.setWeight(QFont.Weight.DemiBold)
                gi.setFont(0, font)
                self.sens.addTopLevelItem(gi)
                gi.setExpanded(True)
                self.sens_groups[group] = gi
            for r in readings:
                key = (r.group, r.name)
                it = self.sens_items.get(key)
                if it is None:
                    it = QTreeWidgetItem([r.name, "", "", "", "", ""])
                    it.setData(5, KEY_ROLE, key)
                    for c in range(1, 5):
                        it.setTextAlignment(c, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    gi.addChild(it)
                    self.sens_items[key] = it
                it.setForeground(1, QColor(theme.LED_ORANGE))
                for c, v in ((1, r.current), (2, r.low), (3, r.high), (4, r.average)):
                    it.setText(c, sensors.show(v, r.kind, f))
        self.sens.viewport().update()
        self._sync()

    def reset_sensors(self):
        if self.sampler is not None:
            self.sampler.reset()
            if self.sampler.readings:
                self._show_sensors()

    def toggle_log(self, on: bool) -> bool:
        if self.sampler is None:
            self.log_button.setChecked(False)
            return False
        if not on:
            self.sampler.stop_log()
            self.log_button.setChecked(False)
            self._sync()
            return False
        name = f"{self._computer()} sensors {time.strftime('%Y-%m-%d %H%M')}.csv"
        path = self._ask("log_file", os.path.join(os.path.expanduser("~"), "Documents", name))
        if not path:
            self.log_button.setChecked(False)
            return False
        self.sampler.start_log(path)
        self.log_button.setChecked(True)
        self._sync()
        return True

    # ================================================================ report and copy
    def _computer(self) -> str:
        return self.root.name if self.root else "PC"

    def report_text(self) -> str:
        return hardware.report(self.root or hardware.Node("PC"), self.cards, __version__)

    def save_report(self) -> str | None:
        if self.root is None:
            return None
        path = self._ask("report_file", os.path.join(os.path.expanduser("~"), "Documents",
                                                     f"{self._computer()} hardware report.txt"))
        if not path:
            return None
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write(self.report_text())
        except OSError as e:
            self._say("error", f"The report couldn't be saved:\n{e}")
            return None
        self._say("info", f"Report saved: {path}")
        return path

    def copy_text(self) -> str:
        page = PAGES[self.pages.currentIndex()]
        if page == "summary":
            out = []
            for c in self.cards:
                out.append(c.title)
                out += [f"    {k}: {v}" for k, v in c.rows]
            return "\r\n".join(out)
        if page == "details":
            items = self.props.selectedItems()
            if items and items[0].parent() is not None:
                return f"{items[0].text(0)}: {items[0].text(1)}"
            n = self.node()
            if n is None:
                return ""
            out = [n.name]
            for g, rows in n.groups:
                out.append(f"  [{g}]")
                out += [f"    {k}: {v}" for k, v in rows]
            return "\r\n".join(out)
        items = self.sens.selectedItems()
        f = settings.get("units", "c") == "f"
        if items and items[0].data(5, KEY_ROLE):
            r = self.sampler.readings[items[0].data(5, KEY_ROLE)]
            return f"{r.group}  ·  {r.name}: {sensors.show(r.current, r.kind, f)}"
        return "\r\n".join(f"{r.group}  ·  {r.name}: {sensors.show(r.current, r.kind, f)}"
                           for r in (self.sampler.list() if self.sampler else []))

    def copy(self):
        text = self.copy_text()
        if text:
            QApplication.clipboard().setText(text)
            self.status.setText("Copied.")

    # ================================================================ pages, options, admin
    def show_page(self, page: str):
        self.pages.setCurrentIndex(PAGES.index(page))
        for p in PAGES:
            self.keys[p].setDown(False)
            if f"page_{p}" in getattr(self, "acts", {}):
                self.acts[f"page_{p}"].setChecked(p == page)
        self._sync()

    def options(self) -> bool:
        if not self._ask("options"):
            return False
        self.timer.setInterval(settings.get_int("interval", 2) * 1000)
        if self.sampler is not None and self.sampler.readings:
            self._show_sensors()
        return True

    def as_admin(self) -> bool:
        """Drive health and temperatures need administrator rights: start again with Windows' prompt."""
        if sys.platform != "win32":
            return False
        if "elevate" in self.answers:
            return self.answers["elevate"]()
        import ctypes
        args = "" if getattr(sys, "frozen", False) else "-m pr7hw"
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
        if r > 32:
            self.close()
            return True
        return False

    def check_updates(self):
        from . import update_ui
        update_ui.check(self, manual=True)

    # ================================================================ status
    def _sync(self):
        page = PAGES[self.pages.currentIndex()]
        admin = sensors.is_admin()
        if self.loading:
            text = "Reading the hardware…"
        elif page == "summary":
            ago = int(time.time() - getattr(self, "read_at", time.time()))
            text = f"SYSTEM SUMMARY  ·  read {ago} s ago" if self.root else "SYSTEM SUMMARY"
        elif page == "details":
            n = self.node()
            sec = next((s.name for s in (self.root.children if self.root else []) if n is not None and
                        any(x is n for _d, x in s.walk())), "")
            text = "  ·  ".join(x for x in ("DETAILS" if not sec else sec.upper(), n.name if n and n.name != sec
                                              else "") if x)
        else:
            run = int(time.time() - self.sampler.started) if self.sampler else 0
            text = (f"SENSORS  ·  every {settings.get_int('interval', 2)} s  ·  running {hardware.duration(run)}"
                    + (f"  ·  logging to {os.path.basename(self.sampler.log_path)}"
                       if self.sampler and self.sampler.log_path else ""))
        self.status.setText(text)
        if sys.platform == "win32":
            self.state.setText("Administrator: yes (drive health and temperatures shown)" if admin else
                               "Administrator: no (AS ADMIN shows drive health and temperatures)")
        else:
            self.state.setText("")
        nvidia = bool(sensors.nvidia_smi())
        self.sensor_note.setText("GPU temperature through nvidia-smi" if nvidia else
                                 "CPU temperature: only where the board reports an ACPI thermal zone")
        self.acts["log"].setText("Stop Logging" if self.sampler and self.sampler.log_path else "Log Sensors to CSV…")

    # ================================================================ asking
    def _ask(self, kind: str, payload=None):
        if kind in self.answers:
            a = self.answers[kind]
            return a(payload) if callable(a) else a
        if kind == "report_file":
            return QFileDialog.getSaveFileName(self, "Save Report", payload, "Text files (*.txt)")[0]
        if kind == "log_file":
            return QFileDialog.getSaveFileName(self, "Log Sensors to CSV", payload, "CSV files (*.csv)")[0]
        if kind == "options":
            d = OptionsDialog(self)
            if d.exec():
                d.save()
                return True
            return False
        return None

    def _say(self, kind: str, text: str):
        self.said.append((kind, text))
        if "say" in self.answers:
            self.answers["say"](kind, text)
            return
        icon = QMessageBox.Icon.Warning if kind in ("error", "warning") else QMessageBox.Icon.Information
        QMessageBox(icon, "PR7-HW", text, parent=self).exec()

    def closeEvent(self, e):
        self.timer.stop()
        if self.sampler is not None:
            self.sampler.stop_log()
        super().closeEvent(e)


def joined_first(n: hardware.Node) -> str:
    """A device's one-line description for its section's list: its first two properties."""
    for _g, rows in n.groups:
        return "  ·  ".join(v for _k, v in rows[:2] if v)
    return ""
