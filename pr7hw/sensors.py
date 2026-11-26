"""Live readings (no Qt), the way HWiNFO's Sensors window keeps them: each reading has a current value, Min / Max /
Average since the start (or the last Reset) and the last HISTORY samples for its graph.

Where each one comes from, all without a driver of our own:
    psutil            CPU load (total and the busiest core), clock, memory, page file, every drive's and network
                      adapter's speed, battery; on Linux also its temperature sensors
    performance counters (PDH, Windows)   GPU load and video memory per adapter (what Task Manager shows), the ACPI
                      thermal zones' temperature
    nvidia-smi        an NVIDIA card's temperature, fan, power and clock (installed with NVIDIA's driver)
    drives            S.M.A.R.T. temperatures (wmi.py's reliability part; administrator only, every 30 s)

A source is a callable returning [(group, name, value, kind)]; `Sampler(sources)` takes stand-ins in tests."""

from __future__ import annotations

import collections
import csv
import os
import shutil
import subprocess
import sys
import time

import psutil

HISTORY = 60                              # samples kept for the graph (2 minutes at the default 2 s)
KINDS = ("percent", "temp", "bytes", "rate", "mhz", "watts", "rpm", "count")


class Reading:
    __slots__ = ("group", "name", "kind", "values", "current", "low", "high", "total", "count")

    def __init__(self, group: str, name: str, kind: str):
        self.group, self.name, self.kind = group, name, kind
        self.values = collections.deque(maxlen=HISTORY)
        self.current = self.low = self.high = None
        self.total, self.count = 0.0, 0

    def add(self, v: float):
        self.current = v
        self.values.append(v)
        self.low = v if self.low is None else min(self.low, v)
        self.high = v if self.high is None else max(self.high, v)
        self.total += v
        self.count += 1

    @property
    def average(self):
        return self.total / self.count if self.count else None

    def reset(self):
        self.low = self.high = self.current
        self.total, self.count = (self.current or 0.0, 1) if self.current is not None else (0.0, 0)


def show(v, kind: str, fahrenheit: bool = False) -> str:
    if v is None:
        return ""
    if kind == "percent":
        return f"{v:.0f} %"
    if kind == "temp":
        return f"{v * 9 / 5 + 32:.0f} °F" if fahrenheit else f"{v:.0f} °C"
    if kind == "mhz":
        return f"{v / 1000:.2f} GHz" if v >= 1000 else f"{v:.0f} MHz"
    if kind in ("bytes", "rate"):
        n, unit = float(v), "B"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1000 or unit == "TB":
                break
            n /= 1000
        text = f"{n:.0f} {unit}" if unit == "B" or n >= 100 else f"{n:.1f} {unit}"
        if kind == "bytes" and unit != "B":
            # memory sizes in binary units, as Windows shows memory
            b, unit2 = float(v), "B"
            for unit2 in ("B", "KB", "MB", "GB", "TB"):
                if b < 1024 or unit2 == "TB":
                    break
                b /= 1024
            text = f"{b:.1f} {unit2}"
        return text + ("/s" if kind == "rate" else "")
    if kind == "watts":
        return f"{v:.0f} W"
    if kind == "rpm":
        return f"{v:.0f} rpm"
    return f"{v:,.0f}"


# ---------------------------------------------------------------- sources
class Rates:
    """Turns ever-growing counters into per-second rates (the first call has none yet)."""

    def __init__(self):
        self.last: dict = {}

    def __call__(self, key, value: float, now: float) -> float | None:
        prev = self.last.get(key)
        self.last[key] = (value, now)
        if prev is None or now <= prev[1]:
            return None
        return max(0.0, (value - prev[0]) / (now - prev[1]))


def cpu_source():
    psutil.cpu_percent(percpu=True)                     # the first call only starts the clock

    def read():
        per = psutil.cpu_percent(percpu=True)
        out = [("CPU", "Total load", sum(per) / len(per) if per else 0.0, "percent"),
               ("CPU", "Busiest core", max(per) if per else 0.0, "percent")]
        f = psutil.cpu_freq()
        if f and f.current:
            out.append(("CPU", "Clock", float(f.current), "mhz"))
        try:
            out.append(("CPU", "Processes", float(len(psutil.pids())), "count"))
        except psutil.Error:
            pass
        return out
    return read


