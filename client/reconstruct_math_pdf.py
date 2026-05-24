from __future__ import annotations

import argparse
import io
import json
import os
import re
from pathlib import Path
from typing import Any

import fitz

MPLCONFIGDIR = Path("output/.matplotlib").resolve()
MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt


RAW_DIR = Path("data/raw")


def reconstruct_math_pdf(
    source_file: str,
    equations_json: Path,
    output_pdf: Path,
    report_json: Path,
    base_pdf: Path | None = None,
    include_inline: bool = False,
    max_display_height: float = 24.0,
) -> dict[str, Any]:
    source_path = RAW_DIR / source_file
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    input_pdf = base_pdf or source_path
    if not input_pdf.exists():
        raise FileNotFoundError(f"Base PDF not found: {input_pdf}")

    equations = json.loads(equations_json.read_text(encoding="utf-8"))
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    doc = fitz.open(input_pdf)

    for equation in equations:
        region_type = equation.get("region_type", "display_equation")
        bbox = equation["bbox"]
        height = float(bbox["bottom"]) - float(bbox["top"])
        if region_type == "inline_equation" and not include_inline:
            skipped.append({"region_id": equation["region_id"], "reason": "inline_region_requires_review"})
            continue
        if region_type == "display_equation" and height > max_display_height:
            skipped.append(
                {
                    "region_id": equation["region_id"],
                    "reason": "display_region_overlaps_multiple_lines",
                    "bbox_height": round(height, 2),
                }
            )
            continue
        latex = equation.get("llm_latex")
        if not latex:
            skipped.append({"region_id": equation["region_id"], "reason": "no_latex"})
            continue
        page = doc[int(equation["page"]) - 1]
        rect = fitz.Rect(bbox["x0"], bbox["top"], bbox["x1"], bbox["bottom"])
        try:
            image_bytes = _render_formula(latex)
        except Exception as exc:
            skipped.append({"region_id": equation["region_id"], "reason": f"render_error: {exc}"})
            continue

        page.draw_rect(rect, fill=(1, 1, 1), color=(1, 1, 1), overlay=True)
        insert_rect = _fit_rendered_formula(rect, latex, region_type)
        page.insert_image(insert_rect, stream=image_bytes, keep_proportion=True, overlay=True)
        applied.append(
            {
                "region_id": equation["region_id"],
                "region_type": region_type,
                "page": equation["page"],
                "bbox": bbox,
                "latex": latex,
            }
        )

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_pdf)
    doc.close()
    report = {
        "source_file": source_file,
        "base_pdf": str(input_pdf),
        "equations_json": str(equations_json),
        "output_pdf": str(output_pdf),
        "include_inline": include_inline,
        "max_display_height": max_display_height,
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "applied": applied,
        "skipped": skipped,
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _render_formula(latex: str) -> bytes:
    normalized = _normalize_mathtext(latex)
    figure = plt.figure(figsize=(0.01, 0.01), dpi=300)
    figure.patch.set_alpha(0)
    figure.text(0, 0, f"${normalized}$", fontsize=13, color="black")
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", transparent=True, bbox_inches="tight", pad_inches=0.015, dpi=300)
    plt.close(figure)
    return buffer.getvalue()


def _normalize_mathtext(latex: str) -> str:
    value = latex.strip().rstrip(".")
    value = re.sub(r"\\text\{([^}]*)\}", r"\\mathrm{\1}", value)
    value = value.replace(r"\;", r"\,")
    value = value.replace(r"\quad", r"\qquad")
    return value


def _fit_rendered_formula(rect: fitz.Rect, latex: str, region_type: str) -> fitz.Rect:
    # Keep the placement fixed at the extracted bbox while allowing compact
    # inline equations a little room to remain readable.
    if region_type == "inline_equation":
        minimum_height = 12
        height = max(rect.height, minimum_height)
        return fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + height)
    return rect


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct a PDF by replacing detected math regions with LLM LaTeX renderings.")
    parser.add_argument("source_file")
    parser.add_argument("--equations-json", default=None)
    parser.add_argument("--base-pdf", default=None, help="PDF to receive overlays, such as a chunk-based reconstruction.")
    parser.add_argument("--output-pdf", default=None)
    parser.add_argument("--report-json", default=None)
    parser.add_argument("--include-inline", action="store_true", help="Replace inline equation candidates after reviewing their bounding boxes.")
    parser.add_argument("--max-display-height", type=float, default=24.0, help="Skip display regions taller than this point size.")
    args = parser.parse_args()

    stem = Path(args.source_file).stem
    equations_json = Path(args.equations_json or f"output/{stem}_equation_llm.json")
    output_pdf = Path(args.output_pdf or f"output/{stem}_math_reconstructed.pdf")
    report_json = Path(args.report_json or f"output/{stem}_math_reconstruction_report.json")
    report = reconstruct_math_pdf(
        args.source_file,
        equations_json,
        output_pdf,
        report_json,
        base_pdf=Path(args.base_pdf) if args.base_pdf else None,
        include_inline=args.include_inline,
        max_display_height=args.max_display_height,
    )
    print(f"applied={report['applied_count']} skipped={report['skipped_count']}")
    print(output_pdf)
    print(report_json)


if __name__ == "__main__":
    main()
