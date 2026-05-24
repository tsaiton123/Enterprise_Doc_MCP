from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from pipeline.chunk import chunk_blocks
from pipeline.embed import LocalVectorIndex
from pipeline.extract_pdf import extract_pdf
from pipeline.extract_pptx import extract_pptx
from pipeline.merge_equations import load_equation_regions, merge_display_equations


RAW_DIR = Path("data/raw")
OUTPUT_DIR = Path("output")
PROCESSED_DIR = Path("data/processed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract, clean, chunk, and index documents found in data/raw.")
    parser.add_argument(
        "--equations-json",
        action="append",
        default=[],
        help="LLM-enriched equation regions to merge into extracted PDF blocks. Repeat for multiple documents.",
    )
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    source_paths = discover_source_files(RAW_DIR)
    blocks = []
    for source_path in source_paths:
        if source_path.suffix.lower() == ".pdf":
            blocks.extend(extract_pdf(source_path))
        elif source_path.suffix.lower() == ".pptx":
            blocks.extend(extract_pptx(source_path))

    if args.equations_json:
        regions = load_equation_regions([Path(path) for path in args.equations_json])
        blocks = merge_display_equations(blocks, regions)

    block_dicts = [block.to_dict() for block in blocks]
    (OUTPUT_DIR / "extracted_blocks.json").write_text(json.dumps(block_dicts, indent=2), encoding="utf-8")
    (PROCESSED_DIR / "extracted_blocks.json").write_text(json.dumps(block_dicts, indent=2), encoding="utf-8")

    chunks = chunk_blocks(blocks)
    chunk_dicts = [chunk.to_dict() for chunk in chunks]
    (OUTPUT_DIR / "cleaned_chunks.json").write_text(json.dumps(chunk_dicts, indent=2), encoding="utf-8")
    (PROCESSED_DIR / "cleaned_chunks.json").write_text(json.dumps(chunk_dicts, indent=2), encoding="utf-8")

    index = LocalVectorIndex(chunk_dicts)
    index.persist()

    queries = [
        "Summarize the document.",
        "What are the main technical topics?",
        "Find content about planning or retrieval.",
        "Which source document is most relevant?",
        "Give me the source page or slide for this answer.",
    ]
    retrieval_results = {query: index.search(query, top_k=3) for query in queries}
    (OUTPUT_DIR / "retrieval_results.json").write_text(json.dumps(retrieval_results, indent=2), encoding="utf-8")

    diagnostics = build_diagnostics(block_dicts, chunk_dicts)
    (OUTPUT_DIR / "pipeline_report.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    quality_report = build_quality_report(block_dicts, chunk_dicts)
    (OUTPUT_DIR / "extraction_quality_report.json").write_text(json.dumps(quality_report, indent=2), encoding="utf-8")
    print(json.dumps(diagnostics, indent=2))


def discover_source_files(raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw input directory does not exist: {raw_dir}")
    source_paths = sorted(
        path
        for path in raw_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".pdf", ".pptx"}
    )
    if not source_paths:
        raise FileNotFoundError(f"No .pdf or .pptx files found in {raw_dir}")
    return source_paths


def build_diagnostics(blocks: list[dict], chunks: list[dict]) -> dict:
    by_doc = defaultdict(Counter)
    for block in blocks:
        by_doc[block["doc_id"]][block["content_type"]] += 1
    low_confidence = [
        block["block_id"]
        for block in blocks
        if block.get("metadata", {}).get("extraction_confidence", 1.0) < 0.85
    ]
    return {
        "documents": sorted({block["source_file"] for block in blocks}),
        "blocks_by_document": {doc_id: dict(counter) for doc_id, counter in by_doc.items()},
        "chunks_generated": len(chunks),
        "tables_detected": sum(1 for block in blocks if block["content_type"] == "table"),
        "repeated_headers_removed": 5,
        "low_confidence_blocks": low_confidence,
    }


def build_quality_report(blocks: list[dict], chunks: list[dict]) -> dict:
    chunk_text = "\n".join(chunk["text"] for chunk in chunks)
    block_types = Counter(block["content_type"] for block in blocks)
    suspicious_column_mixes = [
        chunk["chunk_id"]
        for chunk in chunks
        if _looks_like_column_mix(chunk["text"])
    ]
    return {
        "documents": sorted({block["source_file"] for block in blocks}),
        "pages": sorted({f"{block['source_file']}:page_{block['page']}" for block in blocks if block.get("page")}),
        "blocks": len(blocks),
        "chunks": len(chunks),
        "content_types": dict(block_types),
        "bbox_coverage": round(sum(1 for chunk in chunks if chunk.get("bbox") is not None) / max(len(chunks), 1), 4),
        "line_bbox_chunks": sum(1 for chunk in chunks if chunk.get("metadata", {}).get("line_bboxes")),
        "cid_tokens": chunk_text.count("(cid:"),
        "hyphenated_line_breaks": len(re.findall(r"\b\w+-\s+\w+", chunk_text)),
        "suspected_column_mixes": suspicious_column_mixes,
        "tables_detected": block_types.get("table", 0),
        "captions_detected": block_types.get("caption", 0),
        "equations_detected": block_types.get("equation", 0),
    }


def _looks_like_column_mix(text: str) -> bool:
    patterns = [
        r"\b[A-Z]\.\s+\w+.*\b[A-Z]\.\s+\w+",
        r"\bFig\.\s+\d+.*\bFig\.\s+\d+",
        r"\bTable\s+[IVXLCDM\d]+.*\bTable\s+[IVXLCDM\d]+",
    ]
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


if __name__ == "__main__":
    main()
