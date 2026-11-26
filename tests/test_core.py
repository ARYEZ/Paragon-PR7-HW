import csv
import datetime as dt
import json

import pytest

from pr7hw import cpuinfo, hardware, sensors, wmi
from conftest import LOCAL


def test_script_asks_every_class_on_its_own():
    s = wmi.script()
    assert s.count("try {") == len(wmi.QUERIES) and "ConvertTo-Json -Depth 5 -Compress" in s
    assert "Win32_Processor" in s and "MSFT_PhysicalDisk" in s and "Get-StorageReliabilityCounter" in s


def test_read_gives_lists_and_survives_rubbish():
    got = wmi.read(run=lambda s: 'WARNING: something\r\n{"cpu": {"Name": "X"}, "battery": null, "admin": [false]}')
    assert got["cpu"] == [{"Name": "X"}] and got["battery"] is None and wmi.scalar(got, "admin") is False
    assert wmi.read(run=lambda s: "not json") == {}
    assert wmi.read(run=lambda s: (_ for _ in ()).throw(OSError("no powershell"))) == {}


def test_dates_and_sizes():
    assert hardware.date("/Date(1786708800000)/").year == 2026
    assert hardware.date({"value": "/Date(0)/", "DateTime": "x"}) == dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    assert hardware.date("20260814000000.000000+000").month == 8 and hardware.date(None) is None
    assert hardware.mem(17_171_480_576) == "16 GB" and hardware.mem(67_755_065_344) == "63.1 GB"
    assert hardware.size(2_000_396_321_280) == "2.00 TB" and hardware.size(16_777_216) == "16.8 MB"
    assert hardware.text([68, 69, 76, 76, 0, 0]) == "DELL" and hardware.rate(2_500_000_000) == "2.5 Gb/s"
    assert hardware.duration(3 * 86400 + 4 * 3600 + 60) == "3 days 4 h" and hardware.duration(125) == "2 min"


def test_summary_of_the_made_up_pc(studio):
    cards = {c.section: c for c in hardware.summary(studio, LOCAL)}
    cpu = cards["cpu"]
    assert cpu.title == "AMD Ryzen 9 7950X 16-Core Processor"            # trailing spaces trimmed
    rows = dict(cpu.rows)
    assert rows["Cores / threads"] == "16 / 32" and rows["Caches"] == "L1 1 MB  ·  L2 16 MB  ·  L3 64 MB"
    assert rows["Clock"] == "4.50 GHz base  ·  now 5.21 GHz" and ("AVX-512", True) in cpu.chips
    assert cards["memory"].title == "Memory  ·  64 GB DDR5"
    assert dict(cards["memory"].rows)["Modules"] == "2 × 32 GB  ·  4 slots, 2 used"
    assert dict(cards["memory"].rows)["Speed"] == "6000 MT/s"
    gpu = cards["gpu"]
    assert gpu.title == "NVIDIA GeForce RTX 4080 SUPER" and dict(gpu.rows)["Memory"] == "16 GB"   # not AdapterRAM's 4 GB
    assert dict(gpu.rows)["Display"] == "3840 × 2160 at 144 Hz  ·  DELL U3225QE"
    d = dict(cards["drives"].rows)
    assert d["Disk 0"] == "Samsung SSD 990 PRO 2TB  ·  2.00 TB  ·  NVMe  ·  SSD  ·  healthy  ·  41 °C"
    assert d["Disk 2"].endswith("SATA  ·  HDD 7200 rpm  ·  healthy  ·  36 °C")
    assert cards["windows"].title == "Windows 11 Pro 24H2"
    w = dict(cards["windows"].rows)
    assert w["Build"] == "26100.2454  ·  64-bit" and w["Up for"] == "3 days 4 h"
    assert w["Network"].startswith("Realtek Gaming 2.5GbE Family Controller (connected, 2.5 Gb/s)")
    assert dict(cards["board"].rows)["BIOS"].endswith("2026-08-14  ·  Secure Boot on")


