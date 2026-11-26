# PyInstaller build of PR7-HW: pyinstaller pr7hw.spec  ->  dist/PR7-HW/PR7-HW.exe  (folder build: starts fast)
#
# Windows Defender judges unknown, unsigned programs partly by how they look: a PyInstaller program with no file
# details and the stock (shared, much-copied) starter is a common false positive. So the .exe carries proper
# version details (Properties > Details), and CI builds PyInstaller's starter from source (see build.yml).
import re
import sys
from pathlib import Path


root = Path(SPECPATH)
version = re.search(r'__version__ = "(.+?)"', (root / "pr7hw" / "__init__.py").read_text()).group(1)
nums = tuple(int(x) for x in (version.split(".") + ["0", "0", "0"])[:4])
details = None
if sys.platform == "win32":  # version resources exist only in Windows programs
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
    details = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "Paragon"),
            StringStruct("FileDescription", "Paragon PR7-HW hardware information"),
            StringStruct("FileVersion", version),
            StringStruct("InternalName", "PR7-HW"),
            StringStruct("LegalCopyright", "Paragon"),
            StringStruct("OriginalFilename", "PR7-HW.exe"),
            StringStruct("ProductName", "Paragon PR7-HW"),
            StringStruct("ProductVersion", version)])]),
              VarFileInfo([VarStruct("Translation", [1033, 1200])])])

a = Analysis(
    [str(root / "tools" / "launcher.py")],
    pathex=[str(root)],
    datas=[(str(root / "pr7hw" / "fonts"), "pr7hw/fonts"), (str(root / "pr7hw" / "icons"), "pr7hw/icons")],
    # QtNetwork's local socket brings the running PR7-HW to the front when it's started again.
    hiddenimports=["PySide6.QtNetwork"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
              "PySide6.QtPrintSupport", "PIL"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PR7-HW", console=False, upx=False,  # no UPX: packed
          icon=str(root / "pr7hw" / "icons" / "app.ico"), version=details)          # .exes look worse still
coll = COLLECT(exe, a.binaries, a.datas, name="PR7-HW", upx=False)
