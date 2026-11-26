"""Windows' answers (wmi.read) turned into what PR7-HW shows (no Qt): the details tree (`build` -> Node) and the System
Summary's cards (`summary` -> Card), the way HWiNFO groups them; `report` writes both as text.

Windows reports most things as numbers (SMBIOS memory types, storage bus types ...): the tables below name them.
`local` adds what Python reads itself: the CPU's caches and features (cpuinfo.py) and memory in use (psutil)."""

from __future__ import annotations

import datetime as dt
import re
import time
from dataclasses import dataclass, field

from .wmi import one, rows, scalar

MEMORY_TYPES = {20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 27: "LPDDR", 28: "LPDDR2", 29: "LPDDR3", 30: "LPDDR4",
                34: "DDR5", 35: "LPDDR5"}
FORM_FACTORS = {8: "DIMM", 12: "SO-DIMM", 13: "SO-DIMM"}
BUS_TYPES = {1: "SCSI", 2: "ATAPI", 3: "ATA", 6: "Fibre Channel", 7: "USB", 8: "RAID", 9: "iSCSI", 10: "SAS",
             11: "SATA", 12: "SD", 13: "MMC", 15: "File-backed virtual", 16: "Storage Spaces", 17: "NVMe"}
MEDIA_TYPES = {3: "HDD", 4: "SSD", 5: "SCM"}
HEALTH = {0: "Healthy", 1: "Warning", 2: "Unhealthy", 5: "Unknown"}
NET_STATUS = {0: "Disconnected", 1: "Connecting", 2: "Connected", 7: "Cable unplugged", 4: "Disconnecting"}
BATTERY_STATUS = {1: "Discharging", 2: "On mains power", 3: "Fully charged", 4: "Low", 5: "Critical", 6: "Charging",
                  7: "Charging (high)", 8: "Charging (low)", 9: "Charging (critical)"}
CHEMISTRY = {3: "Lead acid", 4: "Nickel cadmium", 5: "Nickel metal hydride", 6: "Lithium-ion", 8: "Lithium polymer"}


@dataclass
class Node:
    name: str
    icon: str = "app"
    groups: list = field(default_factory=list)       # [(GROUP, [(property, value)])]
    children: list = field(default_factory=list)
    section: str = ""

    def walk(self, depth: int = 0):
        yield depth, self
        for c in self.children:
            yield from c.walk(depth + 1)

    def find(self, name: str) -> "Node | None":
        return next((n for _d, n in self.walk() if n.name == name), None)


@dataclass
class Card:
    title: str
    rows: list
    section: str
    chips: list = field(default_factory=list)       # [(name, supported)]


# ---------------------------------------------------------------- formatting
def size(n, unit_base: int = 1000) -> str:
    """Bytes the way HWiNFO / Windows show them: drives in decimal (2.00 TB), memory in binary (64 GB)."""
    if n is None:
        return ""
    n = float(n)
    for unit in ("bytes", "KB", "MB", "GB", "TB", "PB"):
        if n < unit_base or unit == "PB":
            if unit == "bytes":
                return f"{int(n)} bytes"
            if n >= 100 or (unit_base == 1024 and abs(n - round(n)) < n * 0.0015) or n == int(n):
                return f"{round(n):.0f} {unit}"       # 15.99 GiB of video memory is "16 GB", as Windows says
            return f"{n:.2f} {unit}" if n < 10 else f"{n:.1f} {unit}"
        n /= unit_base
    return ""


def mem(n) -> str:
    return size(n, 1024)


def ghz(mhz) -> str:
    return f"{mhz / 1000:.2f} GHz".replace(".00 GHz", ".0 GHz") if mhz else ""


