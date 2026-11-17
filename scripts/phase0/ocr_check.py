"""Phase 0 / U6: Tesseract accuracy on scanned Arabic/English pages.

Usage:  python scripts/phase0/ocr_check.py path/to/images [--lang ara+eng] [--psm 3]
For each image (png/jpg/tif), put the correct text in a .txt file with the same name to get a character
error rate (CER). Without it, only Tesseract's own mean confidence is reported. Standard library only.
"""
import argparse
import pathlib
import re
import statistics
import subprocess
import time

from common import save

WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    text = re.sub(r"[\u064B-\u0652\u0640]", "", text)  # diacritics and tatweel do not count as errors
    return WS.sub(" ", text).strip()


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def ocr(image: pathlib.Path, lang: str, psm: int) -> tuple[str, float | None, float]:
    started = time.perf_counter()
    text = subprocess.run(["tesseract", str(image), "stdout", "-l", lang, "--psm", str(psm)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    tsv = subprocess.run(["tesseract", str(image), "stdout", "-l", lang, "--psm", str(psm), "tsv"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    confs = []
    for line in tsv.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) >= 12 and cols[11].strip():
            try:
                c = float(cols[10])
                if c >= 0:
                    confs.append(c)
            except ValueError:
                pass
    return text, (round(statistics.mean(confs), 1) if confs else None), round(time.perf_counter() - started, 2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder")
    parser.add_argument("--lang", default="ara+eng")
    parser.add_argument("--psm", type=int, default=3)
    args = parser.parse_args()
    rows = []
    for image in sorted(p for p in pathlib.Path(args.folder).iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}):
        text, conf, seconds = ocr(image, args.lang, args.psm)
        row = {"image": image.name, "mean_confidence": conf, "seconds": seconds}
        truth = image.with_suffix(".txt")
        if truth.exists():
            ref, hyp = normalize(truth.read_text(encoding="utf-8")), normalize(text)
            row["cer"] = round(levenshtein(hyp, ref) / max(len(ref), 1), 3)
        rows.append(row)
        print(row)
    cers = [r["cer"] for r in rows if "cer" in r]
    save("ocr", {"lang": args.lang, "psm": args.psm, "images": rows,
                 "mean_cer": round(statistics.mean(cers), 3) if cers else None,
                 "mean_seconds": round(statistics.mean(r["seconds"] for r in rows), 2) if rows else None})


if __name__ == "__main__":
    main()
