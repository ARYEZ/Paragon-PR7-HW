"""What Windows knows about the hardware (no Qt): one PowerShell run of Get-CimInstance over the classes HWiNFO's
summary needs, printed as JSON. One process for everything because PowerShell takes ~1 s to start; each class is
asked on its own (try / catch) so a class this PC doesn't have (no battery, no TPM, not administrator) is just absent.

`read(run=)`: `run(script) -> str` is injectable; tests feed a recorded answer (tests/data/studio.json, a made-up PC)."""

from __future__ import annotations

import base64
import json
import subprocess
import sys

# name -> PowerShell expression; Select-Object keeps the answer small (CIM objects carry dozens of fields)
QUERIES = {
    "cpu": "Get-CimInstance Win32_Processor | Select-Object Name, Manufacturer, NumberOfCores, NumberOfLogicalProcessors,"
           " MaxClockSpeed, CurrentClockSpeed, SocketDesignation, L2CacheSize, L3CacheSize, ProcessorId, Caption,"
           " VirtualizationFirmwareEnabled, AddressWidth",
    "system": "Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer, Model, Name, TotalPhysicalMemory,"
              " SystemType, PCSystemType",
    "board": "Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer, Product, Version, SerialNumber",
    "bios": "Get-CimInstance Win32_BIOS | Select-Object Manufacturer, SMBIOSBIOSVersion, ReleaseDate, SMBIOSMajorVersion,"
            " SMBIOSMinorVersion",
    "memory": "Get-CimInstance Win32_PhysicalMemory | Select-Object BankLabel, DeviceLocator, Capacity, Speed,"
              " ConfiguredClockSpeed, Manufacturer, PartNumber, SerialNumber, SMBIOSMemoryType, FormFactor,"
              " ConfiguredVoltage",
    "memory_slots": "Get-CimInstance Win32_PhysicalMemoryArray | Select-Object MemoryDevices, MaxCapacityEx",
    "gpu": "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterCompatibility, DriverVersion, DriverDate,"
           " AdapterRAM, CurrentHorizontalResolution, CurrentVerticalResolution, CurrentRefreshRate, VideoProcessor,"
           " PNPDeviceID",
    # AdapterRAM stops at 4 GB (a 32-bit field): the driver's own qwMemorySize in the display class key is exact
    "gpu_memory": "Get-ChildItem 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}'"
                  " -ErrorAction SilentlyContinue | ForEach-Object { $p = Get-ItemProperty $_.PSPath -ErrorAction"
                  " SilentlyContinue; if ($p.'HardwareInformation.qwMemorySize') { [pscustomobject]@{ Name ="
                  " $p.DriverDesc; Bytes = [uint64]$p.'HardwareInformation.qwMemorySize' } } }",
    "monitors": "Get-CimInstance -Namespace root\\wmi WmiMonitorID | Select-Object ManufacturerName, UserFriendlyName,"
                " SerialNumberID, YearOfManufacture, InstanceName",
    "disks": "Get-CimInstance Win32_DiskDrive | Select-Object Index, Model, SerialNumber, FirmwareRevision, Size,"
             " InterfaceType, Partitions, MediaType, PNPDeviceID",
    "physical_disks": "Get-CimInstance -Namespace root\\Microsoft\\Windows\\Storage MSFT_PhysicalDisk | Select-Object"
                      " DeviceId, FriendlyName, MediaType, BusType, HealthStatus, SpindleSpeed, Size",
    # health counters need administrator rights; without them this part is simply missing
    "reliability": "Get-PhysicalDisk | ForEach-Object { $d = $_; $r = $d | Get-StorageReliabilityCounter -ErrorAction"
                   " Stop; [pscustomobject]@{ DeviceId = $d.DeviceId; Temperature = $r.Temperature; TemperatureMax ="
                   " $r.TemperatureMax; Wear = $r.Wear; PowerOnHours = $r.PowerOnHours; StartStopCycleCount ="
                   " $r.StartStopCycleCount; ReadErrorsTotal = $r.ReadErrorsTotal; WriteErrorsTotal ="
                   " $r.WriteErrorsTotal } }",
    "volumes": "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID, VolumeName, FileSystem,"
               " Size, FreeSpace",
    "partitions": "Get-Partition -ErrorAction SilentlyContinue | Select-Object DiskNumber, PartitionNumber, DriveLetter,"
                  " Size, Type",
    "network": "Get-CimInstance Win32_NetworkAdapter -Filter 'PhysicalAdapter=True' | Select-Object Name, Manufacturer,"
               " MACAddress, Speed, NetConnectionStatus, NetConnectionID, AdapterType",
    "audio": "Get-CimInstance Win32_SoundDevice | Select-Object Name, Manufacturer, Status",
    "usb": "Get-CimInstance Win32_USBController | Select-Object Name, Manufacturer",
    "usb_devices": "(Get-CimInstance Win32_PnPEntity -Filter \"PNPDeviceID LIKE 'USB\\\\%'\" | Measure-Object).Count",
    "battery": "Get-CimInstance Win32_Battery | Select-Object Name, EstimatedChargeRemaining, DesignCapacity,"
               " FullChargeCapacity, BatteryStatus, Chemistry",
    "os": "Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture,"
          " LastBootUpTime, InstallDate, CSName, TotalVisibleMemorySize, FreePhysicalMemory",
    "display_version": "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion').DisplayVersion",
    "ubr": "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion').UBR",
    "tpm": "Get-CimInstance -Namespace root\\cimv2\\Security\\MicrosoftTpm Win32_Tpm | Select-Object SpecVersion,"
           " ManufacturerIdTxt, IsEnabled_InitialValue",
    "secure_boot": "Confirm-SecureBootUEFI",
    "thermal": "Get-CimInstance -Namespace root\\wmi MSAcpi_ThermalZoneTemperature | Select-Object InstanceName,"
               " CurrentTemperature",
    "admin": "([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole("
             "[Security.Principal.WindowsBuiltInRole]::Administrator)",
}


