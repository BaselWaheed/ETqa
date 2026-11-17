"""Fails if likely secrets are committed (Phase 1 gate). Usage: python scripts/check_secrets.py"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "logs", "media", "staticfiles", "phase0_report"}
SKIP_FILES = {".env"}  # local only, ignored by git
PATTERNS = [
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(secret_key|password|passwd|api_key|token)\s*[:=]\s*['\"][^'\"\s]{16,}['\"]"),
    re.compile(r"postgres(ql)?://[^:\s/]+:[^@\s]{6,}@(?!127\.0\.0\.1|localhost)"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]
ALLOW = re.compile(r"change-me|dev-only|test-only|example|Correct-Horse|:'\w+'")


def scan() -> list[str]:
    hits = []
    for path in ROOT.rglob("*"):
        if path.is_dir() or path.name in SKIP_FILES or SKIP_DIRS.intersection(path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".pdf", ".docx", ".xlsx", ".zip", ".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(p.search(line) for p in PATTERNS) and not ALLOW.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{lineno}")
    return hits


if __name__ == "__main__":
    found = scan()
    for hit in found:
        print("possible secret:", hit)
    sys.exit(1 if found else 0)
