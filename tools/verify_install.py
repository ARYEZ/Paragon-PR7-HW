"""Check a real install of PR7-HW-Setup.exe (CI, Windows): verify_install.py installed|uninstalled

`installed`: the files, the Start menu entry, the uninstall entry, and the installed exe's --selftest (the runner's
real hardware through WMI, the sensors sampled, a report and a sensor log written) and --report.
`uninstalled`: all of it gone."""
import json
import os
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

HKCU = winreg.HKEY_CURRENT_USER
APP = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "PR7-HW"
SHORTCUT = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Paragon PR7-HW.lnk"
UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{A805BD4F-97AC-4B0E-A173-574E7779EA1A}_is1"


def value(root, path, name=""):
    try:
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def check(ok, what, p):
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        p.append(what)


def installed():
    p = []
    exe = APP / "PR7-HW.exe"
    for f in (exe, APP / "unins000.exe", APP / "_internal" / "pr7hw" / "fonts" / "Inter-Regular.ttf"):
        check(f.is_file(), f"file {f}", p)
    check(SHORTCUT.is_file(), "Start menu shortcut", p)
    check(value(HKCU, UNINSTALL, "DisplayName") == "Paragon PR7-HW", "Installed apps entry", p)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out.json"
        try:
            subprocess.run([str(exe), "--selftest", str(out)], timeout=600, check=False)
        except subprocess.TimeoutExpired:
            pass
        got = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        check(bool(got.get("cpu")) and got.get("windows") is True and bool(got.get("drives")) and got.get("fonts"),
              f"the installed exe reads the CPU, Windows and the drives ({got.get('cpu')}, {got.get('drives')})", p)
        check(got.get("samples", 0) >= 2 and "CPU  ·  Total load" in got.get("sensors", []),
              f"it samples the sensors ({len(got.get('sensors', []))} readings)", p)
        check(got.get("report", 0) > 500 and got.get("log_lines", 0) >= 2, "it saves a report and a sensor log", p)
        if "error" in got:
            print(got["error"])
        rep = Path(d) / "report.txt"
        subprocess.run([str(exe), "--report", str(rep)], timeout=300, check=False)
        text = rep.read_text(encoding="utf-8-sig") if rep.exists() else ""
        check("SYSTEM SUMMARY" in text and "Central processor" in text, "--report writes the report", p)
    return p


def uninstalled():
    deadline = time.time() + 60
    while True:
        p = []
        check(not (APP / "PR7-HW.exe").exists(), "program files removed", p)
        check(not SHORTCUT.exists(), "Start menu shortcut removed", p)
        check(value(HKCU, UNINSTALL, "DisplayName") is None, "Installed apps entry removed", p)
        if not p or time.time() > deadline:
            return p
        print("... waiting for the uninstaller to finish")
        time.sleep(3)


if __name__ == "__main__":
    problems = {"installed": installed, "uninstalled": uninstalled}[sys.argv[1]]()
    print("\nALL OK" if not problems else f"\n{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
