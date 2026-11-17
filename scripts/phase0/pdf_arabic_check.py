"""Phase 0 / U5: does pypdf return Arabic in logical (reading) order?

Usage:  pip install --user pypdf
        python scripts/phase0/pdf_arabic_check.py path/to/pdf_folder
Writes each page's extracted text to phase0_report/pdf/ for side-by-side comparison with the rendered page,
plus a heuristic score per page. The heuristic counts words that start with the article "ال" against words that
end with "لا" (its mirror image). In correctly ordered Arabic the first is far more common; when extraction
reverses the text, the second dominates.
"""
import pathlib
import re
import sys

from common import REPORT_DIR, save

ARABIC = re.compile(r"[\u0600-\u06FF]")
WORD = re.compile(r"[\u0600-\u06FF]+")


def score(text: str) -> dict:
    words = WORD.findall(text)
    starts = sum(w.startswith("ال") for w in words)
    ends = sum(w.endswith("لا") for w in words)
    letters = len(ARABIC.findall(text))
    ratio = round(letters / max(len(text.strip()), 1), 2)
    if len(words) < 20:
        verdict = "too little Arabic to judge"
    elif starts >= 3 * max(ends, 1):
        verdict = "logical order (likely correct)"
    elif ends >= 3 * max(starts, 1):
        verdict = "REVERSED (visual order)"
    else:
        verdict = "unclear - inspect manually"
    return {"arabic_ratio": ratio, "arabic_words": len(words), "starts_with_al": starts, "ends_with_la": ends,
            "verdict": verdict}


def main() -> None:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit("pypdf is not installed: pip install --user pypdf")
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    folder = pathlib.Path(sys.argv[1])
    out_dir = REPORT_DIR / "pdf"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for pdf in sorted(folder.glob("*.pdf")):
        pages = []
        for n, page in enumerate(PdfReader(pdf).pages, 1):
            text = page.extract_text() or ""
            (out_dir / f"{pdf.stem}_p{n}.txt").write_text(text, encoding="utf-8")
            pages.append({"page": n, **score(text)})
        results[pdf.name] = pages
        reversed_pages = [p["page"] for p in pages if p["verdict"].startswith("REVERSED")]
        print(f"{pdf.name}: {len(pages)} pages, reversed: {reversed_pages or 'none'}")
    save("pdf_arabic", {"folder": str(folder), "files": results})


if __name__ == "__main__":
    main()
