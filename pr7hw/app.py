"""Start PR7-HW.

    PR7-HW.exe                     the window (one per user: a second start brings the first to the front)
    PR7-HW.exe --report OUT.txt    read the hardware and write the report, no window (CI; scripts)
    PR7-HW.exe --version
    PR7-HW.exe --selftest OUT.json   read this PC's hardware through the real window offscreen, sample the sensors
                                     twice, save a report and a sensor log; writes what was found (CI checks the
                                     installed exe on the runner)
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import sys

TIMEOUT_MS = 1500


def server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return "Paragon-PR7-HW-" + hashlib.sha1(user.encode()).hexdigest()[:12]


def hand_over() -> bool:
    from PySide6.QtNetwork import QLocalSocket
    s = QLocalSocket()
    s.connectToServer(server_name())
    if not s.waitForConnected(TIMEOUT_MS):
        return False
    s.write(b'{"show": true}\n')
    s.flush()
    s.waitForBytesWritten(TIMEOUT_MS)
    if not s.waitForDisconnected(TIMEOUT_MS):
        s.disconnectFromServer()
    return True


def listen(window):
    """Later starts hand over to this window (PR7-R's hand-off, with its Windows fix: data may already be waiting)."""
    from PySide6.QtNetwork import QLocalServer
    server = QLocalServer(window)
    QLocalServer.removeServer(server_name())
    if not server.listen(server_name()):
        return None

    def connection():
        sock = server.nextPendingConnection()
        if sock is None:
            return
        buf = bytearray()
        done = []

        def read():
            buf.extend(bytes(sock.readAll()))
            if buf.endswith(b"\n") and not done:
                done.append(True)
                window.showNormal()
                window.raise_()
                window.activateWindow()
                sock.disconnectFromServer()
        sock.readyRead.connect(read)
        sock.disconnected.connect(read)
        if sock.bytesAvailable():
            read()
    server.newConnection.connect(connection)
    window.instance_server = server
    return server


def _offscreen_settings():
    import tempfile
    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())


def selftest(out: str, reader=None) -> int:
    import tempfile
    import time
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    result = {}
    try:
        from PySide6.QtGui import QFontDatabase
        from PySide6.QtWidgets import QApplication
        _offscreen_settings()
        from . import __version__, theme
        from .main_window import MainWindow
        app = QApplication.instance() or QApplication(sys.argv[:1])
        theme.load_fonts()
        w = MainWindow(reader=reader, sync=True)
        tmp = tempfile.mkdtemp()
        w.answers.update({"say": lambda k, t: None, "report_file": os.path.join(tmp, "report.txt"),
                          "log_file": os.path.join(tmp, "sensors.csv")})
        w.resize(1320, 860)
        w.show()
        w.refresh()
        w.toggle_log(True)
        time.sleep(1.1)
        w.tick()
        for p in ("summary", "details", "sensors"):
            w.show_page(p)
            app.processEvents()
            w.grab()
        report = w.save_report()
        cpu = w.root.find("Central processor").children if w.root and w.root.find("Central processor") else []
        drives = w.root.find("Drives").children if w.root and w.root.find("Drives") else []
        result = {"version": __version__, "cpu": cpu[0].name if cpu else "", "cores": os.cpu_count(),
                  "memory_modules": len(w.root.find("Memory").children) if w.root else 0,
                  "drives": [d.name for d in drives], "cards": [c.title for c in w.cards],
                  "sensors": [f"{r.group}  ·  {r.name}" for r in w.sampler.list()],
                  "samples": w.sampler.samples, "report": os.path.getsize(report) if report else 0,
                  "log_lines": len(open(os.path.join(tmp, "sensors.csv"), encoding="utf-8-sig").read().splitlines())
                  if os.path.exists(os.path.join(tmp, "sensors.csv")) else 0,
                  "windows": w.data.get("os") is not None and bool(w.data.get("os")),
                  "fonts": "Inter" in QFontDatabase.families()}
        w.close()
    except Exception as e:  # noqa: BLE001 - reported in the output
        result = {"error": f"{type(e).__name__}: {e}"}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh)
    return 0 if "cpu" in result else 1


def write_report(out: str) -> int:
    from . import __version__, hardware, wmi
    from .main_window import local_info
    data = wmi.read()
    local = local_info()
    text = hardware.report(hardware.build(data, local), hardware.summary(data, local), __version__)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        f.write(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv[:1] == ["--version"]:
            from . import __version__
            print(__version__)
            return 0
        if argv[:1] == ["--selftest"] and len(argv) == 2:
            return selftest(argv[1])
        if argv[:1] == ["--report"] and len(argv) == 2:
            return write_report(argv[1])
    except Exception:  # noqa: BLE001 - a command-line mode never waits on an error box (PR7-IS's lesson)
        return 1
    from PySide6.QtWidgets import QApplication

    from . import finish, settings, theme
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setOrganizationName("Paragon")
    app.setApplicationName("PR7-HW")
    if hand_over():
        return 0
    theme.set_finish(finish.start(settings.get("finish", "obsidian")))
    theme.load_fonts()
    from PySide6.QtGui import QFont, QIcon
    app.setFont(QFont("Inter", 10))
    icon = os.path.join(os.path.dirname(__file__), "icons", "app.ico")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    from .main_window import MainWindow
    w = MainWindow()
    w.show()
    w.refresh()
    from PySide6.QtCore import QTimer
    follow = QTimer(w)                            # one finish for the family: follow another app's switch
    follow.timeout.connect(lambda: finish.follow(theme.FINISH, w.set_finish))
    follow.start(2000)
    listen(w)
    from . import update_ui
    update_ui.start(w)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