def memory_source():
    def read():
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        return [("Memory", "In use", float(vm.total - vm.available), "bytes"),
                ("Memory", "Load", float(vm.percent), "percent"),
                ("Memory", "Page file in use", float(sw.used), "bytes")]
    return read


def disk_source(names: dict | None = None):
    """`names`: {"PhysicalDrive0": "Samsung SSD 990 PRO 2TB"} (from wmi.py) so a drive reads as its model."""
    rates = Rates()
    names = names or {}

    def read():
        now = time.monotonic()
        out = []
        for name, c in sorted((psutil.disk_io_counters(perdisk=True) or {}).items()):
            if sys.platform != "win32" and (name.startswith(("loop", "ram")) or name[-1:].isdigit() and
                                            not name.startswith("nvme") and name[:-1] in os.listdir("/sys/block")):
                continue                                   # Linux: whole disks only
            label = names.get(name) or name.replace("PhysicalDrive", "Disk ")
            for what, value in (("read", c.read_bytes), ("write", c.write_bytes)):
                r = rates((name, what), float(value), now)
                if r is not None:
                    out.append(("Drives", f"{label}  ·  {what}", r, "rate"))
        return out
    return read


def network_source():
    rates = Rates()

    def read():
        now = time.monotonic()
        stats = psutil.net_if_stats()
        out = []
        for name, c in sorted((psutil.net_io_counters(pernic=True) or {}).items()):
            st = stats.get(name)
            if not st or not st.isup or name.lower().startswith(("lo", "loopback")):
                continue
            for what, value in (("download", c.bytes_recv), ("upload", c.bytes_sent)):
                r = rates((name, what), float(value), now)
                if r is not None:
                    out.append((f"Network  ·  {name}", what.capitalize(), r, "rate"))
        return out
    return read


def battery_source():
    def read():
        b = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        return [("Battery", "Charge", float(b.percent), "percent")] if b else []
    return read


def linux_temps_source():
    def read():
        out = []
        for chip, entries in (psutil.sensors_temperatures() or {}).items():
            for i, e in enumerate(entries):
                if e.current:
                    out.append((f"Temperatures  ·  {chip}", e.label or f"Sensor {i + 1}", float(e.current), "temp"))
        return out
    return read


def nvidia_smi() -> str | None:
    exe = shutil.which("nvidia-smi")
    if not exe and sys.platform == "win32":
        p = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
        exe = p if os.path.exists(p) else None
    return exe


def nvidia_source(exe: str, run=None):
    """nvidia-smi's CSV: one line per card."""
    fields = "name,temperature.gpu,utilization.gpu,memory.used,power.draw,fan.speed,clocks.gr"

    def default(args):
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        return subprocess.run(args, capture_output=True, text=True, timeout=5, creationflags=flags).stdout
    run = run or default

    def read():
        out = []
        text = run([exe, f"--query-gpu={fields}", "--format=csv,noheader,nounits"])
        for line in text.strip().splitlines():
            bits = [b.strip() for b in line.split(",")]
            if len(bits) < 7:
                continue
            g = f"GPU  ·  {bits[0].replace('NVIDIA ', '')}"

            def num(s):
                try:
                    return float(s)
                except ValueError:
                    return None           # "[N/A]" for what a card doesn't report
            for name, v, kind in (("Temperature", num(bits[1]), "temp"), ("Load", num(bits[2]), "percent"),
                                  ("Video memory", num(bits[3]) * 1024 * 1024 if num(bits[3]) is not None else None,
                                   "bytes"),
                                  ("Power", num(bits[4]), "watts"), ("Fan", num(bits[5]), "percent"),
                                  ("Clock", num(bits[6]), "mhz")):
                if v is not None:
                    out.append((g, name, v, kind))
        return out
    return read


