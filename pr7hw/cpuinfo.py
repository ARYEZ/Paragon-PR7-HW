"""The CPU's caches and instruction sets (no Qt), which WMI doesn't report well.

Windows: GetLogicalProcessorInformation (the caches per level, as CPU-Z adds them up) and IsProcessorFeaturePresent
(Windows' own list of features: SSE..AVX-512, virtualisation, RDRAND ...; FMA3 / BMI2 / AES-NI, which it has no
number for, come with every AVX2 CPU). Linux (tests, and handy): /sys and the
flags line of /proc/cpuinfo."""

from __future__ import annotations

import ctypes
import os
import sys

# The chips shown, in order, and how Windows / Linux name each
FEATURES = ["MMX", "SSE2", "SSE3", "SSSE3", "SSE4.1", "SSE4.2", "AVX", "AVX2", "AVX-512", "FMA3", "AES-NI",
            "BMI2", "RDRAND", "VT-x/AMD-V", "NX", "x86-64"]
PF = {"MMX": 3, "SSE2": 10, "SSE3": 13, "RDRAND": 28, "NX": 12, "VT-x/AMD-V": 21, "SSSE3": 36, "SSE4.1": 37,
      "SSE4.2": 38, "AVX": 39, "AVX2": 40, "AVX-512": 41}            # PF_* numbers of IsProcessorFeaturePresent
LINUX = {"MMX": "mmx", "SSE2": "sse2", "SSE3": "pni", "SSSE3": "ssse3", "SSE4.1": "sse4_1", "SSE4.2": "sse4_2",
         "AVX": "avx", "AVX2": "avx2", "AVX-512": "avx512f", "FMA3": "fma", "AES-NI": "aes",
         "BMI2": "bmi2", "RDRAND": "rdrand", "NX": "nx", "x86-64": "lm"}


def features() -> set[str]:
    if sys.platform == "win32":
        k32 = ctypes.windll.kernel32
        got = {name for name, n in PF.items() if k32.IsProcessorFeaturePresent(n)}
        # Windows has no PF_ number for these: AVX2 machines all have FMA3, BMI2 and AES; x86-64 is this build itself
        if "AVX2" in got:
            got |= {"FMA3", "BMI2", "AES-NI"}
        if sys.maxsize > 2 ** 32:
            got.add("x86-64")
        return got
    flags = set()
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith(("flags", "Features")):
                    flags = set(line.split(":", 1)[1].split())
                    break
    except OSError:
        return set()
    got = {name for name, flag in LINUX.items() if flag in flags}
    if "vmx" in flags or "svm" in flags:
        got.add("VT-x/AMD-V")
    return got


def caches() -> dict[int, int]:
    """{level: total bytes over the whole CPU} (L1 data + instruction counted together, as CPU-Z's total)."""
    if sys.platform == "win32":
        return _caches_windows()
    total: dict[int, int] = {}
    seen = set()
    base = "/sys/devices/system/cpu"
    try:
        cpus = [d for d in os.listdir(base) if d.startswith("cpu") and d[3:].isdigit()]
    except OSError:
        return {}
    for cpu in cpus:
        folder = os.path.join(base, cpu, "cache")
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for idx in names:
            if not idx.startswith("index"):
                continue
            d = os.path.join(folder, idx)
            try:
                level = int(open(os.path.join(d, "level")).read())
                size = open(os.path.join(d, "size")).read().strip()
                shared = open(os.path.join(d, "shared_cpu_list")).read().strip()
                kind = open(os.path.join(d, "type")).read().strip()
            except (OSError, ValueError):
                continue
            key = (level, kind, shared)
            if key in seen:
                continue
            seen.add(key)
            n = int(size.rstrip("KMG"))
            n *= {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}.get(size[-1], 1)
            total[level] = total.get(level, 0) + n
    return total


def _caches_windows() -> dict[int, int]:
    class CACHE(ctypes.Structure):
        _fields_ = [("Level", ctypes.c_ubyte), ("Associativity", ctypes.c_ubyte), ("LineSize", ctypes.c_ushort),
                    ("Size", ctypes.c_ulong), ("Type", ctypes.c_int)]

    class UNION(ctypes.Union):
        _fields_ = [("Cache", CACHE), ("Reserved", ctypes.c_ulonglong * 2)]

    class INFO(ctypes.Structure):
        _fields_ = [("ProcessorMask", ctypes.c_size_t), ("Relationship", ctypes.c_int), ("u", UNION)]

    k32 = ctypes.windll.kernel32
    need = ctypes.c_ulong(0)
    k32.GetLogicalProcessorInformation(None, ctypes.byref(need))
    count = need.value // ctypes.sizeof(INFO)
    if not count:
        return {}
    buf = (INFO * count)()
    if not k32.GetLogicalProcessorInformation(buf, ctypes.byref(need)):
        return {}
    total: dict[int, int] = {}
    for info in buf[:need.value // ctypes.sizeof(INFO)]:
        if info.Relationship == 2:                  # RelationCache
            c = info.u.Cache
            total[c.Level] = total.get(c.Level, 0) + c.Size
    return total
