from __future__ import annotations

from pathlib import Path
import re

from pipeline.models import Block


HEADER_PREFIX = "Acme Enterprise Quarterly Operating Report"


def _table_to_markdown(rows: list[list[str | None]]) -> str:
    cleaned = [["" if cell is None else str(cell).strip() for cell in row] for row in rows if row]
    if not cleaned:
        return ""
    header = cleaned[0]
    separator = ["---" for _ in header]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in cleaned[1:]:
        padded = row + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(padded[: len(header)]) + " |")
    return "\n".join(lines)


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _union_bbox(boxes: list[dict[str, float]]) -> dict[str, float] | None:
    if not boxes:
        return None
    return {
        "x0": round(min(box["x0"] for box in boxes), 2),
        "top": round(min(box["top"] for box in boxes), 2),
        "x1": round(max(box["x1"] for box in boxes), 2),
        "bottom": round(max(box["bottom"] for box in boxes), 2),
    }


def _bbox_inside(inner: dict[str, float], outer: tuple[float, float, float, float]) -> bool:
    x0, top, x1, bottom = outer
    return inner["x0"] >= x0 and inner["x1"] <= x1 and inner["top"] >= top and inner["bottom"] <= bottom


def _split_row_on_gaps(row: list[dict], page_width: float, page_height: float, min_gap: float = 36.0) -> list[list[dict]]:
    ordered = sorted(row, key=lambda item: float(item["x0"]))
    segments: list[list[dict]] = []
    current: list[dict] = []
    previous_x1: float | None = None
    for word in ordered:
        x0 = float(word["x0"])
        if previous_x1 is not None and x0 - previous_x1 > min_gap and current:
            segments.append(current)
            current = []
        current.append(word)
        previous_x1 = float(word["x1"])
    if current:
        segments.append(current)

    midpoint = page_width / 2
    split_segments: list[list[dict]] = []
    for segment in segments:
        x0 = min(float(item["x0"]) for item in segment)
        x1 = max(float(item["x1"]) for item in segment)
        top = min(float(item["top"]) for item in segment)
        spans_text_area = x0 < page_width * 0.12 and x1 > page_width * 0.88
        body_row_spans_midpoint = top > page_height * 0.13 and x1 - x0 > page_width * 0.45 and x0 < midpoint < x1
        has_left_words = any((float(item["x0"]) + float(item["x1"])) / 2 < midpoint - 8 for item in segment)
        has_right_words = any((float(item["x0"]) + float(item["x1"])) / 2 > midpoint + 8 for item in segment)
        if (spans_text_area or body_row_spans_midpoint) and has_left_words and has_right_words:
            left = [item for item in segment if (float(item["x0"]) + float(item["x1"])) / 2 < midpoint]
            right = [item for item in segment if (float(item["x0"]) + float(item["x1"])) / 2 >= midpoint]
            if left:
                split_segments.append(left)
            if right:
                split_segments.append(right)
        else:
            split_segments.append(segment)
    return split_segments


def _line_bboxes(page, excluded_bboxes: list[tuple[float, float, float, float]] | None = None) -> list[dict[str, object]]:
    excluded_bboxes = excluded_bboxes or []
    words = page.extract_words(x_tolerance=1, y_tolerance=3, keep_blank_chars=False)
    rows: list[list[dict]] = []
    for word in words:
        for row in rows:
            if abs(float(row[0]["top"]) - float(word["top"])) <= 3:
                row.append(word)
                break
        else:
            rows.append([word])

    lines: list[dict[str, object]] = []
    for row in rows:
        for segment in _split_row_on_gaps(row, float(page.width), float(page.height)):
            text = " ".join(str(item["text"]) for item in segment)
            bbox = {
                "x0": round(min(float(item["x0"]) for item in segment), 2),
                "top": round(min(float(item["top"]) for item in segment), 2),
                "x1": round(max(float(item["x1"]) for item in segment), 2),
                "bottom": round(max(float(item["bottom"]) for item in segment), 2),
            }
            if any(_bbox_inside(bbox, excluded_bbox) for excluded_bbox in excluded_bboxes):
                continue
            lines.append({"text": _normalize_for_match(text), "bbox": bbox})
    return _order_lines_for_reading(page, lines)


