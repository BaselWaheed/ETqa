"""Shared helpers for Phase 0 scripts. Standard library only."""
import json
import os
import pathlib
import platform
import sys
from datetime import datetime, timezone

REPORT_DIR = pathlib.Path(os.environ.get("ETQA_PHASE0_DIR", "phase0_report"))


def save(name: str, data: dict) -> pathlib.Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    data = {"generated_at": datetime.now(timezone.utc).isoformat(), "host": platform.node(), **data}
    path = REPORT_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {path}")
    return path


def memory_mb() -> dict:
    """Total and available physical memory in MB (Windows and Linux)."""
    if sys.platform == "win32":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return {"total_mb": stat.ullTotalPhys // 2**20, "available_mb": stat.ullAvailPhys // 2**20}
    info = {}
    try:
        for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            info[key] = int(value.split()[0]) // 1024
        return {"total_mb": info.get("MemTotal"), "available_mb": info.get("MemAvailable")}
    except OSError:
        return {"total_mb": None, "available_mb": None}


def mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None