def date(v) -> dt.datetime | None:
    """PowerShell 5's JSON dates: "/Date(ms)/" (or {"value": ..., "DateTime": ...}); WMI's "yyyymmddHHMMSS.ffffff+zzz"."""
    if isinstance(v, dict):
        v = v.get("value") or v.get("DateTime")
    if not isinstance(v, str):
        return None
    m = re.search(r"/Date\((-?\d+)", v)
    if m:
        return dt.datetime.fromtimestamp(int(m.group(1)) / 1000, dt.timezone.utc)
    m = re.match(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", v)
    if m:
        return dt.datetime(*map(int, m.groups()), tzinfo=dt.timezone.utc)
    try:
        return dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def day(v) -> str:
    d = date(v)
    return d.strftime("%Y-%m-%d") if d else ""


def text(chars) -> str:
    """WmiMonitorID's names: arrays of character codes, padded with zeros."""
    if isinstance(chars, str):
        return chars.strip()
    return "".join(chr(c) for c in (chars or []) if c).strip()


def duration(seconds: float) -> str:
    d, rest = divmod(int(seconds), 86400)
    h, rest = divmod(rest, 3600)
    m = rest // 60
    return (f"{d} day{'s' if d != 1 else ''} {h} h" if d else f"{h} h {m} min" if h else f"{m} min")


def joined(*bits) -> str:
    return "  ·  ".join(str(b) for b in bits if b not in (None, ""))


def clean(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def kelvin10(v) -> float | None:
    return round(v / 10 - 273.15, 1) if isinstance(v, (int, float)) and v > 0 else None


# ---------------------------------------------------------------- the pieces
def cpu_rows(data: dict, local: dict) -> tuple[str, list, list]:
    c = one(data, "cpu")
    name = clean(c.get("Name")) or local.get("cpu_name", "") or "Processor"
    cores, threads = c.get("NumberOfCores"), c.get("NumberOfLogicalProcessors")
    count = len(rows(data.get("cpu")))
    caches = local.get("caches") or {}
    cache_text = joined(*(f"L{lvl} {mem(n)}" for lvl, n in sorted(caches.items()))) or joined(
        f"L2 {mem((c.get('L2CacheSize') or 0) * 1024 * count)}" if c.get("L2CacheSize") else "",
        f"L3 {mem((c.get('L3CacheSize') or 0) * 1024 * count)}" if c.get("L3CacheSize") else "")
    r = [("Cores / threads", f"{cores} / {threads}" + (f"  ·  {count} processors" if count > 1 else "") if cores else ""),
         ("Clock", joined(f"{ghz(c.get('MaxClockSpeed'))} base" if c.get("MaxClockSpeed") else "",
                          f"now {ghz(local.get('cpu_mhz') or c.get('CurrentClockSpeed'))}"
                          if (local.get("cpu_mhz") or c.get("CurrentClockSpeed")) else "")),
         ("Caches", cache_text), ("Socket", clean(c.get("SocketDesignation"))),
         ("Family", joined(clean(c.get("Caption")).replace("AMD64 ", "").replace("Intel64 ", ""),
                           clean(c.get("Manufacturer")))),
         ("Virtualisation", {True: "On in the firmware", False: "Off in the firmware"}.get(
             c.get("VirtualizationFirmwareEnabled"), ""))]
    from .cpuinfo import FEATURES
    feats = local.get("features") or set()
    chips = [(f, f in feats) for f in FEATURES] if feats else []
    return name, [x for x in r if x[1]], chips


def memory_modules(data: dict) -> list[dict]:
    return [m for m in rows(data.get("memory")) if isinstance(m, dict)]


def memory_kind(m: dict) -> str:
    return MEMORY_TYPES.get(m.get("SMBIOSMemoryType"), "")


def module_name(m: dict) -> str:
    return clean(m.get("DeviceLocator") or m.get("BankLabel") or "Module")


def disks(data: dict) -> list[dict]:
    """Win32_DiskDrive joined with MSFT_PhysicalDisk (bus, media, health), the health counters and the partitions."""
    phys = {str(p.get("DeviceId")): p for p in rows(data.get("physical_disks")) if isinstance(p, dict)}
    rel = {str(r.get("DeviceId")): r for r in rows(data.get("reliability")) if isinstance(r, dict)}
    parts = [p for p in rows(data.get("partitions")) if isinstance(p, dict)]
    vols = {str(v.get("DeviceID", "")).rstrip(":"): v for v in rows(data.get("volumes")) if isinstance(v, dict)}
    out = []
    for d in sorted((d for d in rows(data.get("disks")) if isinstance(d, dict)), key=lambda d: d.get("Index", 0)):
        idx = str(d.get("Index"))
        p, r = phys.get(idx, {}), rel.get(idx, {})
        mine = sorted((x for x in parts if str(x.get("DiskNumber")) == idx), key=lambda x: x.get("PartitionNumber", 0))
        media = MEDIA_TYPES.get(p.get("MediaType"), "")
        if media == "HDD" and p.get("SpindleSpeed") and p["SpindleSpeed"] not in (0, 4294967295):
            media = f"HDD {p['SpindleSpeed']} rpm"
        out.append({"index": idx, "model": clean(d.get("Model") or p.get("FriendlyName")), "serial": clean(d.get("SerialNumber")),
                    "firmware": clean(d.get("FirmwareRevision")), "size": d.get("Size") or p.get("Size"),
                    "bus": BUS_TYPES.get(p.get("BusType"), clean(d.get("InterfaceType"))), "media": media,
                    "health": HEALTH.get(p.get("HealthStatus"), ""), "temp": r.get("Temperature") or None,
                    "temp_max": r.get("TemperatureMax") or None, "wear": r.get("Wear"),
                    "hours": r.get("PowerOnHours"), "starts": r.get("StartStopCycleCount"),
                    "errors": (r.get("ReadErrorsTotal") or 0) + (r.get("WriteErrorsTotal") or 0) if r else None,
                    "partitions": [(x.get("Type") or "Partition", x.get("DriveLetter"), x.get("Size")) for x in mine],
                    "volumes": [vols[str(x.get("DriveLetter"))] for x in mine if str(x.get("DriveLetter") or "") in vols]})
    return out


def gpu_memory(data: dict, g: dict) -> int | None:
    for m in rows(data.get("gpu_memory")):
        if isinstance(m, dict) and clean(m.get("Name")) == clean(g.get("Name")) and m.get("Bytes"):
            return int(m["Bytes"])
    ram = g.get("AdapterRAM")
    return int(ram) if ram else None


def monitors(data: dict) -> list[dict]:
    out = []
    for m in rows(data.get("monitors")):
        if isinstance(m, dict):
            out.append({"name": text(m.get("UserFriendlyName")) or "Monitor", "maker": text(m.get("ManufacturerName")),
                        "serial": text(m.get("SerialNumberID")), "year": m.get("YearOfManufacture")})
    return out


def windows_name(data: dict) -> str:
    o = one(data, "os")
    cap = clean(o.get("Caption")).replace("Microsoft ", "")
    # Windows 11 still reports version 10.0; build 22000+ is 11 (older captions may say 10)
    if cap.startswith("Windows 10") and str(o.get("BuildNumber", "0")).isdigit() and int(o["BuildNumber"]) >= 22000:
        cap = cap.replace("Windows 10", "Windows 11", 1)
    return joined(cap, scalar(data, "display_version")).replace("  ·  ", " ") if cap else ""


def uptime(data: dict, now: float | None = None) -> str:
    boot = date(one(data, "os").get("LastBootUpTime"))
    if not boot:
        return ""
    return duration((now or time.time()) - boot.timestamp())


def temperature(c) -> str:
    return f"{c:.0f} °C" if isinstance(c, (int, float)) else ""


# ---------------------------------------------------------------- the details tree
def build(data: dict, local: dict | None = None) -> Node:
    local = local or {}
    o, sysinfo = one(data, "os"), one(data, "system")
    root = Node(clean(o.get("CSName") or sysinfo.get("Name") or local.get("computer") or "This PC"), "desktop",
                section="computer")
    root.groups = [("COMPUTER", [(k, v) for k, v in (
        ("Name", root.name), ("Maker", clean(sysinfo.get("Manufacturer"))), ("Model", clean(sysinfo.get("Model"))),
        ("Type", sysinfo.get("SystemType")), ("Windows", windows_name(data)),
        ("Memory", mem(sysinfo.get("TotalPhysicalMemory")))) if v])]
    # CPU
    name, crows, chips = cpu_rows(data, local)
    cpu = Node("Central processor", "app", section="cpu")
    c = one(data, "cpu")
    feat = [("Instruction sets", ", ".join(n for n, on in chips if on))] if chips else []
    pid = [("Processor ID", c["ProcessorId"])] if c.get("ProcessorId") else []
    cpu.children.append(Node(name, "app", [("PROCESSOR", crows + pid + feat)], section="cpu"))
    root.children.append(cpu)
    # board and BIOS
    b, bios = one(data, "board"), one(data, "bios")
    board = Node("Motherboard", "drive", section="board")
    if b:
        board.children.append(Node(clean(b.get("Product")) or "Motherboard", "drive", [("MOTHERBOARD", [
            (k, v) for k, v in (("Maker", clean(b.get("Manufacturer"))), ("Model", clean(b.get("Product"))),
                                ("Version", clean(b.get("Version"))), ("Serial number", clean(b.get("SerialNumber"))))
            if v])], section="board"))
    if bios:
        sb = scalar(data, "secure_boot")
        tpm = one(data, "tpm")
        board.children.append(Node("BIOS", "drive", [("FIRMWARE", [(k, v) for k, v in (
            ("Maker", clean(bios.get("Manufacturer"))), ("Version", clean(bios.get("SMBIOSBIOSVersion"))),
            ("Date", day(bios.get("ReleaseDate"))),
            ("SMBIOS", f"{bios.get('SMBIOSMajorVersion')}.{bios.get('SMBIOSMinorVersion')}"
             if bios.get("SMBIOSMajorVersion") is not None else ""),
            ("Secure Boot", {True: "On", False: "Off"}.get(sb, "")),
            ("TPM", joined(str(tpm.get("SpecVersion", "")).split(",")[0], clean(tpm.get("ManufacturerIdTxt")))
             if tpm else "")) if v])], section="board"))
    root.children.append(board)
    # memory
    memory = Node("Memory", "table", section="memory")
    for m in memory_modules(data):
        memory.children.append(Node(module_name(m), "table", [("MODULE", [(k, v) for k, v in (
            ("Size", mem(m.get("Capacity"))), ("Type", joined(memory_kind(m), FORM_FACTORS.get(m.get("FormFactor"), ""))),
            ("Speed", f"{m.get('ConfiguredClockSpeed') or m.get('Speed')} MT/s"
             if (m.get("ConfiguredClockSpeed") or m.get("Speed")) else ""),
            ("Rated speed", f"{m.get('Speed')} MT/s" if m.get("Speed") else ""),
            ("Maker", clean(m.get("Manufacturer"))), ("Part number", clean(m.get("PartNumber"))),
            ("Serial number", clean(m.get("SerialNumber"))),
            ("Voltage", f"{m['ConfiguredVoltage'] / 1000:.2f} V" if m.get("ConfiguredVoltage") else ""),
            ("Bank", clean(m.get("BankLabel")))) if v])], section="memory"))
    slots = one(data, "memory_slots")
    memory.groups = [("MEMORY", [(k, v) for k, v in (
        ("Installed", mem(sum(int(m.get("Capacity") or 0) for m in memory_modules(data)))),
        ("Slots", f"{slots.get('MemoryDevices')}, {len(memory_modules(data))} used" if slots.get("MemoryDevices") else ""),
        ("Most the board takes", mem((slots.get("MaxCapacityEx") or 0) * 1024) if slots.get("MaxCapacityEx") else ""),
        ("In use", local.get("mem_text", ""))) if v])]
    root.children.append(memory)
    # graphics, monitors
    gfx = Node("Graphics", "screen", section="gpu")
    for g in rows(data.get("gpu")):
        if not isinstance(g, dict):
            continue
        gm = gpu_memory(data, g)
        res = (f"{g['CurrentHorizontalResolution']} × {g['CurrentVerticalResolution']}"
               + (f" at {g['CurrentRefreshRate']} Hz" if g.get("CurrentRefreshRate") else "")
               if g.get("CurrentHorizontalResolution") else "")
        gfx.children.append(Node(clean(g.get("Name")) or "Display adapter", "screen", [("ADAPTER", [(k, v) for k, v in (
            ("Name", clean(g.get("Name"))), ("Maker", clean(g.get("AdapterCompatibility"))),
            ("Memory", mem(gm) if gm else ""), ("Chip", clean(g.get("VideoProcessor"))),
            ("Driver", joined(clean(g.get("DriverVersion")), day(g.get("DriverDate")))), ("Display", res)) if v])],
            section="gpu"))
    root.children.append(gfx)
    mons = monitors(data)
    if mons:
        mon = Node("Monitors", "desktop", section="monitors")
        for m in mons:
            mon.children.append(Node(m["name"], "desktop", [("MONITOR", [(k, v) for k, v in (
                ("Name", m["name"]), ("Maker code", m["maker"]), ("Serial number", m["serial"]),
                ("Made in", str(m["year"] or ""))) if v])], section="monitors"))
        root.children.append(mon)
    # drives
    drv = Node("Drives", "drive", section="drives")
    for d in disks(data):
        drive_rows = [(k, v) for k, v in (
            ("Model", d["model"]), ("Serial number", d["serial"]), ("Firmware", d["firmware"]),
            ("Capacity", f"{size(d['size'])} ({int(d['size']):,} bytes)" if d["size"] else ""),
            ("Interface", d["bus"]), ("Media", d["media"]),
            ("Partitions", joined(*(f"{(t or '').replace('Basic', 'Data')} {letter + ': ' if letter else ''}{size(s)}"
                                    for t, letter, s in d["partitions"])))) if v]
        groups = [("DRIVE", drive_rows)]
        health = [(k, v) for k, v in (
            ("Status", d["health"]),
            ("Temperature", joined(temperature(d["temp"]), f"highest seen {temperature(d['temp_max'])}"
                                   if d["temp_max"] else "")),
            ("Wear", f"{d['wear']} % used" if d["wear"] is not None else ""),
            ("Power on", joined(f"{d['hours']:,} hours" if d["hours"] else "", f"{d['starts']:,} starts"
                                if d["starts"] else "")),
            ("Read / write errors", str(d["errors"]) if d["errors"] is not None else "")) if v]
        if health:
            groups.append(("HEALTH", health))
        vols = [(f"{v.get('DeviceID')} {clean(v.get('VolumeName'))}".strip(),
                 joined(v.get("FileSystem"), f"{size(v.get('Size'))}, {size(v.get('FreeSpace'))} free")) for v in d["volumes"]]
        if vols:
            groups.append(("VOLUMES", vols))
        drv.children.append(Node(d["model"] or f"Disk {d['index']}", "drive", groups, section="drives"))
    root.children.append(drv)
    # network, audio, USB, battery
    net = Node("Network", "network", section="network")
    for a in rows(data.get("network")):
        if isinstance(a, dict):
            net.children.append(Node(clean(a.get("Name")), "network", [("ADAPTER", [(k, v) for k, v in (
                ("Name", clean(a.get("Name"))), ("Maker", clean(a.get("Manufacturer"))),
                ("Connection", clean(a.get("NetConnectionID"))),
                ("State", NET_STATUS.get(a.get("NetConnectionStatus"), "")),
                ("Speed", rate(a.get("Speed")) if a.get("NetConnectionStatus") == 2 else ""),
                ("MAC address", a.get("MACAddress"))) if v])], section="network"))
    root.children.append(net)
    audio = [a for a in rows(data.get("audio")) if isinstance(a, dict)]
    if audio:
        au = Node("Audio", "volume", section="audio")
        for a in audio:
            au.children.append(Node(clean(a.get("Name")), "volume", [("DEVICE", [(k, v) for k, v in (
                ("Name", clean(a.get("Name"))), ("Maker", clean(a.get("Manufacturer"))),
                ("State", clean(a.get("Status")))) if v])], section="audio"))
        root.children.append(au)
    usb = [u for u in rows(data.get("usb")) if isinstance(u, dict)]
    if usb:
        n_dev = scalar(data, "usb_devices")
        us = Node("USB", "usb", [("USB", [("Controllers", str(len(usb)))] + ([("Devices", str(n_dev))] if n_dev else []))],
                  section="usb")
        for u in usb:
            us.children.append(Node(clean(u.get("Name")), "usb", [("CONTROLLER", [(k, v) for k, v in (
                ("Name", clean(u.get("Name"))), ("Maker", clean(u.get("Manufacturer")))) if v])], section="usb"))
        root.children.append(us)
    bat = [x for x in rows(data.get("battery")) if isinstance(x, dict)]
    if bat:
        bn = Node("Battery", "app", section="battery")
        for x in bat:
            wear = ""
            if x.get("DesignCapacity") and x.get("FullChargeCapacity"):
                wear = f"{100 - 100 * x['FullChargeCapacity'] / x['DesignCapacity']:.0f} % worn"
            bn.children.append(Node(clean(x.get("Name")) or "Battery", "app", [("BATTERY", [(k, v) for k, v in (
                ("Charge", f"{x.get('EstimatedChargeRemaining')} %" if x.get("EstimatedChargeRemaining") is not None else ""),
                ("State", BATTERY_STATUS.get(x.get("BatteryStatus"), "")),
                ("Chemistry", CHEMISTRY.get(x.get("Chemistry"), "")), ("Wear", wear)) if v])], section="battery"))
        root.children.append(bn)
    # Windows
    win = Node(windows_name(data) or "Windows", "window", [("WINDOWS", [(k, v) for k, v in (
        ("Edition", windows_name(data)),
        ("Build", joined(f"{o.get('BuildNumber')}.{scalar(data, 'ubr')}" if scalar(data, "ubr") is not None
                         else o.get("BuildNumber"), o.get("OSArchitecture"))),
        ("Installed", day(o.get("InstallDate"))), ("Started", day(o.get("LastBootUpTime"))),
        ("Up for", uptime(data)), ("Computer name", clean(o.get("CSName"))),
        ("Administrator", {True: "Yes", False: "No (drive health needs it)"}.get(scalar(data, "admin"), ""))) if v])],
        section="windows")
    root.children.append(Node("Windows", "window", children=[win], section="windows"))
    return root


def rate(bits) -> str:
    if not bits:
        return ""
    b = float(bits)
    return f"{b / 1e9:g} Gb/s" if b >= 1e9 else f"{b / 1e6:g} Mb/s"


# ---------------------------------------------------------------- the summary page
def summary(data: dict, local: dict | None = None) -> list[Card]:
    local = local or {}
    cards = []
    name, crows, chips = cpu_rows(data, local)
    cards.append(Card(name, crows, "cpu", chips))
    b, bios = one(data, "board"), one(data, "bios")
    if b or bios:
        sb = scalar(data, "secure_boot")
        tpm = one(data, "tpm")
        cards.append(Card(joined(clean(b.get("Manufacturer")), clean(b.get("Product"))).replace("  ·  ", " ")
                          or "Motherboard", [(k, v) for k, v in (
            ("BIOS", joined(clean(bios.get("Manufacturer")), clean(bios.get("SMBIOSBIOSVersion")),
                            day(bios.get("ReleaseDate")),
                            {True: "Secure Boot on", False: "Secure Boot off"}.get(sb, ""))),
            ("TPM", str(tpm.get("SpecVersion", "")).split(",")[0] if tpm else "")) if v], "board"))
    mods = memory_modules(data)
    total = sum(int(m.get("Capacity") or 0) for m in mods) or one(data, "system").get("TotalPhysicalMemory")
    kinds = sorted({memory_kind(m) for m in mods if memory_kind(m)})
    slots = one(data, "memory_slots")
    speeds = sorted({m.get("ConfiguredClockSpeed") or m.get("Speed") for m in mods if (m.get("ConfiguredClockSpeed")
                                                                                       or m.get("Speed"))})
    mrows = [("Modules", joined(f"{len(mods)} × {mem(mods[0].get('Capacity'))}" if mods and len({m.get('Capacity')
                                                                                              for m in mods}) == 1
                                else ", ".join(mem(m.get("Capacity")) for m in mods),
                                f"{slots.get('MemoryDevices')} slots, {len(mods)} used" if slots.get("MemoryDevices")
                                else "")),
             ("Speed", ", ".join(f"{s} MT/s" for s in speeds))]
    mrows += [(module_name(m), joined(clean(m.get("Manufacturer")), clean(m.get("PartNumber")), mem(m.get("Capacity"))))
              for m in mods[:4]]
    mrows.append(("In use", local.get("mem_text", "")))
    cards.append(Card(joined("Memory", f"{mem(total)} {' / '.join(kinds)}".strip()), [r for r in mrows if r[1]], "memory"))
    gpus = [g for g in rows(data.get("gpu")) if isinstance(g, dict)]
    mons = monitors(data)
    if gpus:
        g = max(gpus, key=lambda g: gpu_memory(data, g) or 0)
        res = (f"{g['CurrentHorizontalResolution']} × {g['CurrentVerticalResolution']}"
               + (f" at {g['CurrentRefreshRate']} Hz" if g.get("CurrentRefreshRate") else "")
               if g.get("CurrentHorizontalResolution") else "")
        grows = [("Memory", mem(gpu_memory(data, g)) if gpu_memory(data, g) else ""),
                 ("Driver", joined(clean(g.get("DriverVersion")), day(g.get("DriverDate")))),
                 ("Display", joined(res, mons[0]["name"] if mons else ""))]
        grows += [("Other adapter", clean(x.get("Name"))) for x in gpus if x is not g]
        grows += [("Monitor", m["name"]) for m in mons[1:]]
        cards.append(Card(clean(g.get("Name")), [r for r in grows if r[1]], "gpu"))
    drows = []
    for d in disks(data):
        drows.append((f"Disk {d['index']}", joined(d["model"], size(d["size"]), d["bus"], d["media"], d["health"].lower(),
                                                    temperature(d["temp"]))))
    vols = [v for v in rows(data.get("volumes")) if isinstance(v, dict)]
    if vols:
        drows.append(("Volumes", joined(*(f"{v.get('DeviceID')} {size(v.get('Size'))} ({size(v.get('FreeSpace'))} free)"
                                           for v in vols))))
    cards.append(Card("Drives", drows, "drives"))
    o = one(data, "os")
    nets = [a for a in rows(data.get("network")) if isinstance(a, dict)]
    up = [a for a in nets if a.get("NetConnectionStatus") == 2]
    nrow = joined(*(clean(a.get("Name")) + (f" (connected, {rate(a.get('Speed'))})" if a in up else "") for a in nets))
    bat = [x for x in rows(data.get("battery")) if isinstance(x, dict)]
    wrows = [("Build", joined(f"{o.get('BuildNumber')}.{scalar(data, 'ubr')}" if scalar(data, "ubr") is not None
                              else o.get("BuildNumber"), o.get("OSArchitecture"))),
             ("Computer", clean(o.get("CSName"))), ("Up for", uptime(data)), ("Network", nrow),
             ("Battery", joined(f"{bat[0].get('EstimatedChargeRemaining')} %",
                                BATTERY_STATUS.get(bat[0].get("BatteryStatus"), "")) if bat else "")]
    cards.append(Card(windows_name(data) or "Windows", [r for r in wrows if r[1]], "windows"))
    return cards


def report(root: Node, cards: list[Card], version: str = "") -> str:
    """Everything as plain text (Report): the summary, then every device with its properties."""
    out = [f"Paragon PR7-HW {version} report  ·  {time.strftime('%Y-%m-%d %H:%M')}", "", "SYSTEM SUMMARY", ""]
    for c in cards:
        out.append(c.title)
        out += [f"    {k:<22}{v}" for k, v in c.rows]
        if c.chips:
            out.append(f"    {'Instruction sets':<22}{', '.join(n for n, on in c.chips if on)}")
        out.append("")
    out += ["DETAILS", ""]
    for depth, n in root.walk():
        out.append("    " * depth + n.name)
        for g, props in n.groups:
            out.append("    " * depth + f"  [{g}]")
            out += ["    " * depth + f"    {k:<22}{v}" for k, v in props]
    return "\r\n".join(out) + "\r\n"
