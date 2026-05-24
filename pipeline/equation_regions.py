from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pdfplumber

from pipeline.extract_pdf import _line_bboxes


STRONG_MATH_CHARS = r"[=∈⊂∀σ∆ϵ{}\\+−≤≥√∑∫]"
PROSE_HINTS = {
    "and",
    "the",
    "with",
    "between",
    "environment",
    "environments",
    "workspace",
    "boundary",
    "obstacle",
    "obstacles",
    "excluding",
    "runtime",
    "success",
    "path",
    "length",
    "nodes",
    "waypoints",
}
SCRIPT_TOKENS = {
    "min",
    "max",
    "free",
    "obs",
    "start",
    "goal",
    "s",
    "g",
    "i",
    "j",
    "k",
    "t",
    "x",
    "y",
    "z",
    "0",
    "1",
    "2",
    "3",
}
VARIABLE_TOKENS = {"b", "c", "f", "g", "h", "i", "j", "k", "n", "p", "r", "s", "t", "x", "y", "z", "O", "R", "T", "X"}


def detect_equation_regions(pdf_path: Path, padding: float = 3.0) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            lines = _line_bboxes(page)
            candidates = [_candidate_from_line(line) for line in lines]
            candidates = [candidate for candidate in candidates if candidate["is_seed"] or candidate["is_script"]]
            components = _connected_components(candidates)
            display_regions: list[dict[str, Any]] = []
            for component_index, component in enumerate(components, start=1):
                if not any(item["is_seed"] for item in component):
                    continue
                bbox = _union_bbox([item["bbox"] for item in component])
                if not bbox or not _valid_region(bbox):
                    continue
                padded = _pad_bbox(bbox, padding, float(page.width), float(page.height))
                display_regions.append(
                    {
                        "region_id": f"{pdf_path.stem}_p{page_number}_eq_{component_index:03d}",
                        "source_file": pdf_path.name,
                        "page": page_number,
                        "bbox": padded,
                        "raw_text": " ".join(item["text"] for item in sorted(component, key=lambda item: (item["bbox"]["top"], item["bbox"]["x0"]))),
                        "component_lines": [
                            {
                                "text": item["text"],
                                "bbox": item["bbox"],
                                "role": "seed" if item["is_seed"] else "script",
                            }
                            for item in sorted(component, key=lambda item: (item["bbox"]["top"], item["bbox"]["x0"]))
                        ],
                        "region_type": "display_equation",
                        "extraction_method": "pdfplumber_geometry_component_merge",
                    }
                )
            regions.extend(display_regions)
            inline_regions = _detect_inline_regions(pdf_path.name, page, page_number, padding, display_regions)
            regions.extend(inline_regions)
    return _dedupe_regions(regions)


def write_equation_regions_json(pdf_path: Path, output_path: Path) -> list[dict[str, Any]]:
    regions = detect_equation_regions(pdf_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(regions, indent=2), encoding="utf-8")
    return regions


def _candidate_from_line(line: dict[str, object]) -> dict[str, Any]:
    text = str(line["text"]).strip()
    bbox = line["bbox"]
    return {
        "text": text,
        "bbox": bbox,
        "is_seed": _is_math_seed(text),
        "is_script": _is_script_fragment(text),
    }


