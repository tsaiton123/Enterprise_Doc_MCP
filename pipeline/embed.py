from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.metrics.pairwise import cosine_similarity


INDEX_DIR = Path("output/vector_index")


class LocalVectorIndex:
    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks = chunks
        self.vectorizer = HashingVectorizer(n_features=2048, alternate_sign=False, norm="l2")
        self.matrix = self.vectorizer.transform([chunk["text"] for chunk in chunks])

    def search(self, query: str, top_k: int = 5, source_filter: str | None = None) -> list[dict[str, Any]]:
        candidates = self.chunks
        indices = list(range(len(candidates)))
        if source_filter:
            lowered = source_filter.lower()
            indices = [idx for idx, chunk in enumerate(candidates) if lowered in chunk["source_file"].lower()]
        if not indices:
            return []
        query_vector = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vector, self.matrix[indices]).ravel()
        ranked = sorted(zip(indices, scores, strict=False), key=lambda item: item[1], reverse=True)[:top_k]
        results = []
        for idx, score in ranked:
            chunk = dict(self.chunks[idx])
            chunk["score"] = round(float(score), 4)
            chunk["citation"] = citation_for(chunk)
            results.append(chunk)
        return results

    def persist(self, path: Path = INDEX_DIR) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "chunks.json").write_text(json.dumps(self.chunks, indent=2), encoding="utf-8")
        (path / "index_manifest.json").write_text(
            json.dumps(
                {
                    "backend": "sklearn.HashingVectorizer",
                    "n_features": 2048,
                    "chunk_count": len(self.chunks),
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def citation_for(chunk: dict[str, Any]) -> str:
    locator = f"page {chunk['page']}" if chunk.get("page") else f"slide {chunk.get('slide')}"
    table = f", table {chunk['table_id']}" if chunk.get("table_id") else ""
    return f"{chunk['source_file']}, {locator}{table}"


def load_index(path: Path = INDEX_DIR) -> LocalVectorIndex:
    chunks = json.loads((path / "chunks.json").read_text(encoding="utf-8"))
    return LocalVectorIndex(chunks)
