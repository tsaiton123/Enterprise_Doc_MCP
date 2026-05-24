from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Block:
    block_id: str
    doc_id: str
    source_file: str
    source_type: str
    content_type: str
    text: str
    page: int | None = None
    slide: int | None = None
    section: str | None = None
    bbox: dict[str, float] | None = None
    reading_order: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "doc_id": self.doc_id,
            "source_file": self.source_file,
            "source_type": self.source_type,
            "content_type": self.content_type,
            "text": self.text,
            "page": self.page,
            "slide": self.slide,
            "section": self.section,
            "bbox": self.bbox,
            "reading_order": self.reading_order,
            "metadata": self.metadata,
        }

@dataclass
class Chunk:
    chunk_id: str
    text: str
    content_type: str
    source_file: str
    doc_id: str
    page: int | None = None
    slide: int | None = None
    section: str | None = None
    table_id: str | None = None
    bbox: dict[str, float] | None = None
    reading_order: int = 0
    parent_section: str | None = None
    neighbor_chunks: dict[str, str | None] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "content_type": self.content_type,
            "source_file": self.source_file,
            "doc_id": self.doc_id,
            "page": self.page,
            "slide": self.slide,
            "section": self.section,
            "table_id": self.table_id,
            "bbox": self.bbox,
            "reading_order": self.reading_order,
            "parent_section": self.parent_section,
            "neighbor_chunks": self.neighbor_chunks,
            "metadata": self.metadata,
        }
