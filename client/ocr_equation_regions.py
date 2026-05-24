from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import fitz
from PIL import Image


RAW_DIR = Path("data/raw")
DEFAULT_CROP_DIR = Path("output/equation_crops")


def ocr_equation_regions(source_file: str, regions_json: Path, crop_dir: Path, output_json: Path, scale: float = 4.0) -> list[dict[str, Any]]:
    source_path = RAW_DIR / source_file
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    regions = json.loads(regions_json.read_text(encoding="utf-8"))
    crop_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(source_path)
    enriched = []
    for region in regions:
        crop_path = crop_dir / f"{region['region_id']}.png"
        _save_region_crop(doc, region, crop_path, scale)
        ocr_text = _run_tesseract(crop_path)
        enriched.append(
            {
                **region,
                "crop_path": str(crop_path),
                "ocr_text": ocr_text,
                "ocr_engine": "tesseract",
                "ocr_status": "complete" if ocr_text else "empty",
            }
        )
    doc.close()

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(enriched, indent=2), encoding="utf-8")
    return enriched


def _save_region_crop(doc, region: dict[str, Any], crop_path: Path, scale: float) -> None:
    page = doc[int(region["page"]) - 1]
    bbox = region["bbox"]
    rect = fitz.Rect(bbox["x0"], bbox["top"], bbox["x1"], bbox["bottom"])
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=rect, alpha=False)
    pixmap.save(crop_path)
    _postprocess_crop(crop_path)


def _postprocess_crop(crop_path: Path) -> None:
    image = Image.open(crop_path).convert("L")
    # Simple thresholding improves Tesseract on small PDF math crops.
    image = image.point(lambda pixel: 0 if pixel < 190 else 255)
    image.save(crop_path)


def _run_tesseract(crop_path: Path) -> str:
    cmd = [
        "tesseract",
        str(crop_path),
        "stdout",
        "--psm",
        "7",
        "--oem",
        "1",
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return " ".join(result.stdout.split())


def main() -> None:
    parser = argparse.ArgumentParser(description="Crop detected equation regions and run local Tesseract OCR.")
    parser.add_argument("source_file")
    parser.add_argument("--regions-json", default=None)
    parser.add_argument("--crop-dir", default=str(DEFAULT_CROP_DIR))
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--scale", type=float, default=4.0)
    args = parser.parse_args()

    stem = Path(args.source_file).stem
    regions_json = Path(args.regions_json or f"output/{stem}_equation_bboxes.json")
    output_json = Path(args.output_json or f"output/{stem}_equation_ocr.json")
    enriched = ocr_equation_regions(args.source_file, regions_json, Path(args.crop_dir), output_json, args.scale)
    print(f"ocr_regions={len(enriched)}")
    print(output_json)


if __name__ == "__main__":
    main()
