from __future__ import annotations

import argparse
import json
from pathlib import Path

import fitz

from pipeline.equation_regions import detect_equation_regions


RAW_DIR = Path("data/raw")


def mark_equation_bboxes(source_file: str, output_pdf: Path, output_json: Path) -> list[dict]:
    source_path = RAW_DIR / source_file
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    regions = detect_equation_regions(source_path)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(regions, indent=2), encoding="utf-8")

    doc = fitz.open(source_path)
    for region in regions:
        page = doc[int(region["page"]) - 1]
        bbox = region["bbox"]
        rect = fitz.Rect(bbox["x0"], bbox["top"], bbox["x1"], bbox["bottom"])
        color = (0, 0.2, 1) if region.get("region_type") == "inline_equation" else (1, 0, 0)
        page.draw_rect(rect, color=color, width=1.4)
        label_point = fitz.Point(rect.x0, max(8, rect.y0 - 3))
        page.insert_text(
            label_point,
            region["region_id"],
            fontsize=6,
            color=color,
        )
    doc.save(output_pdf)
    doc.close()
    return regions


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark detected equation bboxes on a copy of a source PDF.")
    parser.add_argument("source_file")
    parser.add_argument("--output-pdf", default=None)
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args()

    stem = Path(args.source_file).stem
    output_pdf = Path(args.output_pdf or f"output/{stem}_equation_bboxes.pdf")
    output_json = Path(args.output_json or f"output/{stem}_equation_bboxes.json")
    regions = mark_equation_bboxes(args.source_file, output_pdf, output_json)
    print(f"regions={len(regions)}")
    print(output_pdf)
    print(output_json)


if __name__ == "__main__":
    main()
