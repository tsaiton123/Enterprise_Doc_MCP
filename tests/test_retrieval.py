from __future__ import annotations

from pathlib import Path

from mcp_server import kb


def test_pipeline_outputs_exist() -> None:
    assert Path("output/extracted_blocks.json").exists()
    assert Path("output/cleaned_chunks.json").exists()
    assert Path("output/vector_index/chunks.json").exists()


def test_retrieval_returns_cited_chunks() -> None:
    answer = kb.answer_with_citations("motion planning", top_k=3)
    assert answer["results"]
    assert answer["citations"]
    assert all(result["source_file"].endswith((".pdf", ".pptx")) for result in answer["results"])


def test_chunks_include_bboxes() -> None:
    results = kb.search_knowledge_base("motion planning", top_k=5)
    assert results
    assert all(result["bbox"] is not None for result in results)


def test_no_sample_specific_apac_answer() -> None:
    answer = kb.answer_with_citations("What was APAC revenue growth?", top_k=3)
    assert "APAC revenue growth was 12%" not in answer["answer"]
