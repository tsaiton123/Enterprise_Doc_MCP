from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from textwrap import wrap
from typing import Any

import pdfplumber
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

from mcp_server import kb


RAW_DIR = Path("data/raw")


def reconstruct_pdf(source_file: str, output_path: Path, show_labels: bool = False) -> None:
    source_path = RAW_DIR / source_file
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    chunks = [
        chunk
        for chunk in _load_source_chunks(source_file)
        if chunk.get("page") is not None and chunk.get("bbox") is not None
    ]
    chunks_by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_page[int(chunk["page"])].append(chunk)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pdfplumber.open(source_path) as pdf:
        pdf_canvas = canvas.Canvas(str(output_path))
        for page_number, page in enumerate(pdf.pages, start=1):
            width = float(page.width)
            height = float(page.height)
            pdf_canvas.setPageSize((width, height))
            _draw_page_frame(pdf_canvas, width, height, source_file, page_number)
            page_chunks = _split_overlapping_chunks(chunks_by_page.get(page_number, []))
            for chunk in page_chunks:
                _draw_chunk(pdf_canvas, chunk, page_height=height, show_labels=show_labels)
            pdf_canvas.showPage()
        pdf_canvas.save()


def _load_source_chunks(source_file: str) -> list[dict[str, Any]]:
    docs = kb.list_documents()
    if source_file not in {doc["source_file"] for doc in docs}:
        raise ValueError(f"{source_file} is not present in output/cleaned_chunks.json")
    chunks: list[dict[str, Any]] = []
    for page in range(1, 1000):
        page_chunks = kb.get_chunks_by_page(source_file, page)
        if page_chunks:
            chunks.extend(page_chunks)
        elif chunks and page > max(int(chunk["page"]) for chunk in chunks) + 5:
            break
    return chunks


def _split_overlapping_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[float, float, float, float], list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        bbox = chunk["bbox"]
        key = (float(bbox["x0"]), float(bbox["top"]), float(bbox["x1"]), float(bbox["bottom"]))
        groups[key].append(chunk)

    adjusted: list[dict[str, Any]] = []
    for key, group in groups.items():
        x0, top, x1, bottom = key
        if len(group) == 1:
            adjusted.append(group[0])
            continue
        slice_height = max((bottom - top) / len(group), 18)
        for index, chunk in enumerate(sorted(group, key=lambda item: item["chunk_id"])):
            clone = dict(chunk)
            clone["bbox"] = {
                "x0": x0,
                "top": top + index * slice_height,
                "x1": x1,
                "bottom": min(bottom, top + (index + 1) * slice_height),
            }
            clone["metadata"] = {**chunk.get("metadata", {}), "bbox_note": "subdivided_shared_chunk_region"}
            adjusted.append(clone)
    return sorted(adjusted, key=lambda chunk: (chunk["page"], chunk["bbox"]["top"], chunk["bbox"]["x0"], chunk["chunk_id"]))


def _draw_page_frame(pdf_canvas: canvas.Canvas, width: float, height: float, source_file: str, page_number: int) -> None:
    pdf_canvas.setStrokeColor(HexColor("#DDDDDD"))
    pdf_canvas.setLineWidth(0.5)
    pdf_canvas.rect(24, 24, width - 48, height - 48, stroke=1, fill=0)
    pdf_canvas.setFillColor(HexColor("#555555"))
    pdf_canvas.setFont("Helvetica", 8)
    pdf_canvas.drawString(28, height - 18, f"Reconstructed from chunks: {source_file} page {page_number}")


def _draw_chunk(pdf_canvas: canvas.Canvas, chunk: dict[str, Any], page_height: float, show_labels: bool = False) -> None:
    bbox = chunk["bbox"]
    x0 = float(bbox["x0"])
    x1 = float(bbox["x1"])
    top = float(bbox["top"])
    bottom = float(bbox["bottom"])
    y_top = page_height - top
    y_bottom = page_height - bottom
    width = max(x1 - x0, 20)
    height = max(y_top - y_bottom, 12)

    color = _color_for_type(chunk["content_type"])
    pdf_canvas.setStrokeColor(color)
    pdf_canvas.setLineWidth(0.6)
    pdf_canvas.rect(x0, y_bottom, width, height, stroke=1, fill=0)

    content_type = chunk["content_type"]
    font_name = "Helvetica-Bold" if content_type in {"section_header", "caption", "equation", "slide_title"} else "Helvetica"
    font_size = _font_size_for_chunk(content_type, height)
    pdf_canvas.setFillColor(HexColor("#111111"))
    pdf_canvas.setFont(font_name, font_size)
    text = chunk["text"].replace("\n", " ")
    chars_per_line = max(int(width / (font_size * 0.48)), 8)
    line_height = font_size + 1.5
    max_lines = max(int((height - 3) / line_height), 1)
    lines = wrap(text, width=chars_per_line)[:max_lines]
    text_y = y_top - font_size
    for line in lines:
        if text_y < y_bottom + 1:
            break
        pdf_canvas.drawString(x0 + 2, text_y, line)
        text_y -= line_height

    if show_labels:
        pdf_canvas.setFillColor(color)
        pdf_canvas.setFont("Helvetica", 4)
        label = f"{chunk['chunk_id']} [{content_type}]"
        pdf_canvas.drawString(x0 + 2, y_bottom - 5, label[:140])


def _font_size_for_chunk(content_type: str, height: float) -> float:
    if content_type == "section_header":
        return min(max(height * 0.72, 7), 11)
    if content_type == "equation":
        return min(max(height * 0.7, 6), 9)
    if content_type == "caption":
        return min(max(height * 0.55, 5.5), 7)
    return min(max(height / 3, 5.5), 7)


def _color_for_type(content_type: str):
    return {
        "header": HexColor("#C0392B"),
        "section_header": HexColor("#C0392B"),
        "equation": HexColor("#6C3483"),
        "caption": HexColor("#7D6608"),
        "table_text": HexColor("#1E8449"),
        "paragraph": HexColor("#1F618D"),
        "table": HexColor("#1E8449"),
        "table_row_summary": HexColor("#7D6608"),
        "slide_title": HexColor("#8E44AD"),
        "bullet_list": HexColor("#2874A6"),
        "speaker_notes": HexColor("#BA4A00"),
    }.get(content_type, HexColor("#34495E"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct a PDF by placing cleaned chunks at their extracted bboxes.")
    parser.add_argument("source_file")
    parser.add_argument("--output", default=None)
    parser.add_argument("--show-labels", action="store_true", help="Draw chunk ids below their bboxes for debugging.")
    args = parser.parse_args()

    output_path = Path(args.output or f"output/reconstructed_{Path(args.source_file).stem}.pdf")
    reconstruct_pdf(args.source_file, output_path, show_labels=args.show_labels)
    print(output_path)


if __name__ == "__main__":
    main()
