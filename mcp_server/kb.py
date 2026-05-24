from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.embed import citation_for, load_index


CHUNKS_PATH = Path("output/cleaned_chunks.json")


def _load_chunks() -> list[dict[str, Any]]:
    return json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))


def search_knowledge_base(query: str, top_k: int = 5, source_filter: str | None = None) -> list[dict[str, Any]]:
    return load_index().search(query=query, top_k=top_k, source_filter=source_filter)


def answer_with_citations(query: str, top_k: int = 5, source_filter: str | None = None) -> dict[str, Any]:
    results = search_knowledge_base(query, top_k=top_k, source_filter=source_filter)
    if not results:
        return {"answer": "No grounded answer found.", "citations": [], "results": []}
    leading = results[0]
    answer = _synthesize(query, results)
    return {
        "answer": answer,
        "primary_source": citation_for(leading),
        "citations": [citation_for(result) for result in results],
        "results": results,
    }


def get_chunk(chunk_id: str) -> dict[str, Any] | None:
    return next((chunk for chunk in _load_chunks() if chunk["chunk_id"] == chunk_id), None)


def get_chunks_by_page(source_file: str, page: int) -> list[dict[str, Any]]:
    chunks = [
        chunk
        for chunk in _load_chunks()
        if chunk.get("source_file") == source_file and chunk.get("page") == page
    ]
    return sorted(chunks, key=lambda chunk: (chunk.get("reading_order", 0), chunk.get("bbox", {}).get("top", 0), chunk["chunk_id"]))


def list_documents() -> list[dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    for chunk in _load_chunks():
        doc = docs.setdefault(
            chunk["doc_id"],
            {"doc_id": chunk["doc_id"], "source_file": chunk["source_file"], "source_type": chunk["metadata"]["source_type"], "sections": set()},
        )
        if chunk.get("section"):
            doc["sections"].add(chunk["section"])
    return [{**doc, "sections": sorted(doc["sections"])} for doc in docs.values()]


def get_document_outline(doc_id: str) -> dict[str, Any]:
    chunks = [chunk for chunk in _load_chunks() if chunk["doc_id"] == doc_id]
    outline: dict[str, list[str]] = {}
    for chunk in chunks:
        section = chunk.get("section") or "Unsectioned"
        outline.setdefault(section, []).append(chunk["chunk_id"])
    return {"doc_id": doc_id, "outline": outline}


def get_table(table_id: str) -> dict[str, Any] | None:
    for chunk in _load_chunks():
        if chunk.get("table_id") == table_id and chunk["content_type"] == "table":
            return chunk
    return None


def _synthesize(query: str, results: list[dict[str, Any]]) -> str:
    snippets = []
    for result in results[:3]:
        locator = citation_for(result)
        text = result["text"].strip()
        if len(text) > 320:
            text = text[:317].rstrip() + "..."
        snippets.append(f"{text}\nSource: {locator}")
    return "\n\n".join(snippets)
