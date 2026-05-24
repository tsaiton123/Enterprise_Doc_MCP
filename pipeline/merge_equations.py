from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from pipeline.models import Block


def load_equation_regions(paths: list[Path]) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for path in paths:
        regions.extend(json.loads(path.read_text(encoding="utf-8")))
    return regions


def merge_display_equations(
    blocks: list[Block],
    regions: list[dict[str, Any]],
    max_region_height: float = 24.0,
) -> list[Block]:
    merged_blocks = list(blocks)
    for region in regions:
        if region.get("region_type") != "display_equation" or not region.get("llm_latex"):
            continue
        bbox = region["bbox"]
        if float(bbox["bottom"]) - float(bbox["top"]) > max_region_height:
            continue
        merged_blocks = _merge_region(merged_blocks, region)
    return sorted(merged_blocks, key=_block_sort_key)


def _merge_region(blocks: list[Block], region: dict[str, Any]) -> list[Block]:
    component_boxes = [
        component["bbox"]
        for component in region.get("component_lines", [])
        if component.get("bbox")
    ]
    if not component_boxes:
        component_boxes = [region["bbox"]]

    survivors: list[Block] = []
    consumed_lines: list[dict[str, Any]] = []
    matched: list[Block] = []
    for block in blocks:
        if block.source_file != region.get("source_file") or block.page != region.get("page"):
            survivors.append(block)
            continue
        remaining_lines, removed_lines = _remove_component_lines(block, component_boxes)
        if not removed_lines:
            survivors.append(block)
            continue
        matched.append(block)
        consumed_lines.extend(removed_lines)
        if remaining_lines:
            survivors.append(_with_lines(block, remaining_lines))

    if not matched:
        return blocks

    anchor = min(matched, key=lambda block: block.reading_order)
    merged = Block(
        block_id=f"{region['region_id']}_merged",
        doc_id=anchor.doc_id,
        source_file=anchor.source_file,
        source_type=anchor.source_type,
        content_type="equation",
        text=region.get("llm_plain_text") or region["llm_latex"],
        page=anchor.page,
        slide=anchor.slide,
        section=anchor.section,
        bbox=dict(region["bbox"]),
        reading_order=anchor.reading_order,
        metadata={
            "extraction_confidence": region.get("llm_confidence", 0.9),
            "line_bboxes": [
                {
                    "text": region.get("llm_plain_text") or region["llm_latex"],
                    "bbox": dict(region["bbox"]),
                    "column_id": anchor.metadata.get("column_id"),
                    "line_index": min(
                        (
                            line.get("line_index", anchor.reading_order)
                            for block in matched
                            for line in block.metadata.get("line_bboxes", [])
                        ),
                        default=anchor.reading_order,
                    ),
                }
            ],
            "section_path": list(anchor.metadata.get("section_path", [])),
            "column_id": anchor.metadata.get("column_id"),
            "latex": region["llm_latex"],
            "llm_plain_text": region.get("llm_plain_text"),
            "llm_model": region.get("llm_model"),
            "equation_region_id": region["region_id"],
            "extraction_method": "pdfplumber_bbox_merge_with_llm_transcription",
            "consumed_component_count": len(consumed_lines),
            "consumed_block_ids": [block.block_id for block in matched],
        },
    )
    survivors.append(merged)
    return survivors


def _remove_component_lines(block: Block, component_boxes: list[dict[str, float]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lines = block.metadata.get("line_bboxes", [])
    if not lines:
        return [], []
    remaining: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for line in lines:
        if any(_coverage(line["bbox"], component_bbox) >= 0.45 for component_bbox in component_boxes):
            removed.append(deepcopy(line))
        else:
            remaining.append(deepcopy(line))
    return remaining, removed


def _coverage(inner: dict[str, float], outer: dict[str, float]) -> float:
    width = max(0.0, min(inner["x1"], outer["x1"]) - max(inner["x0"], outer["x0"]))
    height = max(0.0, min(inner["bottom"], outer["bottom"]) - max(inner["top"], outer["top"]))
    area = max(1.0, (inner["x1"] - inner["x0"]) * (inner["bottom"] - inner["top"]))
    return width * height / area


def _with_lines(block: Block, lines: list[dict[str, Any]]) -> Block:
    clone = deepcopy(block)
    clone.text = " ".join(str(line["text"]) for line in lines)
    clone.bbox = _union_bbox([line["bbox"] for line in lines])
    clone.metadata["line_bboxes"] = lines
    clone.metadata["math_component_lines_removed"] = True
    return clone


def _union_bbox(boxes: list[dict[str, float]]) -> dict[str, float]:
    return {
        "x0": round(min(box["x0"] for box in boxes), 2),
        "top": round(min(box["top"] for box in boxes), 2),
        "x1": round(max(box["x1"] for box in boxes), 2),
        "bottom": round(max(box["bottom"] for box in boxes), 2),
    }


def _block_sort_key(block: Block) -> tuple[str, int, int, float, float]:
    return (
        block.source_file,
        block.page or block.slide or 0,
        block.reading_order,
        float((block.bbox or {}).get("top", 0)),
        float((block.bbox or {}).get("x0", 0)),
    )