def test_details_tree(studio):
    root = hardware.build(studio, LOCAL)
    assert root.name == "STUDIO-PC"
    assert [c.name for c in root.children] == ["Central processor", "Motherboard", "Memory", "Graphics", "Monitors",
                                               "Drives", "Network", "Audio", "USB", "Windows"]
    ssd = dict(root.find("Samsung SSD 990 PRO 2TB").groups)
    assert dict(ssd["DRIVE"])["Partitions"] == "System 105 MB  ·  Reserved 16.8 MB  ·  Data C: 2.00 TB  ·  Recovery 786 MB"
    assert dict(ssd["HEALTH"]) == {"Status": "Healthy", "Temperature": "41 °C  ·  highest seen 63 °C", "Wear": "3 % used",
                                   "Power on": "6,412 hours  ·  1,284 starts", "Read / write errors": "0"}
    assert dict(ssd["VOLUMES"]) == {"C: Windows": "NTFS  ·  2.00 TB, 657 GB free"}
    dimm = dict(dict(root.find("DIMM_A2").groups)["MODULE"])
    assert dimm["Type"] == "DDR5  ·  DIMM" and dimm["Speed"] == "6000 MT/s" and dimm["Voltage"] == "1.35 V"
    assert dict(dict(root.find("BIOS").groups)["FIRMWARE"])["TPM"] == "2.0  ·  AMD"
    wifi = dict(dict(root.find("Intel(R) Wi-Fi 7 BE200 320MHz").groups)["ADAPTER"])
    assert wifi["State"] == "Cable unplugged" and "Speed" not in wifi          # no made-up speed when unplugged
    assert dict(root.find("USB").groups)["USB"] == [("Controllers", "2"), ("Devices", "11")]


def test_without_admin_or_on_a_laptop(studio):
    data = dict(studio, reliability=[], admin=[False], tpm=[], secure_boot=None,
                battery=[{"Name": "DELL 7FHHV", "EstimatedChargeRemaining": 84, "DesignCapacity": 60000,
                          "FullChargeCapacity": 51000, "BatteryStatus": 2, "Chemistry": 6}])
    root = hardware.build(data, {})
    ssd = dict(root.find("Samsung SSD 990 PRO 2TB").groups)
    assert dict(ssd["HEALTH"]) == {"Status": "Healthy"}                        # the counters need administrator
    bat = dict(dict(root.find("DELL 7FHHV").groups)["BATTERY"])
    assert bat == {"Charge": "84 %", "State": "On mains power", "Chemistry": "Lithium-ion", "Wear": "15 % worn"}
    assert "Administrator" in dict(dict(root.find("Windows 11 Pro 24H2").groups)["WINDOWS"])
    assert hardware.summary({}, {})                                           # nothing known: still a page


def test_report(studio):
    text = hardware.report(hardware.build(studio, LOCAL), hardware.summary(studio, LOCAL), "9.9")
    assert text.startswith("Paragon PR7-HW 9.9 report") and "\r\n" in text
    assert "SYSTEM SUMMARY" in text and "DETAILS" in text and "Instruction sets      MMX" in text
    assert "    Samsung SSD 990 PRO 2TB" in text and "Wear                  3 % used" in text


def test_cpuinfo_here():
    """The real CPU this runs on: some features and caches are found (Linux /proc and /sys, or Windows' API)."""
    f = cpuinfo.features()
    assert f <= set(cpuinfo.FEATURES) | {"VT-x/AMD-V"}
    if f:
        assert "SSE2" in f or "x86-64" in f or not any(x.startswith("SSE") for x in f)
    c = cpuinfo.caches()
    assert all(k in (1, 2, 3, 4) and v > 0 for k, v in c.items())


def test_reading_and_show():
    r = sensors.Reading("CPU", "Load", "percent")
    for v in (10, 30, 20):
        r.add(v)
    assert (r.current, r.low, r.high, r.average) == (20, 10, 30, 20)
    r.reset()
    assert (r.low, r.high, r.average) == (20, 20, 20)
    assert sensors.show(68.4, "temp") == "68 °C" and sensors.show(20, "temp", fahrenheit=True) == "68 °F"
    assert sensors.show(5210, "mhz") == "5.21 GHz" and sensors.show(412e6, "rate") == "412 MB/s"
    assert sensors.show(22_977_000_000, "bytes") == "21.4 GB" and sensors.show(0, "rate") == "0 B/s"
    assert sensors.show(None, "temp") == ""


def test_rates():
    rate = sensors.Rates()
    assert rate("d", 1000, 10.0) is None
    assert rate("d", 5000, 12.0) == 2000
    assert rate("d", 4000, 13.0) == 0                                            # a counter that restarted


