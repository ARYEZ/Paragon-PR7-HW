"""What only real Windows can show (CI runs these): WMI's answers, the performance counters, the CPU's features and
caches through Windows' own calls, all on the runner's real (virtual) hardware."""
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only (CI)")


@pytest.fixture(scope="module")
def real():
    from pr7hw import wmi
    t = time.time()
    data = wmi.read()
    return data, time.time() - t


def test_wmi_answers(real):
    from pr7hw import wmi
    data, took = real
    assert took < 60, took
    assert wmi.one(data, "cpu").get("Name") and wmi.one(data, "cpu").get("NumberOfLogicalProcessors")
    assert wmi.one(data, "os").get("BuildNumber") and wmi.rows(data.get("disks"))
    assert wmi.scalar(data, "admin") in (True, False)


def test_the_tree_and_summary_from_real_answers(real):
    from pr7hw import hardware
    from pr7hw.main_window import local_info
    data, _ = real
    local = local_info()
    root = hardware.build(data, local)
    cards = hardware.summary(data, local)
    assert root.find("Central processor").children[0].name == hardware.clean(data["cpu"][0]["Name"])
    assert root.find("Drives").children and cards[0].rows
    assert hardware.windows_name(data).startswith("Windows")
    text = hardware.report(root, cards, "test")
    assert "SYSTEM SUMMARY" in text


def test_cpu_features_and_caches():
    from pr7hw import cpuinfo
    f = cpuinfo.features()
    assert {"SSE2", "x86-64", "NX"} <= f
    c = cpuinfo.caches()
    assert c.get(1, 0) > 0 and c.get(2, 0) > 0


def test_performance_counters():
    from pr7hw import sensors
    p = sensors.Pdh({"cpu": r"\Processor(*)\% Processor Time"})
    time.sleep(0.5)
    got = p.read()
    assert "_Total" in got.get("cpu", {})
    src = sensors.pdh_source()                       # GPU / thermal counters may have nothing on a VM: no error
    assert isinstance(src(), list)


def test_sampler_with_every_default_source():
    from pr7hw import sensors
    s = sensors.Sampler()
    s.sample()
    time.sleep(1)
    s.sample()
    assert ("CPU", "Total load") in s.readings and ("Memory", "In use") in s.readings
    assert any(g == "Drives" for g, _n in s.readings)
