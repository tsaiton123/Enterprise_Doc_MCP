from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pipeline.embed import INDEX_DIR, LocalVectorIndex, citation_for, load_index
from pipeline.run_pipeline import RAW_DIR, build_index


CHUNKS_PATH = Path("output/cleaned_chunks.json")
SUPPORTED_SUFFIXES = {".pdf", ".pptx"}

# In-memory caches, invalidated when the backing file's mtime changes. This
# avoids rebuilding the vectorizer matrix on every query (the old behaviour)
# while still picking up a fresh index after an ingest, even across processes.
_index_cache: tuple[float, LocalVectorIndex] | None = None
_chunks_cache: tuple[float, list[dict[str, Any]]] | None = None


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


def _get_index() -> LocalVectorIndex:
    global _index_cache
    signature = _mtime(INDEX_DIR / "chunks.json")
    if _index_cache is None or _index_cache[0] != signature:
        _index_cache = (signature, load_index())
    return _index_cache[1]


def _load_chunks() -> list[dict[str, Any]]:
    global _chunks_cache
    signature = _mtime(CHUNKS_PATH)
    if _chunks_cache is None or _chunks_cache[0] != signature:
        _chunks_cache = (signature, json.loads(CHUNKS_PATH.read_text(encoding="utf-8")))
    return _chunks_cache[1]


def search_knowledge_base(query: str, top_k: int = 5, source_filter: str | None = None) -> list[dict[str, Any]]:
    return _get_index().search(query=query, top_k=top_k, source_filter=source_filter)


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


def ingest_document(path: str) -> dict[str, Any]:
    """Copy a local .pdf/.pptx into the corpus and rebuild the searchable index.

    The file must already be reachable on the machine running this server
    (client-side ingestion): the agent supplies a filesystem path, the document
    never transits as upload bytes.
    """
    source = Path(path).expanduser()
    if not source.is_file():
        return {"status": "error", "error": f"File not found: {source}"}
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return {
            "status": "error",
            "error": f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_SUFFIXES)}.",
        }

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    destination = RAW_DIR / source.name
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)

    diagnostics = build_index(run_sample_queries=False)
    return {
        "status": "ingested",
        "file": source.name,
        "documents": diagnostics["documents"],
        "chunks_generated": diagnostics["chunks_generated"],
        "tables_detected": diagnostics["tables_detected"],
    }


def reindex() -> dict[str, Any]:
    """Rebuild the index from every document currently in data/raw."""
    try:
        diagnostics = build_index(run_sample_queries=False)
    except FileNotFoundError as error:
        return {"status": "error", "error": str(error)}
    return {
        "status": "reindexed",
        "documents": diagnostics["documents"],
        "chunks_generated": diagnostics["chunks_generated"],
        "tables_detected": diagnostics["tables_detected"],
    }


def _synthesize(query: str, results: list[dict[str, Any]]) -> str:
    snippets = []
    for result in results[:3]:
        locator = citation_for(result)
        text = result["text"].strip()
        if len(text) > 320:
            text = text[:317].rstrip() + "..."
        snippets.append(f"{text}\nSource: {locator}")
    return "\n\n".join(snippets)