def _order_lines_for_reading(page, lines: list[dict[str, object]]) -> list[dict[str, object]]:
    if not _looks_two_column(page, lines):
        return sorted(lines, key=lambda item: (item["bbox"]["top"], item["bbox"]["x0"]))  # type: ignore[index]

    midpoint = float(page.width) / 2
    left: list[dict[str, object]] = []
    right: list[dict[str, object]] = []
    preamble: list[dict[str, object]] = []
    full_width: list[dict[str, object]] = []

    column_tops = [
        item["bbox"]["top"]  # type: ignore[index]
        for item in lines
        if item["bbox"]["x1"] <= midpoint or item["bbox"]["x0"] >= midpoint  # type: ignore[index]
    ]
    column_start = min(column_tops) if column_tops else 0

    for item in lines:
        bbox = item["bbox"]  # type: ignore[assignment]
        if bbox["top"] < column_start and bbox["x0"] < midpoint < bbox["x1"]:
            preamble.append(item)
        elif bbox["x1"] <= midpoint:
            left.append(item)
        elif bbox["x0"] >= midpoint:
            right.append(item)
        else:
            full_width.append(item)

    sort_key = lambda item: (item["bbox"]["top"], item["bbox"]["x0"])  # type: ignore[index]
    return [*sorted(preamble, key=sort_key), *sorted(left, key=sort_key), *sorted(right, key=sort_key), *sorted(full_width, key=sort_key)]


def _looks_two_column(page, lines: list[dict[str, object]]) -> bool:
    midpoint = float(page.width) / 2
    left_count = sum(1 for item in lines if item["bbox"]["x1"] <= midpoint)  # type: ignore[index]
    right_count = sum(1 for item in lines if item["bbox"]["x0"] >= midpoint)  # type: ignore[index]
    return left_count >= 5 and right_count >= 5


def _annotate_lines(page, lines: list[dict[str, object]]) -> list[dict[str, object]]:
    midpoint = float(page.width) / 2
    for index, item in enumerate(lines):
        bbox = item["bbox"]  # type: ignore[assignment]
        if bbox["x1"] <= midpoint:
            column_id = "left"
        elif bbox["x0"] >= midpoint:
            column_id = "right"
        else:
            column_id = "full_width"
        item["column_id"] = column_id
        item["line_index"] = index
    return lines


def _line_content_type(line: str, bbox: dict[str, float], page_width: float) -> str:
    stripped = line.strip()
    if _is_section_heading(stripped) or _is_title_like(stripped, bbox, page_width):
        return "section_header"
    if re.match(r"^(fig\.|figure)\s+\d+|^table\s+[ivxlcdm\d]+", stripped, re.IGNORECASE):
        return "caption"
    if _looks_like_table_text(stripped):
        return "table_text"
    if _looks_like_equation(stripped, bbox, page_width):
        return "equation"
    return "paragraph"


def _is_section_heading(text: str) -> bool:
    return bool(
        re.match(r"^[IVXLCDM]+\.\s+\S+", text)
        or re.match(r"^[A-Z]\.\s+\S+", text)
        or re.match(r"^\d+(\.\d+)+\s+\S+", text)
        or re.match(r"^\d+\.\s+\S+", text)
    )


def _is_title_like(text: str, bbox: dict[str, float], page_width: float) -> bool:
    words = text.split()
    centered = bbox["x0"] > page_width * 0.15 and bbox["x1"] < page_width * 0.85
    return centered and len(words) <= 8 and (text.istitle() or text.isupper())


def _looks_like_table_text(text: str) -> bool:
    tokens = text.split()
    numeric_tokens = sum(1 for token in tokens if re.search(r"\d", token))
    return (
        len(tokens) >= 5
        and numeric_tokens >= 3
        and bool(re.search(r"\b(runtime|path|nodes|waypoints|success|goal|resolution|environment)\b", text, re.IGNORECASE))
    )


def _looks_like_equation(text: str, bbox: dict[str, float], page_width: float) -> bool:
    math_chars = len(re.findall(r"[=∈⊂∀σ∆ϵ{}\\()+−]", text))
    centered = bbox["x0"] > page_width * 0.12 and bbox["x1"] < page_width * 0.88
    return centered and math_chars >= 3 and len(text.split()) <= 18


def _section_level(text: str) -> int | None:
    if re.match(r"^[IVXLCDM]+\.\s+", text):
        return 1
    if re.match(r"^[A-Z]\.\s+", text):
        return 2
    if re.match(r"^\d+(\.\d+)+\s+", text) or re.match(r"^\d+\.\s+", text):
        return text.split()[0].count(".") + 1
    return None