class Pdh:
    """Windows' performance counters (PDH) through ctypes: English counter paths with wildcards."""

    def __init__(self, paths: dict[str, str]):
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes
        self.pdh = ctypes.windll.pdh
        self.query = wintypes.HANDLE()
        if self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.query)):
            raise OSError("PdhOpenQuery failed")
        self.counters = {}
        for key, path in paths.items():
            h = wintypes.HANDLE()
            if self.pdh.PdhAddEnglishCounterW(self.query, path, 0, ctypes.byref(h)) == 0:
                self.counters[key] = h
        self.pdh.PdhCollectQueryData(self.query)

    def read(self) -> dict[str, dict[str, float]]:
        ct = self.ct

        class VALUE(ct.Structure):
            _fields_ = [("CStatus", ct.c_ulong), ("doubleValue", ct.c_double)]

        class ITEM(ct.Structure):
            _fields_ = [("szName", ct.c_wchar_p), ("FmtValue", VALUE)]

        self.pdh.PdhCollectQueryData(self.query)
        out = {}
        for key, h in self.counters.items():
            size, count = ct.c_ulong(0), ct.c_ulong(0)
            PDH_FMT_DOUBLE, PDH_MORE_DATA = 0x200, 0x800007D2
            r = self.pdh.PdhGetFormattedCounterArrayW(h, PDH_FMT_DOUBLE, ct.byref(size), ct.byref(count), None)
            if r & 0xFFFFFFFF != PDH_MORE_DATA or not size.value:
                continue
            buf = (ct.c_byte * size.value)()
            if self.pdh.PdhGetFormattedCounterArrayW(h, PDH_FMT_DOUBLE, ct.byref(size), ct.byref(count), buf):
                continue
            items = ct.cast(buf, ct.POINTER(ITEM))
            out[key] = {items[i].szName: items[i].FmtValue.doubleValue for i in range(count.value)
                        if items[i].FmtValue.CStatus in (0, 1)}
        return out


def pdh_source(pdh=None, names: list | None = None):
    """GPU load = the 3D engines' utilisation added up per adapter (Task Manager's figure); video memory = dedicated
    usage; ACPI thermal zones in kelvin. Counters name adapters by a LUID only: `names` (the adapters by video memory,
    largest first, from wmi.py) are given to them in the same order, largest dedicated memory first."""
    pdh = pdh or Pdh({"engine": r"\GPU Engine(*engtype_3D)\Utilization Percentage",
                      "memory": r"\GPU Adapter Memory(*)\Dedicated Usage",
                      "thermal": r"\Thermal Zone Information(*)\Temperature"})
    names = list(names or [])

    def luid(instance: str) -> str:
        parts = instance.split("_")
        return "_".join(parts[1:3]) if instance.startswith("luid_") or "luid" in instance else instance

    def read():
        got = pdh.read()
        out = []
        load: dict[str, float] = {}
        for inst, v in got.get("engine", {}).items():
            key = luid(inst[inst.find("luid"):]) if "luid" in inst else inst
            load[key] = load.get(key, 0.0) + v
        memory = {}
        for inst, v in got.get("memory", {}).items():
            memory[luid(inst)] = v
        adapters = sorted((k for k in set(load) | set(memory) if memory.get(k) or load.get(k)),
                          key=lambda k: -memory.get(k, 0))      # Windows' software adapter has neither
        for i, k in enumerate(adapters):
            g = f"GPU {i + 1}" if len(adapters) > 1 else "GPU"
            if i < len(names) and names[i]:
                g = f"{g}  ·  {names[i]}"
            if k in load:
                out.append((g, "Load", min(100.0, load[k]), "percent"))
            if memory.get(k):
                out.append((g, "Video memory", memory[k], "bytes"))
        for inst, v in sorted(got.get("thermal", {}).items()):
            if v > 0:
                label = inst.rsplit(".", 1)[-1].lstrip("\\_")        # "\\_TZ.TZ00" -> "TZ00"
                out.append(("Motherboard", f"Temperature (ACPI thermal zone {label})", v - 273.15, "temp"))
        return out
    return read