def test_sampler_keeps_going_and_logs(tmp_path):
    calls = []

    def good():
        calls.append(1)
        return [("CPU", "Load", float(len(calls) * 10), "percent")]

    def broken():
        raise RuntimeError("boom")
    s = sensors.Sampler([broken, good])
    s.start_log(str(tmp_path / "log.csv"))
    s.sample()
    s.sample()
    r = s.readings[("CPU", "Load")]
    assert list(r.values) == [10, 20] and r.average == 15 and s.samples == 2
    rows = list(csv.reader(open(tmp_path / "log.csv", encoding="utf-8-sig")))
    assert rows[0] == ["Time", "CPU  ·  Load"] and [x[1] for x in rows[1:]] == ["10.000", "20.000"]
    s.stop_log()
    s.sample()
    assert len(list(csv.reader(open(tmp_path / "log.csv", encoding="utf-8-sig")))) == 3
    for _ in range(sensors.HISTORY + 5):
        s.sample()
    assert len(r.values) == sensors.HISTORY                                       # two minutes kept


def test_real_sources_here():
    s = sensors.Sampler([sensors.cpu_source(), sensors.memory_source(), sensors.disk_source(), sensors.network_source()])
    s.sample()
    s.sample()
    names = [f"{g}/{n}" for g, n in s.order]
    assert "CPU/Total load" in names and "Memory/In use" in names
    assert 0 <= s.readings[("CPU", "Total load")].current <= 100


def test_nvidia_smi_lines():
    out = "NVIDIA GeForce RTX 4080 SUPER, 63, 71, 9830, 212.40, 41, 2610\nNVIDIA T400, 45, 0, 120, [N/A], [N/A], 300\n"
    got = sensors.nvidia_source("nvidia-smi", run=lambda args: out)()
    by = {(g, n): (v, k) for g, n, v, k in got}
    assert by[("GPU  ·  GeForce RTX 4080 SUPER", "Temperature")] == (63.0, "temp")
    assert by[("GPU  ·  GeForce RTX 4080 SUPER", "Video memory")] == (9830 * 1024 * 1024, "bytes")
    assert ("GPU  ·  T400", "Power") not in by and ("GPU  ·  T400", "Clock") in by       # [N/A] left out


class FakePdh:
    def read(self):
        return {"engine": {"pid_123_luid_0x00000000_0x0000F00D_phys_0_eng_0_engtype_3D": 40.0,
                           "pid_456_luid_0x00000000_0x0000F00D_phys_0_eng_0_engtype_3D": 25.0,
                           "pid_9_luid_0x00000000_0x0000BEEF_phys_0_eng_0_engtype_3D": 3.0,
                           "pid_9_luid_0x00000000_0x00000001_phys_0_eng_0_engtype_3D": 0.0},
                "memory": {"luid_0x00000000_0x0000F00D_phys_0": 9.6e9, "luid_0x00000000_0x0000BEEF_phys_0": 2e8,
                           "luid_0x00000000_0x00000001_phys_0": 0.0},
                "thermal": {"\\_TZ.TZ00": 327.15}}


def test_gpu_counters_add_up_per_adapter():
    got = sensors.pdh_source(FakePdh(), names=["RTX 4080 SUPER", "AMD Radeon"])()
    by = {(g, n): v for g, n, v, k in got}
    assert by[("GPU 1  ·  RTX 4080 SUPER", "Load")] == 65.0                   # two processes on the same card
    assert by[("GPU 1  ·  RTX 4080 SUPER", "Video memory")] == 9.6e9
    assert by[("GPU 2  ·  AMD Radeon", "Load")] == 3.0
    assert not any(g.startswith("GPU 3") for g, _n in by)                     # Windows' software adapter left out
    assert by[("Motherboard", "Temperature (ACPI thermal zone TZ00)")] == pytest.approx(54.0)


def test_drive_temperatures_come_every_30_s():
    calls = []

    def run(script):
        calls.append(script)
        return json.dumps([{"Name": "Samsung SSD 990 PRO 2TB", "Temperature": 41}, {"Name": "ST8000", "Temperature": 0}])
    src = sensors.drives_source(run=run, every=30)
    assert src() == [("Drives", "Samsung SSD 990 PRO 2TB  ·  temperature", 41.0, "temp")]
    assert src() == src() and len(calls) == 1                                  # kept in between
