"""Section-aware chunking (section 3, Chunking):
- a heading always starts a chunk, together with its body;
- each chunk records its section path, which also prefixes the embedded text;
- paragraphs fill chunks to the target size with overlap inside the same section;
- table rows are never split; a table continuing into a new chunk repeats its header row;
- anything larger than the hard cap is split."""
from __future__ import annotations

import re

from apps.ai.tokens import count
from apps.retrieval import text as textutil
from apps.sysconfig.services import get as setting

from .blocks import Block

_SENTENCE = re.compile(r"(?<=[.!?؟。])\s+")


def _locator_range(first: str, last: str) -> str:
    if first == last:
        return first
    if first.startswith("p. ") and last.startswith("p. "):
        return f"pp. {first[3:]}-{last[3:]}"
    return f"{first} to {last}"


def _split_long(text: str, cap: int, tokenizer: str) -> list[str]:
    pieces, current = [], ""
    for sentence in _SENTENCE.split(text):
        candidate = f"{current} {sentence}".strip()
        if current and count(candidate, tokenizer) > cap:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    out = []
    for piece in pieces:  # a single sentence over the cap: hard split by characters
        while count(piece, tokenizer) > cap:
            cut = int(len(piece) * cap / count(piece, tokenizer))
            out.append(piece[:cut])
            piece = piece[cut:]
        out.append(piece)
    return out


class Chunker:
    def __init__(self, tokenizer: str = "", patterns: list[str] | None = None):
        self.target = setting("chunk.target_tokens")
        self.cap = setting("chunk.max_tokens")
        self.overlap = setting("chunk.overlap_ratio")
        self.tokenizer = tokenizer
        self.flags = [re.compile(p, re.IGNORECASE) for p in (patterns if patterns is not None
                                                             else setting("security.injection_patterns"))]
        self.out: list[dict] = []
        self.headings: list[tuple[int, str]] = []
        self.lines: list[str] = []
        self.body = False
        self.tokens = 0
        self.first_loc = self.last_loc = ""
        self.table_header = ""

    @property
    def section_path(self) -> str:
        return " > ".join(text for _, text in self.headings)

    def _add(self, text: str, locator: str, is_body: bool) -> None:
        if not self.lines:
            self.first_loc = locator
        self.last_loc = locator
        self.lines.append(text)
        self.tokens += count(text, self.tokenizer)
        self.body = self.body or is_body

    def _emit(self) -> None:
        text = "\n".join(self.lines).strip()
        if text:
            path = self.section_path
            self.out.append({
                "section_path": path[:500],
                "locator": _locator_range(self.first_loc, self.last_loc)[:120],
                "text": text,
                "search_text": textutil.normalize(f"{path}\n{text}"),
                "identifiers": " ".join(textutil.identifiers(text))[:20000],
                "lang": textutil.detect_language(text),
                "token_count": count(text, self.tokenizer),
                "flags": ["possible_injection"] if any(p.search(text) for p in self.flags) else [],
            })
        self.lines, self.body, self.tokens = [], False, 0

    def _flush(self, keep_overlap: bool) -> None:
        tail = []
        if keep_overlap and self.lines:
            budget = int(self.target * self.overlap)
            for line in reversed(self.lines):
                sentences = _SENTENCE.split(line)
                for s in reversed(sentences):
                    if count(" ".join([s] + tail), self.tokenizer) > budget:
                        break
                    tail.insert(0, s)
                break  # overlap only from the last paragraph
        loc = self.last_loc
        self._emit()
        if tail:
            self._add(" ".join(tail), loc, is_body=False)

    def feed(self, block: Block) -> None:
        if block.kind == "heading":
            if self.body:
                self._flush(keep_overlap=False)
            level = max(block.level, 1)
            self.headings = [h for h in self.headings if h[0] < level] + [(level, block.text)]
            self.table_header = ""
            self._add(block.text, block.locator, is_body=False)
            return
        size = count(block.text, self.tokenizer)
        if block.kind == "row":
            if block.header and block.header != self.table_header:
                self.table_header = block.header
            if self.body and self.tokens + size > self.target:
                self._flush(keep_overlap=False)
                if self.table_header and block.header:
                    self._add(self.table_header, block.locator, is_body=False)
            pieces = [block.text] if size <= self.cap else _split_long(block.text, self.cap, self.tokenizer)
            for piece in pieces:
                if self.body and self.tokens + count(piece, self.tokenizer) > self.cap:
                    self._flush(keep_overlap=False)
                self._add(piece, block.locator, is_body=True)
            return
        pieces = [block.text] if size <= self.target else _split_long(block.text, self.target, self.tokenizer)
        for piece in pieces:
            if self.body and self.tokens + count(piece, self.tokenizer) > self.target:
                self._flush(keep_overlap=True)
            self._add(piece, block.locator, is_body=True)

    def finish(self) -> list[dict]:
        self._emit()
        return self.out


def chunk_blocks(blocks: list[Block], tokenizer: str = "") -> list[dict]:
    chunker = Chunker(tokenizer)
    for block in blocks:
        chunker.feed(block)
    return chunker.finish()
