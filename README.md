# Enterprise Document MCP Knowledge Base

This project is a reproducible PDF/PPTX-to-knowledge-base demo with metadata-rich chunks, table-aware retrieval, citation metadata, diagnostics, and MCP tools/resources.

## What It Builds

- Source PDF/PPTX documents in `data/raw/`
- Normalized extracted blocks in `output/extracted_blocks.json`
- Cleaned, metadata-rich chunks in `output/cleaned_chunks.json`
- Persistent local vector index in `output/vector_index/`
- Retrieval demo output in `output/retrieval_results.json`
- MCP server exposing search, source lookup, outlines, and table access
- Verifiable client logs in `server_logs/`

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
# Add one or more local PDF/PPTX files under data/raw/
.venv/bin/python pipeline/run_pipeline.py
.venv/bin/python client/test_client.py
.venv/bin/pytest
```

Input documents and generated outputs are deliberately ignored by Git. This
keeps source documents, embeddings, reconstructions, and API credentials out
of the repository.

## Equation Extraction And Reconstruction

After an initial pipeline run, equation bboxes can be marked, transcribed with
an OpenAI vision model, merged into final blocks/chunks, and reconstructed:

```bash
.venv/bin/python client/mark_equation_bboxes.py report.pdf
.venv/bin/python client/ocr_equation_regions.py report.pdf
.venv/bin/python client/llm_equation_regions.py --regions-json output/report_equation_ocr.json --limit 0
.venv/bin/python pipeline/run_pipeline.py --equations-json output/report_equation_llm.json
.venv/bin/python client/reconstruct_pdf.py report.pdf --output output/reconstructed_report.pdf
.venv/bin/python client/reconstruct_math_pdf.py report.pdf \
  --base-pdf output/reconstructed_report.pdf \
  --equations-json output/report_equation_llm.json \
  --output-pdf output/reconstructed_report_with_llm_math.pdf
```

Set `OPENAI_API_KEY` in a local `.env` file before the LLM step. It is not
committed.

## MCP Server

Stdio transport:

```bash
.venv/bin/python -m mcp_server.server
```

Streamable HTTP transport:

```bash
MCP_TRANSPORT=http MCP_HOST=127.0.0.1 MCP_PORT=8000 .venv/bin/python -m mcp_server.server
```

## Exposed Tools

- `search_knowledge_base(query, top_k=5, source_filter=None)`
- `answer_with_citations(query, top_k=5, source_filter=None)`
- `get_chunk(chunk_id)`
- `list_documents()`
- `get_document_outline(doc_id)`
- `get_table(table_id)`

## Example Queries

- Summarize the document.
- What are the main technical topics?
- Find content about planning or retrieval.
- Which source document is most relevant?
- Give me the source page or slide for this answer.

## Architecture

```text
data/raw/                  input PDF and PPTX files
pipeline/                  extraction, cleaning, chunking, math merging, embedding
mcp_server/                MCP tools and resources
client/                    reproducible test client and logs
tests/                     retrieval and MCP-style tool tests
output/                    generated normalized blocks, chunks, index, reconstructions
server_logs/               generated connection and tool-call logs
```
