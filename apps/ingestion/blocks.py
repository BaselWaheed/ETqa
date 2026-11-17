from dataclasses import dataclass, field


@dataclass
class Block:
    kind: str            # heading | para | row
    text: str
    locator: str         # "p. 3", "sheet Rates", "Document"
    level: int = 0       # heading level
    header: str = ""     # for table rows: the header row text, repeated when a table spans chunks


@dataclass
class PageRecord:
    locator: str
    method: str          # text | ocr
    text: str
    confidence: float | None = None
    needs_review: bool = False
    note: str = ""


@dataclass
class Extraction:
    blocks: list[Block] = field(default_factory=list)
    pages: list[PageRecord] = field(default_factory=list)
    images: list[tuple[str, bytes]] = field(default_factory=list)  # (locator, bytes) for the vision model
    inferred_headings: int = 0