def _detect_inline_regions(source_file: str, page, page_number: int, padding: float, display_regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    words = _word_lines(page)
    regions: list[dict[str, Any]] = []
    counter = 1
    for line_words in words:
        spans = _inline_spans_for_line(line_words)
        for span in spans:
            bbox = _union_bbox([word["bbox"] for word in span])
            if not bbox:
                continue
            if not _valid_inline_region(bbox):
                continue
            if any(_overlaps_display(bbox, region["bbox"]) for region in display_regions):
                continue
            raw_text = " ".join(word["text"] for word in span)
            padded = _pad_bbox(bbox, padding, float(page.width), float(page.height))
            regions.append(
                {
                    "region_id": f"{Path(source_file).stem}_p{page_number}_inline_eq_{counter:03d}",
                    "source_file": source_file,
                    "page": page_number,
                    "bbox": padded,
                    "raw_text": raw_text,
                    "component_lines": [
                        {
                            "text": word["text"],
                            "bbox": word["bbox"],
                            "role": "inline_word",
                        }
                        for word in span
                    ],
                    "region_type": "inline_equation",
                    "extraction_method": "pdfplumber_inline_math_span",
                }
            )
            counter += 1
    return regions


def _word_lines(page) -> list[list[dict[str, Any]]]:
    words = page.extract_words(x_tolerance=1, y_tolerance=3, keep_blank_chars=False)
    rows: list[list[dict[str, Any]]] = []
    for word in words:
        normalized = {
            "text": str(word["text"]),
            "bbox": {
                "x0": round(float(word["x0"]), 2),
                "top": round(float(word["top"]), 2),
                "x1": round(float(word["x1"]), 2),
                "bottom": round(float(word["bottom"]), 2),
            },
        }
        for row in rows:
            if abs(row[0]["bbox"]["top"] - normalized["bbox"]["top"]) <= 3:
                row.append(normalized)
                break
        else:
            rows.append([normalized])
    return [sorted(row, key=lambda item: item["bbox"]["x0"]) for row in sorted(rows, key=lambda row: row[0]["bbox"]["top"])]


def _inline_spans_for_line(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    spans: list[list[dict[str, Any]]] = []
    seed_indices = [index for index, word in enumerate(words) if _is_inline_seed(word["text"])]
    consumed: set[int] = set()
    for seed_index in seed_indices:
        if seed_index in consumed:
            continue
        start = seed_index
        end = seed_index
        while start > 0 and _can_attach_inline(words[start - 1]["text"], left_side=True):
            start -= 1
        while end + 1 < len(words) and _can_attach_inline(words[end + 1]["text"], left_side=False):
            end += 1
        span = words[start : end + 1]
        if _span_is_useful(span):
            spans.append(span)
            consumed.update(range(start, end + 1))
    return _merge_inline_spans(spans)


def _is_inline_seed(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.search(STRONG_MATH_CHARS, stripped):
        return True
    if "(cid:" in stripped:
        return True
    if re.match(r"^[A-Za-z]\w*,?\w*\s*=", stripped):
        return True
    return False


def _can_attach_inline(text: str, left_side: bool) -> bool:
    stripped = text.strip(".,;:")
    if not stripped:
        return False
    if _is_inline_seed(stripped):
        return True
    if stripped in VARIABLE_TOKENS:
        return True
    if re.match(r"^[A-Za-z][0-9](?:,[A-Za-z0-9]+)?$", stripped):
        return True
    if re.match(r"^[A-Z][A-Za-z]?,[A-Za-z0-9]+$", stripped):
        return True
    if re.match(r"^[0-9.]+$", stripped):
        return True
    if stripped.lower() in SCRIPT_TOKENS:
        return True
    return False


def _span_is_useful(span: list[dict[str, Any]]) -> bool:
    text = " ".join(word["text"] for word in span)
    if len(span) < 2 and not re.search(STRONG_MATH_CHARS, text):
        return False
    alpha_tokens = re.findall(r"[A-Za-z]+", text)
    prose_count = sum(1 for token in alpha_tokens if token.lower() in PROSE_HINTS)
    if prose_count > 1:
        return False
    return bool(re.search(STRONG_MATH_CHARS, text) or "(cid:" in text)


def _overlaps_display(inline_bbox: dict[str, float], display_bbox: dict[str, float]) -> bool:
    x0 = max(inline_bbox["x0"], display_bbox["x0"])
    top = max(inline_bbox["top"], display_bbox["top"])
    x1 = min(inline_bbox["x1"], display_bbox["x1"])
    bottom = min(inline_bbox["bottom"], display_bbox["bottom"])
    intersection = max(0.0, x1 - x0) * max(0.0, bottom - top)
    inline_area = max(1.0, (inline_bbox["x1"] - inline_bbox["x0"]) * (inline_bbox["bottom"] - inline_bbox["top"]))
    return intersection / inline_area > 0.35


def _merge_inline_spans(spans: list[list[dict[str, Any]]]) -> list[list[dict[str, Any]]]:
    if not spans:
        return []
    merged: list[list[dict[str, Any]]] = []
    for span in spans:
        if not merged:
            merged.append(span)
            continue
        previous = merged[-1]
        previous_bbox = _union_bbox([word["bbox"] for word in previous])
        span_bbox = _union_bbox([word["bbox"] for word in span])
        if previous_bbox and span_bbox and _should_merge(previous_bbox, span_bbox):
            merged[-1] = [*previous, *span]
        else:
            merged.append(span)
    return merged


def _is_math_seed(text: str) -> bool:
    stripped = text.strip()
    tokens = re.findall(r"[A-Za-z]+", stripped)
    prose_count = sum(1 for token in tokens if token.lower() in PROSE_HINTS)
    alpha_count = len(tokens)
    strong_math_chars = len(re.findall(STRONG_MATH_CHARS, stripped))
    density = strong_math_chars / max(len(stripped), 1)
    compact = len(stripped.split()) <= 14 and len(stripped) <= 120
    prose_like = prose_count > 0 or alpha_count > 8
    if compact and strong_math_chars >= 1 and not prose_like and (density >= 0.025 or "=" in stripped):
        return True
    if re.search(r"\b[a-zA-Z]\s*=", stripped) and compact and not prose_like:
        return True
    return False


def _is_script_fragment(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > 50:
        return False
    tokens = re.findall(r"[A-Za-z0-9]+", stripped)
    if not tokens:
        return False
    script_count = sum(1 for token in tokens if token.lower() in SCRIPT_TOKENS)
    return script_count == len(tokens) and len(tokens) <= 8


def _connected_components(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    graph: dict[int, set[int]] = defaultdict(set)
    for left_index, left in enumerate(items):
        for right_index in range(left_index + 1, len(items)):
            right = items[right_index]
            if _should_merge(left["bbox"], right["bbox"]):
                graph[left_index].add(right_index)
                graph[right_index].add(left_index)

    visited: set[int] = set()
    components: list[list[dict[str, Any]]] = []
    for index in range(len(items)):
        if index in visited:
            continue
        stack = [index]
        component_indices: list[int] = []
        visited.add(index)
        while stack:
            current = stack.pop()
            component_indices.append(current)
            for neighbor in graph[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append([items[item_index] for item_index in component_indices])
    return components


def _should_merge(a: dict[str, float], b: dict[str, float]) -> bool:
    vertical_gap = max(0.0, max(a["top"], b["top"]) - min(a["bottom"], b["bottom"]))
    horizontal_gap = max(0.0, max(a["x0"], b["x0"]) - min(a["x1"], b["x1"]))
    vertical_overlap = max(0.0, min(a["bottom"], b["bottom"]) - max(a["top"], b["top"]))
    horizontal_overlap = max(0.0, min(a["x1"], b["x1"]) - max(a["x0"], b["x0"]))
    min_width = max(min(a["x1"] - a["x0"], b["x1"] - b["x0"]), 1.0)

    near_subscript = vertical_gap <= 8 and horizontal_overlap / min_width >= 0.15
    adjacent_math = vertical_overlap > 0 and horizontal_gap <= 14
    stacked_centered = vertical_gap <= 12 and abs(_center_x(a) - _center_x(b)) <= max(a["x1"] - a["x0"], b["x1"] - b["x0"], 20)
    return near_subscript or adjacent_math or stacked_centered


def _center_x(box: dict[str, float]) -> float:
    return (box["x0"] + box["x1"]) / 2


def _union_bbox(boxes: list[dict[str, float]]) -> dict[str, float] | None:
    if not boxes:
        return None
    return {
        "x0": round(min(box["x0"] for box in boxes), 2),
        "top": round(min(box["top"] for box in boxes), 2),
        "x1": round(max(box["x1"] for box in boxes), 2),
        "bottom": round(max(box["bottom"] for box in boxes), 2),
    }


def _pad_bbox(bbox: dict[str, float], padding: float, page_width: float, page_height: float) -> dict[str, float]:
    return {
        "x0": round(max(0.0, bbox["x0"] - padding), 2),
        "top": round(max(0.0, bbox["top"] - padding), 2),
        "x1": round(min(page_width, bbox["x1"] + padding), 2),
        "bottom": round(min(page_height, bbox["bottom"] + padding), 2),
    }


def _valid_region(bbox: dict[str, float]) -> bool:
    width = bbox["x1"] - bbox["x0"]
    height = bbox["bottom"] - bbox["top"]
    return width >= 12 and height >= 5 and width <= 360 and height <= 80


def _valid_inline_region(bbox: dict[str, float]) -> bool:
    width = bbox["x1"] - bbox["x0"]
    height = bbox["bottom"] - bbox["top"]
    return width >= 8 and height >= 5 and width <= 260 and height <= 32


def _dedupe_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    for region in sorted(regions, key=lambda item: (item["page"], item["bbox"]["top"], item["bbox"]["x0"])):
        if any(region["page"] == existing["page"] and _iou(region["bbox"], existing["bbox"]) > 0.8 for existing in deduped):
            continue
        deduped.append(region)
    return deduped


def _iou(a: dict[str, float], b: dict[str, float]) -> float:
    x0 = max(a["x0"], b["x0"])
    top = max(a["top"], b["top"])
    x1 = min(a["x1"], b["x1"])
    bottom = min(a["bottom"], b["bottom"])
    intersection = max(0.0, x1 - x0) * max(0.0, bottom - top)
    area_a = max(0.0, a["x1"] - a["x0"]) * max(0.0, a["bottom"] - a["top"])
    area_b = max(0.0, b["x1"] - b["x0"]) * max(0.0, b["bottom"] - b["top"])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0
