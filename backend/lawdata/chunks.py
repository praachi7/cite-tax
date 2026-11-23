"""Corpus chunks (Phase C): the reviewed passages that retrieval returns and citations point to.

The source of truth is corpus/chunks/<SOURCE_ID>.yaml, one file per registry source.
The database index is rebuilt from these files.

Citation resolution (used by the coverage check and later by the stage 1 check in Phase D):
an ID resolves when it
  1. equals a chunk id or is listed in a chunk's `covers`;
  2. is `PREFIX:all` and the source has at least one chunk;
  3. is an ancestor of a chunk id (IT2025:s408 resolves through IT2025:s408(2)); or
  4. is a descendant of a chunk id whose extra labels all appear in that chunk's text
     (RULES2026:r164(6)(c) resolves through RULES2026:r164(6) if "(c)" or "c)" is in it).
"""
from __future__ import annotations

import hashlib
import re
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import Field, field_validator

from .loader import CORPUS_DIR
from .models import CITATION_RE, _Strict

CHUNKS_DIR = CORPUS_DIR / "chunks"
MAX_CHARS = 6000  # about 1,500 tokens; longer chunks are split or trimmed in review


class Extraction(str, Enum):
    auto = "auto"                      # straight from pdftotext, not yet corrected
    hand_corrected = "hand_corrected"  # auto text fixed by a person
    hand_typed = "hand_typed"          # typed from the PDF page (tables)


class Chunk(_Strict):
    id: str
    source_id: str
    covers: list[str] = Field(default_factory=list)
    breadcrumb: str
    heading: Optional[str] = None
    text: str
    tax_year_first: Optional[int] = None
    tax_year_last: Optional[int] = None
    authority_rank: int = Field(ge=1, le=5)
    pdf_pages: list[int] = Field(default_factory=list)
    cross_refs: list[str] = Field(default_factory=list)
    is_table: bool = False
    extraction: Extraction = Extraction.auto
    reviewed: bool = False
    note: Optional[str] = None

    @field_validator("id")
    @classmethod
    def _id_format(cls, v: str) -> str:
        if not CITATION_RE.match(v):
            raise ValueError(f"bad chunk id {v!r}")
        return v

    @property
    def embed_text(self) -> str:
        """What gets embedded: breadcrumb, heading and body together."""
        parts = [self.breadcrumb, self.heading or "", self.text]
        return "\n".join(p for p in parts if p)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.embed_text.encode("utf8")).hexdigest()[:16]


def load_chunk_file(path: Path) -> list[Chunk]:
    with open(path, encoding="utf8") as fh:
        data = yaml.safe_load(fh) or {}
    return [Chunk(**row) for row in data.get("chunks") or []]


def load_all_chunks(directory: Path = CHUNKS_DIR) -> list[Chunk]:
    out: list[Chunk] = []
    for path in sorted(directory.glob("*.yaml")):
        out.extend(load_chunk_file(path))
    return out


# ---------------------------------------------------------------- citation resolution

_LABEL_RE = re.compile(r"\(([^()]+)\)")


def _split(cid: str) -> tuple[str, str]:
    prefix, _, rest = cid.partition(":")
    return prefix, rest


def _labels_in_text(labels: list[str], text: str) -> bool:
    return all(f"({lab})" in text or f"{lab})" in text for lab in labels)


class Resolver:
    """Answers "does this citation ID point to a passage in the corpus?"."""

    def __init__(self, chunks: list[Chunk]):
        self.by_id: dict[str, Chunk] = {}
        self.prefixes: set[str] = set()
        for c in chunks:
            self.by_id[c.id] = c
            for alias in c.covers:
                self.by_id.setdefault(alias, c)
            self.prefixes.add(_split(c.id)[0])

    def resolve(self, cid: str) -> Optional[Chunk]:
        if cid in self.by_id:
            return self.by_id[cid]
        prefix, rest = _split(cid)
        if prefix not in self.prefixes:
            return None
        if rest == "all":
            return next(c for k, c in self.by_id.items() if k.startswith(prefix + ":"))
        # ancestor of a chunk: IT2025:s408 -> IT2025:s408(2); "/" parts count as children too
        for k, c in self.by_id.items():
            if k.startswith(cid) and k[len(cid):][:1] in ("(", "/"):
                return c
        # descendant of a chunk: walk up one label at a time
        head = cid
        extra: list[str] = []
        while True:
            m = re.search(r"(\([^()]+\)|/[^/]+)$", head)
            if not m:
                return None
            piece = m.group(1)
            if piece.startswith("("):
                extra.insert(0, piece[1:-1])
            else:
                return None  # a table row we do not have
            head = head[: m.start()]
            if head in self.by_id:
                c = self.by_id[head]
                return c if _labels_in_text(extra, c.text) else None
