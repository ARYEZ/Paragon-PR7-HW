"""The made-up PC of the mock-up as PowerShell would answer wmi.script() (PowerShell 5's JSON, dates as /Date(ms)/):
`python tools/sample_pc.py` writes tests/data/studio.json; screenshots and tests read it."""

import json
import time
from pathlib import Path

NOW = time.time()


def ms(t):
    return f"/Date({int(t * 1000)})/"


def name(s):
    return [ord(c) for c in s] + [0] * (13 - len(s)) if len(s) < 13 else [ord(c) for c in s]


DATA = {
    "cpu": {"Name": "AMD Ryzen 9 7950X 16-Core Processor            ", "Manufacturer": "AuthenticAMD", "NumberOfCores": 16,
            "NumberOfLogicalProcessors": 32, "MaxClockSpeed": 4501, "CurrentClockSpeed": 4501, "SocketDesignation": "AM5",
            "L2CacheSize": 16384, "L3CacheSize": 65536, "ProcessorId": "178BFBFF00A60F12",
            "Caption": "AMD64 Family 25 Model 97 Stepping 2", "VirtualizationFirmwareEnabled": True, "AddressWidth": 64},
    "system": {"Manufacturer": "ASUS", "Model": "System Product Name", "Name": "STUDIO-PC",
               "TotalPhysicalMemory": 67_755_065_344, "SystemType": "x64-based PC", "PCSystemType": 1},
    "board": {"Manufacturer": "ASUSTeK COMPUTER INC.", "Product": "ROG STRIX X670E-E GAMING WIFI", "Version": "Rev 1.xx",
              "SerialNumber": "230512345678901"},
    "bios": {"Manufacturer": "American Megatrends Inc.", "SMBIOSBIOSVersion": "2613",
             "ReleaseDate": {"value": ms(time.mktime((2026, 8, 14, 12, 0, 0, 0, 0, -1))), "DisplayHint": 2,
                             "DateTime": "Friday, 14 August 2026 12:00:00"},
             "SMBIOSMajorVersion": 3, "SMBIOSMinorVersion": 6},
    "memory": [{"BankLabel": "P0 CHANNEL A", "DeviceLocator": "DIMM_A2", "Capacity": 34_359_738_368, "Speed": 4800,
                "ConfiguredClockSpeed": 6000, "Manufacturer": "G Skill Intl", "PartNumber": "F5-6000J3040G32G    ",
                "SerialNumber": "00000000", "SMBIOSMemoryType": 34, "FormFactor": 8, "ConfiguredVoltage": 1350},
               {"BankLabel": "P0 CHANNEL B", "DeviceLocator": "DIMM_B2", "Capacity": 34_359_738_368, "Speed": 4800,
                "ConfiguredClockSpeed": 6000, "Manufacturer": "G Skill Intl", "PartNumber": "F5-6000J3040G32G    ",
                "SerialNumber": "00000000", "SMBIOSMemoryType": 34, "FormFactor": 8, "ConfiguredVoltage": 1350}],
    "memory_slots": {"MemoryDevices": 4, "MaxCapacityEx": 201_326_592},
    "gpu": [{"Name": "NVIDIA GeForce RTX 4080 SUPER", "AdapterCompatibility": "NVIDIA", "DriverVersion": "32.0.15.6614",
             "DriverDate": ms(time.mktime((2026, 11, 4, 0, 0, 0, 0, 0, -1))), "AdapterRAM": 4_293_918_720,
             "CurrentHorizontalResolution": 3840, "CurrentVerticalResolution": 2160, "CurrentRefreshRate": 144,
             "VideoProcessor": "NVIDIA GeForce RTX 4080 SUPER", "PNPDeviceID": "PCI\\VEN_10DE&DEV_2702"},
            {"Name": "AMD Radeon(TM) Graphics", "AdapterCompatibility": "Advanced Micro Devices, Inc.",
             "DriverVersion": "32.0.12011.1036", "DriverDate": ms(time.mktime((2026, 9, 1, 0, 0, 0, 0, 0, -1))),
             "AdapterRAM": 536_870_912, "CurrentHorizontalResolution": None, "CurrentVerticalResolution": None,
             "CurrentRefreshRate": None, "VideoProcessor": "AMD Radeon Graphics Processor (0x164E)",
             "PNPDeviceID": "PCI\\VEN_1002&DEV_164E"}],
    "gpu_memory": [{"Name": "NVIDIA GeForce RTX 4080 SUPER", "Bytes": 17_171_480_576},
                   {"Name": "AMD Radeon(TM) Graphics", "Bytes": 536_870_912}],
    "monitors": [{"ManufacturerName": name("DEL"), "UserFriendlyName": name("DELL U3225QE"),
                  "SerialNumberID": name("F7KQ3Z3"), "YearOfManufacture": 2025, "InstanceName": "DISPLAY\\DELA1F5"},
                 {"ManufacturerName": name("GSM"), "UserFriendlyName": name("LG 27QN880"),
                  "SerialNumberID": name("112NTQD4K123"), "YearOfManufacture": 2023, "InstanceName": "DISPLAY\\GSM5B9C"}],
    "disks": [{"Index": 0, "Model": "Samsung SSD 990 PRO 2TB", "SerialNumber": "0025_3841_4140_1A2B.",
               "FirmwareRevision": "4B2QJXD7", "Size": 2_000_396_321_280, "InterfaceType": "SCSI", "Partitions": 4,
               "MediaType": "Fixed hard disk media", "PNPDeviceID": "SCSI\\DISK&VEN_NVME"},
              {"Index": 1, "Model": "WD_BLACK SN850X 4000GB", "SerialNumber": "E823_8FA6_BF53_0001.",
               "FirmwareRevision": "620361WD", "Size": 4_000_784_417_280, "InterfaceType": "SCSI", "Partitions": 1,
               "MediaType": "Fixed hard disk media", "PNPDeviceID": "SCSI\\DISK&VEN_NVME"},
              {"Index": 2, "Model": "ST8000VN004-3CP101", "SerialNumber": "WWZ4ABCD", "FirmwareRevision": "SC60",
               "Size": 8_001_560_609_280, "InterfaceType": "IDE", "Partitions": 1, "MediaType": "Fixed hard disk media",
               "PNPDeviceID": "SCSI\\DISK&VEN_SEAGATE"}],
    "physical_disks": [{"DeviceId": "0", "FriendlyName": "Samsung SSD 990 PRO 2TB", "MediaType": 4, "BusType": 17,
                        "HealthStatus": 0, "SpindleSpeed": 0, "Size": 2_000_398_934_016},
                       {"DeviceId": "1", "FriendlyName": "WD_BLACK SN850X 4000GB", "MediaType": 4, "BusType": 17,
                        "HealthStatus": 0, "SpindleSpeed": 0, "Size": 4_000_787_030_016},
                       {"DeviceId": "2", "FriendlyName": "ST8000VN004-3CP101", "MediaType": 3, "BusType": 11,
                        "HealthStatus": 0, "SpindleSpeed": 7200, "Size": 8_001_563_222_016}],
    "reliability": [{"DeviceId": "0", "Temperature": 41, "TemperatureMax": 63, "Wear": 3, "PowerOnHours": 6412,
                     "StartStopCycleCount": 1284, "ReadErrorsTotal": 0, "WriteErrorsTotal": 0},
                    {"DeviceId": "1", "Temperature": 44, "TemperatureMax": 70, "Wear": 1, "PowerOnHours": 2210,
                     "StartStopCycleCount": 433, "ReadErrorsTotal": 0, "WriteErrorsTotal": 0},
                    {"DeviceId": "2", "Temperature": 36, "TemperatureMax": 45, "Wear": None, "PowerOnHours": 18_220,
                     "StartStopCycleCount": 96, "ReadErrorsTotal": 0, "WriteErrorsTotal": 0}],
    "volumes": [{"DeviceID": "C:", "VolumeName": "Windows", "FileSystem": "NTFS", "Size": 1_999_421_960_192,
                 "FreeSpace": 657_141_874_688},
                {"DeviceID": "D:", "VolumeName": "Studio", "FileSystem": "NTFS", "Size": 4_000_768_667_648,
                 "FreeSpace": 1_210_000_000_000},
                {"DeviceID": "E:", "VolumeName": "Archive", "FileSystem": "NTFS", "Size": 8_001_545_588_736,
                 "FreeSpace": 3_100_000_000_000}],
    "partitions": [{"DiskNumber": 0, "PartitionNumber": 1, "DriveLetter": None, "Size": 104_857_600, "Type": "System"},
                   {"DiskNumber": 0, "PartitionNumber": 2, "DriveLetter": None, "Size": 16_777_216, "Type": "Reserved"},
                   {"DiskNumber": 0, "PartitionNumber": 3, "DriveLetter": "C", "Size": 1_999_421_960_192, "Type": "Basic"},
                   {"DiskNumber": 0, "PartitionNumber": 4, "DriveLetter": None, "Size": 786_432_000, "Type": "Recovery"},
                   {"DiskNumber": 1, "PartitionNumber": 1, "DriveLetter": "D", "Size": 4_000_768_667_648, "Type": "Basic"},
                   {"DiskNumber": 2, "PartitionNumber": 1, "DriveLetter": "E", "Size": 8_001_545_588_736,
                    "Type": "Basic"}],
    "network": [{"Name": "Realtek Gaming 2.5GbE Family Controller", "Manufacturer": "Realtek",
                 "MACAddress": "A8:A1:59:12:34:56", "Speed": 2_500_000_000, "NetConnectionStatus": 2,
                 "NetConnectionID": "Ethernet", "AdapterType": "Ethernet 802.3"},
                {"Name": "Intel(R) Wi-Fi 7 BE200 320MHz", "Manufacturer": "Intel Corporation",
                 "MACAddress": "F4:26:79:AB:CD:EF", "Speed": 9_223_372_036_854_775_807, "NetConnectionStatus": 7,
                 "NetConnectionID": "Wi-Fi", "AdapterType": "Ethernet 802.3"}],
    "audio": [{"Name": "Realtek USB Audio", "Manufacturer": "Realtek", "Status": "OK"},
              {"Name": "NVIDIA High Definition Audio", "Manufacturer": "NVIDIA", "Status": "OK"}],
    "usb": [{"Name": "AMD USB 3.10 eXtensible Host Controller - 1.10 (Microsoft)", "Manufacturer": "Generic USB xHCI"},
            {"Name": "AMD USB 3.20 eXtensible Host Controller - 1.20 (Microsoft)", "Manufacturer": "Generic USB xHCI"}],
    "usb_devices": 11,
    "battery": None,
    "os": {"Caption": "Microsoft Windows 11 Pro", "Version": "10.0.26100", "BuildNumber": "26100", "OSArchitecture": "64-bit",
           "LastBootUpTime": ms(NOW - 3 * 86400 - 4 * 3600 - 120), "InstallDate": ms(NOW - 400 * 86400),
           "CSName": "STUDIO-PC", "TotalVisibleMemorySize": 66_167_056, "FreePhysicalMemory": 43_710_000},
    "display_version": "24H2", "ubr": 2454,
    "tpm": {"SpecVersion": "2.0, 0, 1.59", "ManufacturerIdTxt": "AMD", "IsEnabled_InitialValue": True},
    "secure_boot": True,
    "thermal": [{"InstanceName": "ACPI\\ThermalZone\\TZ00_0", "CurrentTemperature": 3272}],
    "admin": True,
}

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "tests" / "data" / "studio.json"
    # as PowerShell prints it: the dates are relative to "now", so tests read it through `answer()`
    out.write_text(json.dumps(DATA))
    print("wrote", out)