def drives_source(run=None, every: float = 30.0):
    """Drive temperatures from the health counters (administrator): asked every `every` seconds, kept in between."""
    from . import wmi
    state = {"at": -1e9, "rows": []}
    script = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-PhysicalDisk | ForEach-Object { $r = $_ | "
              "Get-StorageReliabilityCounter -ErrorAction SilentlyContinue; if ($r.Temperature) { [pscustomobject]@{"
              " Name = $_.FriendlyName; Temperature = $r.Temperature } } } | ConvertTo-Json -Compress")

    def read():
        now = time.monotonic()
        if now - state["at"] >= every:
            state["at"] = now
            try:
                import json
                text = (run or wmi.powershell)(script)
                start = min([i for i in (text.find("["), text.find("{")) if i >= 0] or [-1])
                rows = wmi.rows(json.loads(text[start:])) if start >= 0 else []
                state["rows"] = [("Drives", f"{r['Name']}  ·  temperature", float(r["Temperature"]), "temp")
                                 for r in rows if isinstance(r, dict) and r.get("Temperature")]
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                state["rows"] = []
        return list(state["rows"])
    return read


def is_admin() -> bool:
    if sys.platform != "win32":
        return hasattr(os, "geteuid") and os.geteuid() == 0
    import ctypes
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def default_sources(gpu_names: list | None = None, disk_names: dict | None = None) -> list:
    sources = [cpu_source(), memory_source(), disk_source(disk_names), network_source(), battery_source()]
    if sys.platform == "win32":
        try:
            sources.append(pdh_source(names=gpu_names))
        except OSError:
            pass
        if is_admin():
            sources.append(drives_source())
    elif hasattr(psutil, "sensors_temperatures"):
        sources.append(linux_temps_source())
    exe = nvidia_smi()
    if exe:
        sources.append(nvidia_source(exe))
    return sources


class Sampler:
    def __init__(self, sources: list | None = None):
        self.sources = sources if sources is not None else default_sources()
        self.readings: dict[tuple[str, str], Reading] = {}
        self.order: list[tuple[str, str]] = []
        self.started = time.time()
        self.samples = 0
        self.log_path: str | None = None
        self._log_names: list | None = None

    def sample(self) -> list[Reading]:
        for src in self.sources:
            try:
                got = src()
            except Exception:  # noqa: BLE001 - one source's trouble never stops the others
                continue
            for group, name, value, kind in got:
                key = (group, name)
                r = self.readings.get(key)
                if r is None:
                    r = self.readings[key] = Reading(group, name, kind)
                    self.order.append(key)
                r.add(float(value))
        self.samples += 1
        if self.log_path:
            self._log()
        return self.list()

    def list(self) -> list[Reading]:
        return [self.readings[k] for k in self.order]

    def groups(self) -> list[tuple[str, list[Reading]]]:
        out: dict[str, list[Reading]] = {}
        for r in self.list():
            out.setdefault(r.group, []).append(r)
        return list(out.items())

    def reset(self):
        for r in self.readings.values():
            r.reset()
        self.started = time.time()

    # ------------------------------------------------------------ Log to CSV (HWiNFO's sensor log)
    def start_log(self, path: str):
        self.log_path = path
        self._log_names = None

    def stop_log(self):
        self.log_path = None

    def _log(self):
        names = [f"{g}  ·  {n}" for g, n in self.order]
        new = self._log_names is None or names != self._log_names or not os.path.exists(self.log_path)
        try:
            with open(self.log_path, "a", newline="", encoding="utf-8-sig" if new and not os.path.exists(self.log_path)
                      else "utf-8") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["Time"] + names)
                    self._log_names = names
                w.writerow([time.strftime("%Y-%m-%d %H:%M:%S")] + [f"{self.readings[k].current:.3f}"
                                                                    if self.readings[k].current is not None else ""
                                                                    for k in self.order])
        except OSError:
            self.log_path = None
