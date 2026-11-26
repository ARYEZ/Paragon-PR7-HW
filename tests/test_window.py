import json
import os
import subprocess
import sys


from pr7hw import __version__, settings


def test_summary_page(window):
    assert window.pages.currentIndex() == 0
    titles = [c.title for c in window.cards]
    assert titles[0] == "AMD Ryzen 9 7950X 16-Core Processor" and "Drives" in titles
    assert len(window.card_widgets) == len(window.cards)
    texts = [lab.text() for w in window.card_widgets for lab in w.findChildren(type(window.status))]
    assert "16 / 32" in texts and "AVX-512" in texts and "6000 MT/s" in texts
    assert window.status.text().startswith("SYSTEM SUMMARY")
    window.grab()


def test_details_tree_and_properties(window):
    window.show_page("details")
    top = window.tree.topLevelItem(0)
    assert top.text(0) == "STUDIO-PC" and top.childCount() == 10
    drives = next(top.child(i) for i in range(top.childCount()) if top.child(i).text(0) == "Drives")
    window.tree.setCurrentItem(drives.child(0))
    groups = [window.props.topLevelItem(i).text(0) for i in range(window.props.topLevelItemCount())]
    assert groups == ["DRIVE", "HEALTH", "VOLUMES"]
    health = window.props.topLevelItem(1)
    assert {health.child(i).text(0): health.child(i).text(1) for i in range(health.childCount())}["Wear"] == "3 % used"
    assert window.status.text() == "DRIVES  ·  Samsung SSD 990 PRO 2TB"
    window.props.setCurrentItem(health.child(0))
    health.child(0).setSelected(True)
    window.copy()
    from PySide6.QtWidgets import QApplication
    assert QApplication.clipboard().text() == "Status: Healthy"
    window.tree.setCurrentItem(drives)                      # a section lists its devices
    rows = window.props.topLevelItem(0)
    assert rows.childCount() == 3 and rows.child(0).text(1).startswith("Samsung SSD 990 PRO 2TB")
    window.grab()


def test_sensors_update_min_max_average(window):
    window.show_page("sensors")
    window.tick()
    window.tick()                                            # three samples (the first came with the data)
    groups = [window.sens.topLevelItem(i).text(0) for i in range(window.sens.topLevelItemCount())]
    assert groups == ["CPU", "GPU  ·  RTX 4080 SUPER", "Drives"]
    load = window.sens_items[("CPU", "Total load")]
    assert [load.text(c) for c in range(1, 5)] == ["33 %", "31 %", "33 %", "32 %"]
    temp = window.sens_items[("GPU  ·  RTX 4080 SUPER", "Temperature")]
    assert temp.text(1) == "63 °C"
    settings.set("units", "f")
    window.tick()
    assert temp.text(1) == "147 °F"                         # 64 °C
    settings.set("units", "c")
    window.reset_sensors()
    assert [load.text(c) for c in range(2, 5)] == ["34 %", "34 %", "34 %"]
    assert window.status.text().startswith("SENSORS  ·  every 2 s")
    window.grab()                                           # the graphs paint


def test_report_and_log(window, tmp_path):
    report = tmp_path / "report.txt"
    window.answers["report_file"] = str(report)
    assert window.save_report() == str(report)
    text = report.read_text(encoding="utf-8-sig")
    assert text.startswith(f"Paragon PR7-HW {__version__} report") and "Samsung SSD 990 PRO 2TB" in text
    assert window.said[-1] == ("info", f"Report saved: {report}")
    log = tmp_path / "sensors.csv"
    window.answers["log_file"] = str(log)
    assert window.toggle_log(True) and window.log_button.isChecked()
    window.tick()
    window.tick()
    window.toggle_log(False)
    window.tick()
    lines = log.read_text(encoding="utf-8-sig").splitlines()
    assert lines[0].startswith("Time,CPU  ·  Total load") and len(lines) == 3
    window.answers["log_file"] = ""                          # cancelled
    assert not window.toggle_log(True) and not window.log_button.isChecked()


def test_options_and_finish(window):
    def choose(_):
        settings.set("interval", 5)
        settings.set("units", "f")
        return True
    window.answers["options"] = choose
    assert window.options() and window.timer.interval() == 5000
    settings.set("units", "c")
    window.set_finish("aurora")
    assert window.finish_acts["aurora"].isChecked()
    window.grab()
    window.set_finish("obsidian")


def test_nothing_from_windows_still_works(qapp):
    from pr7hw import sensors
    from pr7hw.main_window import MainWindow
    w = MainWindow(reader=lambda: {}, sampler=sensors.Sampler([]), local=lambda: {}, sync=True)
    w.answers["say"] = lambda k, t: None
    w.refresh()
    assert w.root.name == "This PC" and w.cards
    w.show_page("details")
    w.grab()
    w.close()


def test_selftest_reads_this_machine(tmp_path):
    out = tmp_path / "self.json"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-m", "pr7hw", "--selftest", str(out)], cwd=root, capture_output=True,
                       text=True, timeout=180)
    got = json.loads(out.read_text())
    assert r.returncode == 0, (got, r.stderr)
    assert got["version"] == __version__ and got["fonts"] and got["samples"] >= 2
    assert "CPU  ·  Total load" in got["sensors"] and got["report"] > 500 and got["log_lines"] >= 2
    if sys.platform == "win32":                              # CI: the runner's real hardware through WMI
        assert got["cpu"] and got["memory_modules"] >= 0 and got["drives"] and got["windows"]


def test_second_start_hands_over():
    code = ("import sys, os; sys.path.insert(0, sys.argv[1]); os.environ['QT_QPA_PLATFORM']='offscreen';"
            "from PySide6.QtWidgets import QApplication; a = QApplication([]);"
            "from pr7hw import app; print(app.hand_over())")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-c", code, root], capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "False"
