from __future__ import annotations

from pipeline.merge_equations import merge_display_equations
from pipeline.models import Block


def test_merged_equation_consumes_script_line_but_retains_adjacent_prose() -> None:
    base = {
        "doc_id": "report",
        "source_file": "report.pdf",
        "source_type": "pdf",
        "page": 1,
        "section": "Technical Approach",
    }
    blocks = [
        Block(
            **base,
            block_id="eq_base",
            content_type="equation",
            text="b = (x , y , z )",
            bbox={"x0": 100, "top": 10, "x1": 200, "bottom": 20},
            reading_order=1,
            metadata={"line_bboxes": [{"text": "b = (x , y , z )", "bbox": {"x0": 100, "top": 10, "x1": 200, "bottom": 20}}]},
        ),
        Block(
            **base,
            block_id="paragraph",
            content_type="paragraph",
            text="min min min min and upper corner",
            bbox={"x0": 80, "top": 14, "x1": 200, "bottom": 40},
            reading_order=2,
            metadata={
                "line_bboxes": [
                    {"text": "min min min min", "bbox": {"x0": 110, "top": 14, "x1": 190, "bottom": 21}},
                    {"text": "and upper corner", "bbox": {"x0": 80, "top": 30, "x1": 160, "bottom": 40}},
                ]
            },
        ),
    ]
    regions = [
        {
            "region_id": "formula_1",
            "source_file": "report.pdf",
            "page": 1,
            "region_type": "display_equation",
            "bbox": {"x0": 97, "top": 7, "x1": 203, "bottom": 24},
            "component_lines": [
                {"text": "b = (x , y , z )", "bbox": {"x0": 100, "top": 10, "x1": 200, "bottom": 20}},
                {"text": "min min min min", "bbox": {"x0": 110, "top": 14, "x1": 190, "bottom": 21}},
            ],
            "llm_latex": r"b_{\min} = (x_{\min}, y_{\min}, z_{\min})",
            "llm_plain_text": "b_min = (x_min, y_min, z_min)",
            "llm_confidence": 0.98,
        }
    ]

    merged = merge_display_equations(blocks, regions)

    assert [block.text for block in merged] == ["b_min = (x_min, y_min, z_min)", "and upper corner"]
    equation = merged[0]
    assert equation.metadata["latex"] == r"b_{\min} = (x_{\min}, y_{\min}, z_{\min})"
    assert equation.metadata["consumed_component_count"] == 2
    assert "consumed_component_lines" not in equation.metadata
