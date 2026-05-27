from __future__ import annotations

import os

from fastmcp import FastMCP

from mcp_server import kb


mcp = FastMCP("enterprise-doc-kb")


@mcp.tool
def search_knowledge_base(query: str, top_k: int = 5, source_filter: str | None = None) -> list[dict]:
    """Search metadata-rich document chunks with optional source-file filtering."""
    return kb.search_knowledge_base(query, top_k, source_filter)


@mcp.tool
def answer_with_citations(query: str, top_k: int = 5, source_filter: str | None = None) -> dict:
    """Return a grounded answer with source citations."""
    return kb.answer_with_citations(query, top_k, source_filter)


@mcp.tool
def get_chunk(chunk_id: str) -> dict | None:
    """Fetch one chunk by id."""
    return kb.get_chunk(chunk_id)


@mcp.tool
def get_chunks_by_page(source_file: str, page: int) -> list[dict]:
    """Fetch chunks from one source page in reading order."""
    return kb.get_chunks_by_page(source_file, page)


@mcp.tool
def list_documents() -> list[dict]:
    """List indexed documents and discovered sections."""
    return kb.list_documents()


@mcp.tool
def get_document_outline(doc_id: str) -> dict:
    """Return a document outline mapped to chunk ids."""
    return kb.get_document_outline(doc_id)


@mcp.tool
def get_table(table_id: str) -> dict | None:
    """Fetch one extracted Markdown table by table id."""
    return kb.get_table(table_id)


@mcp.tool
def ingest_document(path: str) -> dict:
    """Ingest a local .pdf/.pptx file by path and rebuild the searchable index.

    The file must be reachable on the machine running this server; supply a
    filesystem path, not upload bytes. Returns ingestion status and counts.
    """
    return kb.ingest_document(path)


@mcp.tool
def reindex() -> dict:
    """Rebuild the index from every document currently in data/raw."""
    return kb.reindex()


@mcp.resource("resource://documents")
def documents_resource() -> list[dict]:
    return kb.list_documents()


@mcp.resource("resource://documents/{doc_id}/outline")
def document_outline_resource(doc_id: str) -> dict:
    return kb.get_document_outline(doc_id)


@mcp.resource("resource://chunks/{chunk_id}")
def chunk_resource(chunk_id: str) -> dict | None:
    return kb.get_chunk(chunk_id)


@mcp.resource("resource://documents/{source_file}/pages/{page}")
def page_chunks_resource(source_file: str, page: int) -> list[dict]:
    return kb.get_chunks_by_page(source_file, page)


@mcp.resource("resource://tables/{table_id}")
def table_resource(table_id: str) -> dict | None:
    return kb.get_table(table_id)


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        host = os.getenv("MCP_HOST", os.getenv("HOST", "127.0.0.1"))
        port = int(os.getenv("PORT", os.getenv("MCP_PORT", "8000")))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run()
