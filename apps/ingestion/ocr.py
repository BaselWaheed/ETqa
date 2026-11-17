"""Tesseract OCR via its command line (no Python binding needed on Windows).

Tesseract is optional. When it is missing, OCR pages are stored empty and flagged needs_review
(see extractors._ocr_into); every other document type is processed normally.
"""
import os
import shutil
import statistics
import subprocess
import tempfile

from apps.sysconfig.services import get as setting


class OCRUnavailable(Exception):
    pass


def tesseract_path() -> str | None:
    """Full path of the configured tesseract command, or None if it cannot be found."""
    command = setting("ocr.tesseract_command")
    if os.path.isfile(command):
        return command
    return shutil.which(command)


def status() -> dict:
    """OCR readiness for health checks: never raises."""
    if not setting("ocr.enabled"):
        return {"status": "disabled"}
    exe = tesseract_path()
    if exe is None:
        return {"status": "not_installed", "detail": "Images and scanned PDF pages are stored without text."}
    try:
        out = subprocess.run([exe, "--list-langs"], capture_output=True, timeout=30, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "detail": exc.__class__.__name__}
    installed = {line.strip() for line in out.stdout.splitlines()[1:] if line.strip()}
    wanted = [lang for lang in setting("ocr.languages").split("+") if lang]
    missing = [lang for lang in wanted if lang not in installed]
    return {"status": "missing_languages" if missing else "ok", "languages": sorted(installed), "missing": missing}


def ocr_bytes(data: bytes, suffix: str = ".png") -> tuple[str, float | None]:
    exe = tesseract_path()
    if exe is None:  # fail fast, without writing a temporary file
        raise OCRUnavailable("Tesseract is not installed")
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return ocr_file(path)
    finally:
        os.remove(path)


def ocr_file(path: str) -> tuple[str, float | None]:
    exe = tesseract_path()
    if exe is None:
        raise OCRUnavailable("Tesseract is not installed")
    cmd = [exe, path, "stdout", "-l", setting("ocr.languages"), "--psm", "3"]
    try:
        tsv = subprocess.run(cmd + ["tsv"], capture_output=True, timeout=300, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OCRUnavailable(str(exc)) from exc
    if tsv.returncode != 0:
        raise OCRUnavailable(tsv.stderr[-300:])
    lines: dict[tuple, list[str]] = {}
    confs = []
    for row in tsv.stdout.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or not cols[11].strip():
            continue
        key = tuple(cols[1:5])  # page, block, paragraph, line
        lines.setdefault(key, []).append(cols[11])
        try:
            if float(cols[10]) >= 0:
                confs.append(float(cols[10]))
        except ValueError:
            pass
    text = "\n".join(" ".join(words) for words in lines.values())
    return text, (round(statistics.mean(confs), 1) if confs else None)