def script() -> str:
    parts = ["$ErrorActionPreference = 'Stop'", "[Console]::OutputEncoding = [Text.Encoding]::UTF8", "$out = [ordered]@{}"]
    for name, expr in QUERIES.items():
        parts.append(f"try {{ $out['{name}'] = @({expr}) }} catch {{ $out['{name}'] = $null }}")
    parts.append("$out | ConvertTo-Json -Depth 5 -Compress")
    return "\n".join(parts)


def powershell(text: str, timeout: float = 90) -> str:
    """Run a PowerShell script (-EncodedCommand: no quoting trouble) hidden; its standard output."""
    enc = base64.b64encode(text.encode("utf-16-le")).decode()
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-EncodedCommand", enc], capture_output=True, timeout=timeout, creationflags=flags)
    return r.stdout.decode("utf-8", "replace")


def read(run=None) -> dict:
    """{name: [rows] | value | None}; {} when PowerShell can't be run (not Windows)."""
    if run is None:
        if sys.platform != "win32":
            return {}
        run = powershell
    try:
        text = run(script())
        start = text.find("{")
        data = json.loads(text[start:]) if start >= 0 else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}
    return {k: rows(v) if isinstance(v, (list, dict)) else v for k, v in data.items()}


def rows(v) -> list:
    """ConvertTo-Json gives one object for a one-row answer and a list for more: always a list."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def one(data: dict, key: str) -> dict:
    r = data.get(key) or []
    return r[0] if isinstance(r, list) and r and isinstance(r[0], dict) else {}


def scalar(data: dict, key: str):
    """@(x) around a plain value comes back as [x]."""
    v = data.get(key)
    if isinstance(v, list):
        return v[0] if v else None
    return v
