"""Turns each supported file type into ordered Blocks with locators (page / sheet / section)."""
from __future__ import annotations

import csv
import io
import re

from apps.sysconfig.services import get as setting

from . import ocr
from .blocks import Block, Extraction, PageRecord

NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+){0,5})\.?\s+(\S.{0,110})$")


class ExtractionError(Exception):
    pass


def _paragraphs_with_headings(text: str, locator: str, out: Extraction) -> None:
    """Plain text (PDF page, TXT, OCR): numbered short lines become headings; blank lines split paragraphs."""
    para: list[str] = []

    def flush():
        if para:
            out.blocks.append(Block("para", " ".join(para).strip(), locator))
            para.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        m = NUMBERED_HEADING.match(line)
        if m and not line.endswith((".", ":", "،", "؛")) and len(line) < 120:
            flush()
            out.blocks.append(Block("heading", line, locator, level=m.group(1).count(".") + 1))
            out.inferred_headings += 1
        else:
            para.append(line)
    flush()


def _ocr_into(data: bytes, suffix: str, locator: str, out: Extraction) -> None:
    if not setting("ocr.enabled"):
        out.pages.append(PageRecord(locator, "ocr", "", None, True, "OCR disabled"))
        return
    try:
        text, conf = ocr.ocr_bytes(data, suffix)
    except ocr.OCRUnavailable as exc:
        out.pages.append(PageRecord(locator, "ocr", "", None, True, f"OCR unavailable: {str(exc)[:200]}"))
        return
    low = conf is None or conf < setting("ocr.review_confidence")
    out.pages.append(PageRecord(locator, "ocr", text, conf, low, "low OCR confidence" if low else ""))
    _paragraphs_with_headings(text, locator, out)


def extract_pdf(path: str) -> Extraction:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    out = Extraction()
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ExtractionError("The PDF is password-protected.")
        pages = list(reader.pages)
    except PdfReadError as exc:
        raise ExtractionError(f"The PDF could not be read: {exc}") from exc
    for n, page in enumerate(pages, 1):
        locator = f"p. {n}"
        text = page.extract_text() or ""
        if len(text.strip()) >= setting("ocr.min_text_chars"):
            out.pages.append(PageRecord(locator, "text", text))
            _paragraphs_with_headings(text, locator, out)
            continue
        images = []
        try:
            images = list(page.images)
        except Exception:  # noqa: BLE001 - unusual image encodings: treat as no image
            pass
        if not images:
            if text.strip():
                out.pages.append(PageRecord(locator, "text", text))
                _paragraphs_with_headings(text, locator, out)
            continue
        for img in images:  # scanned page: OCR its image(s)
            _ocr_into(img.data, "." + (img.name.rsplit(".", 1)[-1] if "." in img.name else "png"), locator, out)
    return out


def extract_docx(path: str) -> Extraction:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(path)
    except Exception as exc:  # noqa: BLE001 - python-docx raises several types for damaged files
        raise ExtractionError(f"The Word document could not be read: {exc}") from exc
    out = Extraction()
    full_text = []
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, document)
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name if para.style is not None else "") or ""
            level = 0
            if style.lower().startswith("heading"):
                digits = "".join(ch for ch in style if ch.isdigit())
                level = int(digits) if digits else 1
            elif style.lower() == "title":
                level = 1
            out.blocks.append(Block("heading" if level else "para", text, "Document", level=level))
            full_text.append(text)
        elif tag == "tbl":
            table = Table(child, document)
            header = ""
            for i, row in enumerate(table.rows):
                cells = []
                for cell in row.cells:
                    value = cell.text.strip()
                    if not cells or cells[-1] != value:  # merged cells repeat; keep one
                        cells.append(value)
                line = " | ".join(cells)
                if not line.strip(" |"):
                    continue
                if i == 0:
                    header = line
                out.blocks.append(Block("row", line, "Document", header=header if i else ""))
                full_text.append(line)
    out.pages.append(PageRecord("Document", "text", "\n".join(full_text)))
    for rel in document.part.rels.values():
        if "image" in rel.reltype:
            try:
                out.images.append((f"image {rel.rId}", rel.target_part.blob))
            except Exception:  # noqa: BLE001 - external/linked images
                continue
    return out


def _rows_to_blocks(rows, locator_prefix: str, out: Extraction) -> None:
    header_cells: list[str] = []
    header = ""
    texts = []
    for n, row in enumerate(rows, 1):
        cells = ["" if v is None else str(v).strip() for v in row]
        if not any(cells):
            continue
        if not header_cells:
            header_cells = cells
            header = " | ".join(cells)
            out.blocks.append(Block("row", header, f"{locator_prefix} row {n}"))
            texts.append(header)
            continue
        pairs = [f"{h or f'col{i + 1}'}: {v}" for i, (h, v) in enumerate(zip(header_cells + [""] * len(cells), cells)) if v]
        line = " | ".join(pairs)
        out.blocks.append(Block("row", line, f"{locator_prefix} row {n}", header=header))
        texts.append(line)
    out.pages.append(PageRecord(locator_prefix, "text", "\n".join(texts)))


def extract_xlsx(path: str) -> Extraction:
    import openpyxl

    out = Extraction()
    # A file handle, not the path: stored files have no extension and openpyxl checks extensions.
    with open(path, "rb") as fh:
        try:
            wb = openpyxl.load_workbook(fh, read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError(f"The Excel file could not be read: {exc}") from exc
        try:
            for ws in wb.worksheets:
                out.blocks.append(Block("heading", f"Sheet: {ws.title}", f"sheet {ws.title}", level=1))
                _rows_to_blocks(ws.iter_rows(values_only=True), f"sheet {ws.title}", out)
        finally:
            wb.close()
    return out


def _decode(path: str) -> str:
    raw = open(path, "rb").read()  # noqa: SIM115
    for enc in setting("upload.text_encodings"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ExtractionError("The text encoding is not supported.")


def extract_csv(path: str) -> Extraction:
    text = _decode(path)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    out = Extraction()
    _rows_to_blocks(csv.reader(io.StringIO(text), dialect), "row-set", out)
    for block in out.blocks:
        block.locator = block.locator.replace("row-set ", "")
    return out


def extract_txt(path: str) -> Extraction:
    text = _decode(path)
    out = Extraction()
    out.pages.append(PageRecord("Document", "text", text))
    _paragraphs_with_headings(text, "Document", out)
    return out


def extract_image(path: str, suffix: str) -> Extraction:
    out = Extraction()
    data = open(path, "rb").read()  # noqa: SIM115
    _ocr_into(data, suffix, "image", out)
    out.images.append(("image", data))
    return out


def extract(path: str, file_type: str) -> Extraction:
    if file_type == "pdf":
        return extract_pdf(path)
    if file_type == "docx":
        return extract_docx(path)
    if file_type == "xlsx":
        return extract_xlsx(path)
    if file_type == "csv":
        return extract_csv(path)
    if file_type == "txt":
        return extract_txt(path)
    if file_type in ("png", "jpg"):
        return extract_image(path, "." + file_type)
    raise ExtractionError(f"No extractor for {file_type}")