def _should_start_new_block(current: list[dict[str, object]], item: dict[str, object]) -> bool:
    if not current:
        return False
    previous = current[-1]
    previous_bbox = previous["bbox"]  # type: ignore[assignment]
    bbox = item["bbox"]  # type: ignore[assignment]
    vertical_gap = bbox["top"] - previous_bbox["bottom"]
    previous_height = max(previous_bbox["bottom"] - previous_bbox["top"], 1)
    content_type = str(item["content_type"])
    previous_type = str(previous["content_type"])
    if content_type in {"section_header", "caption", "equation", "table_text"}:
        return True
    if previous_type in {"section_header", "caption", "equation", "table_text"}:
        return True
    if item.get("column_id") != previous.get("column_id"):
        return True
    return vertical_gap > max(previous_height * 1.35, 8)


def _line_dict(item: dict[str, object]) -> dict[str, object]:
    return {
        "text": item["text"],
        "bbox": item["bbox"],
        "column_id": item.get("column_id"),
        "line_index": item.get("line_index"),
    }


def extract_pdf(path: Path) -> list[Block]:
    import pdfplumber

    blocks: list[Block] = []
    doc_id = path.stem
    table_counter = 0

    with pdfplumber.open(path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            table_objects = page.find_tables()
            table_bboxes = [table_obj.bbox for table_obj in table_objects]
            line_items = _annotate_lines(page, _line_bboxes(page, table_bboxes))
            order = 0
            section = None
            section_path: list[str] = []
            block_lines: list[dict[str, object]] = []

            def flush_block() -> None:
                nonlocal block_lines, order, section
                if not block_lines:
                    return
                content_type = str(block_lines[0]["content_type"])
                text = " ".join(str(item["text"]) for item in block_lines)
                line_boxes = [item["bbox"] for item in block_lines]  # type: ignore[list-item]
                if content_type == "section_header":
                    level = _section_level(text)
                    if level:
                        del section_path[level - 1 :]
                        section_path.append(text)
                    section = text
                blocks.append(
                    Block(
                        block_id=f"{doc_id}_p{page_index}_block_{order}",
                        doc_id=doc_id,
                        source_file=path.name,
                        source_type="pdf",
                        content_type=content_type,
                        text=text,
                        page=page_index,
                        section=section,
                        bbox=_union_bbox(line_boxes),
                        reading_order=order,
                        metadata={
                            "extraction_confidence": 0.9 if content_type != "paragraph" else 0.86,
                            "line_bboxes": [_line_dict(item) for item in block_lines],
                            "section_path": list(section_path),
                            "column_id": block_lines[0].get("column_id"),
                        },
                    )
                )
                block_lines = []
                order += 1

            for line_item in line_items:
                line = str(line_item["text"]).strip()
                if line.startswith(HEADER_PREFIX) or line.startswith("Page "):
                    continue
                line_bbox = line_item["bbox"]  # type: ignore[assignment]
                line_item["content_type"] = _line_content_type(line, line_bbox, float(page.width))
                if _should_start_new_block(block_lines, line_item):
                    flush_block()
                block_lines.append(line_item)
                if line_item["content_type"] in {"section_header", "caption", "equation", "table_text"}:
                    flush_block()
            flush_block()

            for table_obj in table_objects:
                table = table_obj.extract()
                markdown = _table_to_markdown(table)
                if not markdown:
                    continue
                table_counter += 1
                x0, top, x1, bottom = table_obj.bbox
                blocks.append(
                    Block(
                        block_id=f"{doc_id}_p{page_index}_table_{table_counter}",
                        doc_id=doc_id,
                        source_file=path.name,
                        source_type="pdf",
                        content_type="table",
                        text=markdown,
                        page=page_index,
                        section=section,
                        bbox={
                            "x0": round(float(x0), 2),
                            "top": round(float(top), 2),
                            "x1": round(float(x1), 2),
                            "bottom": round(float(bottom), 2),
                        },
                        reading_order=order,
                        metadata={
                            "table_id": f"{doc_id}_tbl_{table_counter:03d}",
                            "extraction_confidence": 0.82,
                            "table_rows": len(table),
                            "section_path": list(section_path),
                        },
                    )
                )
                order += 1

    return blocks
