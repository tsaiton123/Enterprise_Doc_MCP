from __future__ import annotations

from pathlib import Path

from mcp_server import kb


def test_list_documents_tool_shape() -> None:
    expected_sources = {
        path.name
        for path in Path("data/raw").iterdir()
        if path.is_file() and path.suffix.lower() in {".pdf", ".pptx"}
    }
    documents = kb.list_documents()
    assert {document["source_file"] for document in documents} == expected_sources


def test_answer_with_citations_uses_indexed_source() -> None:
    result = kb.answer_with_citations("motion planning", top_k=3)
    assert result["citations"]
    assert "report.pdf" in result["primary_source"]
    assert result["results"][0]["bbox"] is not None


def test_get_chunks_by_page() -> None:
    chunks = kb.get_chunks_by_page("report.pdf", 1)
    assert chunks
    assert all(chunk["source_file"] == "report.pdf" for chunk in chunks)
    assert all(chunk["page"] == 1 for chunk in chunks)
