from __future__ import annotations

from pipeline.clean import normalize_text
from pipeline.models import Block, Chunk


def _union_bbox(boxes: list[dict]) -> dict | None:
    if not boxes:
        return None
    return {
        "x0": round(min(float(box["x0"]) for box in boxes), 2),
        "top": round(min(float(box["top"]) for box in boxes), 2),
        "x1": round(max(float(box["x1"]) for box in boxes), 2),
        "bottom": round(max(float(box["bottom"]) for box in boxes), 2),
    }


def chunk_blocks(blocks: list[Block], max_words: int = 90, overlap_words: int = 18) -> list[Chunk]:
    chunks: list[Chunk] = []
    seen: set[tuple[str, str, str]] = set()

    def add_chunk(block: Block, text: str, suffix: str, bbox: dict | None = None, metadata: dict | None = None) -> None:
        clean_text = normalize_text(text)
        fingerprint = (block.doc_id, block.content_type, clean_text.lower())
        if not clean_text or fingerprint in seen:
            return
        seen.add(fingerprint)
        table_id = block.metadata.get("table_id")
        locator = "p" + str(block.page) if block.page else "s" + str(block.slide)
        chunk_id = f"{block.doc_id}_{locator}_{block.reading_order}_{suffix}"
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=clean_text,
                content_type=block.content_type,
                source_file=block.source_file,
                doc_id=block.doc_id,
                page=block.page,
                slide=block.slide,
                section=block.section,
                table_id=table_id,
                bbox=bbox or block.bbox,
                reading_order=block.reading_order,
                parent_section=block.section,
                metadata={
                    **block.metadata,
                    **(metadata or {}),
                    "source_block_id": block.block_id,
                    "source_ref": f"{block.source_file}:{'page_' + str(block.page) if block.page else 'slide_' + str(block.slide)}",
                    "source_type": block.source_type,
                },
            )
        )
        if table_id:
            for row_index, row in enumerate(_table_row_summaries(clean_text), start=1):
                chunks.append(
                    Chunk(
                        chunk_id=f"{chunk_id}_row_{row_index}",
                        text=row,
                        content_type="table_row_summary",
                        source_file=block.source_file,
                        doc_id=block.doc_id,
                        page=block.page,
                        slide=block.slide,
                        section=block.section,
                        table_id=table_id,
                        bbox=block.bbox,
                        reading_order=block.reading_order,
                        parent_section=block.section,
                        metadata={
                            **block.metadata,
                            "source_ref": f"{block.source_file}:page_{block.page}",
                            "source_type": block.source_type,
                            "derived_from": chunk_id,
                        },
                    )
                )

    for block in blocks:
        if block.content_type in {"table", "header", "section_header", "caption", "equation", "table_text", "slide_title", "speaker_notes", "bullet_list"}:
            suffix = block.metadata.get("table_id", block.content_type)
            add_chunk(block, block.text, str(suffix))
            continue
        line_bboxes = block.metadata.get("line_bboxes", [])
        if line_bboxes:
            current_lines: list[dict] = []
            current_words = 0
            part = 1
            for line in line_bboxes:
                line_words = str(line["text"]).split()
                if current_lines and current_words + len(line_words) > max_words:
                    add_chunk(
                        block,
                        " ".join(str(item["text"]) for item in current_lines),
                        f"{block.content_type}_{block.reading_order}_{part}",
                        bbox=_union_bbox([item["bbox"] for item in current_lines]),
                        metadata={"line_bboxes": current_lines},
                    )
                    overlap_lines = current_lines[-2:] if len(current_lines) > 2 else current_lines[-1:]
                    current_lines = overlap_lines.copy()
                    current_words = sum(len(str(item["text"]).split()) for item in current_lines)
                    part += 1
                current_lines.append(line)
                current_words += len(line_words)
            if current_lines:
                add_chunk(
                    block,
                    " ".join(str(item["text"]) for item in current_lines),
                    f"{block.content_type}_{block.reading_order}_{part}",
                    bbox=_union_bbox([item["bbox"] for item in current_lines]),
                    metadata={"line_bboxes": current_lines},
                )
            continue
        words = block.text.split()
        if len(words) <= max_words:
            add_chunk(block, block.text, f"{block.content_type}_{block.reading_order}")
            continue
        start = 0
        part = 1
        while start < len(words):
            end = min(len(words), start + max_words)
            add_chunk(block, " ".join(words[start:end]), f"{block.content_type}_{block.reading_order}_{part}")
            if end == len(words):
                break
            start = max(0, end - overlap_words)
            part += 1

    for index, chunk in enumerate(chunks):
        chunk.neighbor_chunks = {
            "previous": chunks[index - 1].chunk_id if index > 0 else None,
            "next": chunks[index + 1].chunk_id if index < len(chunks) - 1 else None,
        }
    return chunks


def _table_row_summaries(markdown: str) -> list[str]:
    rows = [line for line in markdown.splitlines() if line.startswith("|") and "---" not in line]
    if len(rows) < 2:
        return []
    headers = [cell.strip() for cell in rows[0].strip("|").split("|")]
    summaries: list[str] = []
    for row in rows[1:]:
        values = [cell.strip() for cell in row.strip("|").split("|")]
        pairs = dict(zip(headers, values, strict=False))
        subject = values[0] if values else "Row"
        facts = ", ".join(f"{key} {value}" for key, value in pairs.items() if value)
        summaries.append(f"Table row summary: {subject} has {facts}.")
    return summaries
