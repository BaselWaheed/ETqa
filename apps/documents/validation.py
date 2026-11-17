"""Upload validation: type by content (magic bytes), size per type, zip-bomb and macro guards (section 6)."""
import io
import zipfile

from apps.sysconfig.services import get as setting


class UploadRejected(Exception):
    pass


EXTENSIONS = {"pdf": "pdf", "docx": "docx", "xlsx": "xlsx", "csv": "csv", "txt": "txt",
              "png": "png", "jpg": "jpg", "jpeg": "jpg"}


def _zip_kind(head: bytes, uploaded) -> str:
    uploaded.seek(0)
    data = uploaded.read()
    uploaded.seek(0)
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UploadRejected("The file is damaged or not a valid Office document.") from exc
    infos = zf.infolist()
    if len(infos) > setting("upload.zip_max_entries"):
        raise UploadRejected("The document contains too many internal parts.")
    total = sum(i.file_size for i in infos)
    if total > setting("upload.zip_max_uncompressed_mb") * 2**20:
        raise UploadRejected("The document expands to an unsafe size.")
    names = {i.filename for i in infos}
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        raise UploadRejected("Documents with macros are not accepted. Save it as .docx or .xlsx without macros.")
    if "[Content_Types].xml" not in names:
        raise UploadRejected("Unsupported file type.")
    if any(n.startswith("word/") for n in names):
        return "docx"
    if any(n.startswith("xl/") for n in names):
        return "xlsx"
    raise UploadRejected("Unsupported Office file type.")


def _text_ok(uploaded) -> bool:
    uploaded.seek(0)
    sample = uploaded.read(64 * 1024)
    uploaded.seek(0)
    if b"\x00" in sample:
        return False
    for enc in setting("upload.text_encodings"):
        try:
            sample.decode(enc)
            return True
        except UnicodeDecodeError:
            continue
    return False


def detect_type(uploaded) -> str:
    """Returns the verified file type or raises UploadRejected. The extension must agree with the content."""
    name = (uploaded.name or "").lower()
    ext = EXTENSIONS.get(name.rsplit(".", 1)[-1] if "." in name else "")
    if ext is None:
        raise UploadRejected("Unsupported file type. Allowed: PDF, DOCX, XLSX, CSV, TXT, PNG, JPG.")
    uploaded.seek(0)
    head = uploaded.read(16)
    uploaded.seek(0)
    if head.startswith(b"%PDF-"):
        actual = "pdf"
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        actual = "png"
    elif head.startswith(b"\xff\xd8\xff"):
        actual = "jpg"
    elif head.startswith(b"PK\x03\x04"):
        actual = _zip_kind(head, uploaded)
    elif ext in ("csv", "txt") and _text_ok(uploaded):
        actual = ext
    else:
        raise UploadRejected("The file content does not match a supported type.")
    if actual != ext:
        raise UploadRejected(f"The file extension says {ext.upper()} but the content is {actual.upper()}.")
    limit_mb = setting("upload.max_mb").get(actual, 10)
    if uploaded.size > limit_mb * 2**20:
        raise UploadRejected(f"{actual.upper()} files are limited to {limit_mb} MB.")
    return actual
