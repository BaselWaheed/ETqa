"""Phase 0 / U11: can everything be installed and found without admin rights?

Usage:  python scripts/phase0/env_check.py [--pg "postgres://etqa:etqa@127.0.0.1:5432/etqa"]
Writes phase0_report/env.json. Standard library only.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request

from common import memory_mb, save


def run(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return out.returncode, (out.stdout + out.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)


def is_admin() -> bool | None:
    if sys.platform == "win32":
        import ctypes
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except OSError:
            return None
    return os.geteuid() == 0 if hasattr(os, "geteuid") else None


def cpu_info() -> dict:
    info = {"logical_cores": os.cpu_count(), "physical_cores": None, "name": platform.processor()}
    if sys.platform == "win32":
        code, out = run(["powershell", "-NoProfile", "-Command",
                         "Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores | ConvertTo-Json"])
        if code == 0 and out:
            try:
                data = json.loads(out)
                data = data if isinstance(data, list) else [data]
                info["physical_cores"] = sum(int(p["NumberOfCores"]) for p in data)
                info["name"] = data[0]["Name"].strip()
            except (ValueError, KeyError):
                pass
    return info


def postgres(pg_url: str | None) -> dict:
    result = {"psql_found": bool(shutil.which("psql"))}
    if not result["psql_found"]:
        return result
    result["version"] = run(["psql", "--version"])[1]
    if pg_url:
        code, out = run(["psql", pg_url, "-Atc",
                         "select name || '|' || coalesce(installed_version,'-') || '|' || default_version "
                         "from pg_available_extensions where name in ('pg_trgm','vector')"])
        result["connect_ok"] = code == 0
        if code == 0:
            exts = {line.split("|")[0]: {"installed": line.split("|")[1], "available": line.split("|")[2]}
                    for line in out.splitlines() if "|" in line}
            result["extensions"] = exts
        else:
            result["error"] = out[-300:]
    return result


def ollama(host: str) -> dict:
    result = {"binary_found": bool(shutil.which("ollama")),
              "env": {k: v for k, v in os.environ.items() if k.startswith("OLLAMA_")}}
    try:
        with urllib.request.urlopen(f"{host}/api/version", timeout=5) as r:
            result["version"] = json.load(r).get("version")
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as r:
            result["models"] = sorted(m["name"] for m in json.load(r).get("models", []))
        result["reachable"] = True
    except OSError as exc:
        result["reachable"] = False
        result["error"] = str(exc)
    return result


def tesseract() -> dict:
    if not shutil.which("tesseract"):
        return {"found": False}
    _, version = run(["tesseract", "--version"])
    _, langs = run(["tesseract", "--list-langs"])
    lang_set = {line.strip() for line in langs.splitlines()[1:]}
    return {"found": True, "version": version.splitlines()[0] if version else None,
            "ara": "ara" in lang_set, "eng": "eng" in lang_set}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pg", default=os.environ.get("ETQA_DATABASE_URL"), help="PostgreSQL URL to test the connection")
    parser.add_argument("--ollama", default="http://127.0.0.1:11434")
    args = parser.parse_args()

    disk = shutil.disk_usage(".")
    report = {
        "python": sys.version.split()[0], "platform": platform.platform(), "running_as_admin": is_admin(),
        "memory": memory_mb(), "cpu": cpu_info(), "disk_free_gb": round(disk.free / 2**30, 1),
        "postgres": postgres(args.pg), "ollama": ollama(args.ollama), "tesseract": tesseract(),
    }
    checks = [
        ("Python >= 3.11", tuple(map(int, report["python"].split(".")[:2])) >= (3, 11)),
        ("Not running as administrator (U11 wants a standard user)", report["running_as_admin"] is False),
        ("psql on PATH", report["postgres"]["psql_found"]),
        ("PostgreSQL connection", report["postgres"].get("connect_ok", False)),
        ("pg_trgm available", "pg_trgm" in report["postgres"].get("extensions", {})),
        ("pgvector available (needed by Phase 5)", "vector" in report["postgres"].get("extensions", {})),
        ("Ollama reachable", report["ollama"]["reachable"]),
        ("Tesseract with Arabic + English", report["tesseract"].get("ara") and report["tesseract"].get("eng")),
    ]
    report["checks"] = {name: bool(ok) for name, ok in checks}
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"RAM {report['memory']}, CPU {report['cpu']}")
    save("env", report)


if __name__ == "__main__":
    main()
