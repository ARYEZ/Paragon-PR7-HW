# Paragon PR7-HW: notes for Claude

**Paragon PR7-HW** is the owner's personal hardware information tool: Python (**PySide6** + psutil) that **works the way
HWiNFO and CPU-Z work**, in the Paragon family look (PR7-Z ... PR7-UN, PR7-LN `ARYEZ/Paragon-PR7-LN`). Windows 10/11 x64
is the target; it runs on Linux for tests. The owner writes Python; explain the why.

## How it's built

- **No kernel driver** (HWiNFO / LibreHardwareMonitor ship one; WinRing0 is on Microsoft's vulnerable-driver blocklist
  and Defender flags it): only what Windows provides. CPU temperature only via ACPI thermal zones; no CPU power / fans.
- `pr7hw/wmi.py` (no Qt): `QUERIES` = one PowerShell run (`-EncodedCommand`), each class in its own try / catch, JSON
  out (PowerShell 5: one row = an object, dates "/Date(ms)/"; `rows`, `one`, `scalar`). `read(run=)`; tests use
  `tools/sample_pc.py` (the mock-up's made-up PC). GPU memory from the display class key's qwMemorySize (AdapterRAM
  stops at 4 GB); drive health from Get-StorageReliabilityCounter (administrator).
- `pr7hw/cpuinfo.py` (no Qt): features via IsProcessorFeaturePresent (FMA3 / BMI2 / AES-NI implied by AVX2) or
  /proc/cpuinfo; caches via GetLogicalProcessorInformation or /sys.
- `pr7hw/hardware.py` (no Qt): `build(data, local)` -> `Node` tree (groups of (property, value)), `summary` -> `Card`s,
  `report` (CRLF text); the SMBIOS / storage number tables; `size` (decimal drives) / `mem` (binary memory, near-whole
  rounded).
- `pr7hw/sensors.py` (no Qt): `Reading` (current, min, max, average, HISTORY deque), `Sampler(sources)`; a source returns
  [(group, name, value, kind)] and one that raises is skipped. psutil, PDH via ctypes (`Pdh`, GPU engines summed per
  LUID, adapters named by video memory order), nvidia-smi CSV, drive temperatures every 30 s, Linux sensors; CSV log.
- `pr7hw/main_window.py`: three pages (summary cards, details QTreeWidgets, sensors QTreeWidget + `Spark` delegate);
  reading and sampling on threads (`sync = True` inline); `reader`, `sampler`, `local` injectable; `_ask` / `answers`
  / `_say`; trees get the soft gradient band in `restyle` (the theme leaves it to painted bands).
- `pr7hw/app.py`: one window per user (QLocalSocket, PR7-R's Windows fix); command-line modes never let an error escape;
  `--selftest OUT.json` (the real hardware offscreen; CI on the installed exe), `--report OUT.txt`.
- Installer `installer/pr7hw.iss` (per user, AppId {A805BD4F-97AC-4B0E-A173-574E7779EA1A} permanent; desktopicon); CI
  installs it, `tools/verify_install.py installed|uninstalled`. Spec: file details, no UPX, PyInstaller's bootloader
  built in CI, Defender scan.
- Updates: `pr7hw/updates.py` / `update_ui.py` (the family's files, keep them in step); `family.py`: the family's AppIds
  (PR7-HW included). `pr7hw/finish.py`: the family's finish, the same file in every app.

## The look (family rules)

- Theme is PR7-LN's (OBSIDIAN + AURORA). Colours: the family's only (readings orange, instruction-set chips the family
  gradient); Inter; labels UPPER CASE; device names keep their case.
- The PR7-HW mark: PR7 `Logo.cpp` geometry plus H (PR7-HB's) and W (PR7-WM's); icon "7HW" by `tools/make_icon.py`,
  wizard art by `tools/make_installer_art.py`. Mock-up: `tools/mockup.py`. Check visuals with
  `QT_SCALE_FACTOR=2 python tools/screenshots.py OUT` (the made-up PC).

## Rules

- Behaviour questions: do what HWiNFO does (summary, the tree, sensors' Min / Max / Average, logging, report).
- Tests: `python -m pytest` (offscreen) on the made-up PC and this machine's real psutil readings; Windows CI adds real
  WMI, PDH and CPU calls. Never the real settings (conftest).
- Releases: bump `__version__` in `pr7hw/__init__.py` and add a `## x.y.z` section to CHANGELOG.md, then push: CI
  publishes that version by itself once every check has passed.
