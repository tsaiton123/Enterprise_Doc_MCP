# Enterprise Document MCP Knowledge Base

A local PDF/PPTX ingestion pipeline and MCP server for searchable,
source-grounded document retrieval. The project focuses on the difficult parts
of enterprise document handling: page geometry, multi-column reading order,
tables, broken PDF math glyphs, and verifiable reconstruction.

## Current Capabilities

| Capability | Implementation | Output |
| --- | --- | --- |
| PDF extraction | `pdfplumber` text, word geometry, tables, page bboxes | `output/extracted_blocks.json` |
| PPTX extraction | `python-pptx` shapes, slide locations, notes | `output/extracted_blocks.json` |
| Structured chunking | Section-aware blocks, bbox and source metadata | `output/cleaned_chunks.json` |
| Local retrieval | Persistent `HashingVectorizer` index with metadata lookup | `output/vector_index/` |
| MCP access | FastMCP tools/resources over stdio or Streamable HTTP | local MCP server |
| Math recovery | Geometry detection, optional OCR/LLM transcription, bbox merge | equation JSON and corrected chunks |
| Extraction audit | Reconstruct chunks at original page positions | reconstructed PDF |

The local retrieval index is intentionally dependency-light and reproducible.
It is not a neural embedding or reranking system yet.

## Repository Policy

Documents and generated results are local artifacts. The repository ignores:

- `.env` and local MCP/client configuration
- `data/raw/*` source documents
- `data/processed/*` generated normalized data
- `output/*` crops, indexes, reports, and reconstructed PDFs
- `server_logs/*` local MCP logs

Placeholder `.gitkeep` files preserve the expected directory layout. Never
commit confidential source documents or API keys.

## 1. Install

Requirements:

- Python 3.11 or newer
- Tesseract only if running the optional OCR math diagnostic
- An OpenAI API key only if running the optional vision-based math
  transcription step

```bash
git clone https://github.com/tsaiton123/Enterprise_Doc_MCP.git
cd Enterprise_Doc_MCP

python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# macOS, optional for equation OCR
brew install tesseract
```

For LLM-assisted equation transcription:

```bash
cp .env.example .env
# Edit .env locally and set OPENAI_API_KEY.
```

## 2. Add Local Documents

Copy PDF or PPTX files into `data/raw/`. The pipeline processes only files
already present there; it does not generate sample documents.

```text
data/raw/
  report.pdf
  strategy_deck.pptx
```

## 3. Run Baseline Extraction And Indexing

```bash
.venv/bin/python pipeline/run_pipeline.py
```

Generated artifacts:

| File | Meaning |
| --- | --- |
| `output/extracted_blocks.json` | Layout-level blocks: paragraphs, headings, equations, captions, tables |
| `output/cleaned_chunks.json` | Retrieval units with page/slide, section, bbox, reading order, and neighbor metadata |
| `output/vector_index/` | Local persistent retrieval index |
| `output/pipeline_report.json` | Block/chunk totals and diagnostics |
| `output/extraction_quality_report.json` | Bbox coverage and suspicious extraction indicators |
| `output/retrieval_results.json` | Example retrieval query results |

A chunk remains traceable to its source location:

```json
{
  "chunk_id": "report_p1_19_equation",
  "text": "b_min = (x_min, y_min, z_min)",
  "content_type": "equation",
  "source_file": "report.pdf",
  "page": 1,
  "bbox": {
    "x0": 382.42,
    "top": 263.59,
    "x1": 492.59,
    "bottom": 280.47
  },
  "metadata": {
    "latex": "b_{\\min} = (x_{\\min}, y_{\\min}, z_{\\min})",
    "extraction_method": "pdfplumber_bbox_merge_with_llm_transcription"
  }
}
```

## 4. Recover Equations When PDF Text Is Broken

This step is optional. Baseline extraction is sufficient for ordinary prose;
use the math workflow when PDF glyph extraction separates scripts, symbols, or
equation fragments into incorrect text boxes.

### The Problem

Some PDFs store a displayed equation as several positioned glyph streams. For
example, `pdfplumber` may extract a base formula and its subscript as separate
lines:

```text
b = (x , y , z )
min min min min
```

The source page looks correct visually, but naive chunking produces duplicate
or corrupted text.

![Math glyph bboxes merged into one equation region](docs/assets/equation_bbox_merge.png)

In the crop above, blue outlines the base equation line, orange outlines the
detached script glyphs, and red outlines the merged region submitted for math
transcription.

### The Implemented Approach

1. `pdfplumber` provides geometry only: word/line boxes and reading order.
2. `pipeline/equation_regions.py` detects math seed lines and nearby
   superscript/subscript fragments, then unions them into one candidate bbox.
3. Optional Tesseract OCR provides a cheap diagnostic transcription.
4. Optional OpenAI vision transcription converts the crop into normalized
   LaTeX and plain text.
5. `pipeline/merge_equations.py` replaces the original equation components
   with one corrected equation block.
6. Lines consumed by the equation, such as `min min min min`, are removed from
   neighboring paragraph blocks before final chunks are written.

### Commands

Use the actual PDF filename from `data/raw/`:

```bash
# Visualize candidate equation bboxes on a copy of the PDF.
.venv/bin/python client/mark_equation_bboxes.py report.pdf

# Optional local OCR diagnostic. This also creates the equation crops.
.venv/bin/python client/ocr_equation_regions.py report.pdf

# Vision transcription. Requires OPENAI_API_KEY in .env.
.venv/bin/python client/llm_equation_regions.py \
  --regions-json output/report_equation_ocr.json \
  --output-json output/report_equation_llm.json \
  --limit 0

# Regenerate final blocks, chunks, and index with merged math.
.venv/bin/python pipeline/run_pipeline.py \
  --equations-json output/report_equation_llm.json
```

Final `extracted_blocks.json` and `cleaned_chunks.json` contain the merged
equation and retained neighboring prose, but not the consumed ghost text
boxes. The intermediate equation JSON intentionally keeps raw component bboxes
for auditability.

### Conservative Handling Of Inline Math

Displayed equations are safe to replace when their merged regions are
well-bounded. Inline equations are more dangerous: a partial inline candidate
can overlap ordinary prose, and replacing it may erase part of a sentence.

The reconstruction step therefore:

- replaces reviewed single-line display equations by default
- skips inline equation overlays unless `--include-inline` is explicitly set
- skips display regions taller than the configured safety threshold
- reports skipped regions for later review

This preserves document integrity while exposing unresolved extraction cases.

## 5. Validate Extraction Through Reconstruction

Reconstruction is a layout audit. It draws cleaned chunks onto blank PDF pages
using their extracted bboxes, so missing headings, mixed columns, overlaps, and
damaged equation extraction are visible.

```bash
# Reconstruct only from cleaned chunks and recorded positions.
.venv/bin/python client/reconstruct_pdf.py report.pdf \
  --output output/reconstructed_report.pdf

# Overlay safe LLM-transcribed display equations on the reconstructed PDF.
.venv/bin/python client/reconstruct_math_pdf.py report.pdf \
  --base-pdf output/reconstructed_report.pdf \
  --equations-json output/report_equation_llm.json \
  --output-pdf output/reconstructed_report_with_llm_math.pdf \
  --report-json output/reconstructed_report_with_llm_math_report.json
```

This is not intended to reproduce font styling perfectly. It tests whether the
extraction pipeline retained content type, reading order, and location.

## 6. Bottlenecks And Mitigations

| Bottleneck | Failure Mode | Current Mitigation | Remaining Work |
| --- | --- | --- | --- |
| Multi-column PDFs | Lines from opposite columns interleave in chunks | Page geometry detects left/right columns and orders each separately | Handle complex three-column layouts and floating figures |
| Displayed math | Subscripts/superscripts appear as detached duplicate text | Candidate bbox union, optional LLM LaTeX, component consumption in final JSON | Improve recognition without an external model |
| Inline math | Candidate bbox overlaps surrounding sentence text | Detect candidates but skip reconstruction replacement by default | Context-aware inline span segmentation |
| Tables | Text extraction loses row relationships | `pdfplumber` table extraction and Markdown preservation | Stitch tables continued across pages |
| Reconstruction | A cleaned text dump can hide location errors | Blank-page bbox reconstruction plus optional math overlays | Automated visual similarity scoring |
| Retrieval quality | Local hashed lexical vectors are limited for paraphrases | Traceable baseline with source citations | Add configurable neural embeddings and reranking |

## 7. Run The MCP Server Locally

Run extraction before starting MCP, because tools read
`output/cleaned_chunks.json` and `output/vector_index/`.

### Local Client: Stdio

For local use, remote hosting is not required. Configure your MCP client to
spawn this server over stdio:

```json
{
  "mcpServers": {
    "enterprise-doc-kb": {
      "command": "/absolute/path/to/Enterprise_Doc_MCP/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/Enterprise_Doc_MCP"
    }
  }
}
```

Restart the client after changing its MCP configuration.

### Local HTTP Development: Streamable HTTP

Use Streamable HTTP locally when developing a remote-client integration:

```bash
MCP_TRANSPORT=http MCP_HOST=127.0.0.1 MCP_PORT=8000 \
  .venv/bin/python -m mcp_server.server
```

The Streamable HTTP MCP endpoint is `http://127.0.0.1:8000/mcp`.

## 8. Deploy To A Public URL With Zeabur

The repository includes a root `Dockerfile` for cloud deployment. Its startup
behavior differs intentionally from local development:

- local ingestion processes only documents manually added to `data/raw/`
- the public container starts with `GENERATE_DEMO_DATA=true`
- if the container has no documents, it generates synthetic report/deck files,
  indexes them, and starts the HTTP MCP server
- no private local document or `.env` file is included in the Docker build
  context, because `.dockerignore` mirrors the sensitive artifact exclusions

This makes a public demonstration usable without publishing personal or
confidential source files.

### Zeabur Deployment Steps

1. In Zeabur, create a project and choose **Deploy New Service** > **GitHub**.
2. Select `tsaiton123/Enterprise_Doc_MCP`.
3. Deploy from branch `main`. Zeabur detects the root `Dockerfile`.
4. Confirm the service exposes its `web` port. The container reads Zeabur's
   injected `PORT` and binds to `0.0.0.0`.
5. Open the service **Domains** tab and add a public Zeabur domain.
6. Use the resulting endpoint with the MCP path appended:

```text
https://<your-service-domain>/mcp
```

The Dockerfile sets `GENERATE_DEMO_DATA=true` by default. No `OPENAI_API_KEY`
is needed in the public demo because equation LLM transcription is a local,
optional enrichment workflow, not a runtime dependency for serving MCP tools.

### Verify The Public MCP Endpoint

After Zeabur reports a successful deployment and a domain is assigned:

```bash
.venv/bin/python client/test_remote.py \
  https://<your-service-domain>/mcp
```

The smoke client lists MCP tools and calls `answer_with_citations` against the
synthetic indexed report. An expected demo question is:

```text
What was APAC revenue growth?
```

Expected grounded content: APAC revenue of `$2.1M` with `12%` growth, cited
from `enterprise_report.pdf`.

### Deploying Real Documents

Do not expose real source documents in the public demo service. For a private
or authenticated deployment, provision documents through protected storage,
turn off synthetic generation with `GENERATE_DEMO_DATA=false`, and add
authentication/TLS policy appropriate for document access before making the
endpoint reachable by clients.

References:

- [Zeabur Dockerfile deployments](https://zeabur.com/docs/en-US/deploy/methods/dockerfile)
- [Zeabur GitHub integration](https://zeabur.com/docs/en-US/deploy/github)
- [FastMCP HTTP deployment](https://gofastmcp.com/v2/deployment/http)

## 9. MCP Tools And Resources

Tools:

| Tool | Purpose |
| --- | --- |
| `search_knowledge_base(query, top_k, source_filter)` | Retrieve ranked chunks |
| `answer_with_citations(query, top_k, source_filter)` | Return grounded snippets with page/slide citations |
| `get_chunk(chunk_id)` | Inspect an individual retrieval unit and bbox |
| `get_chunks_by_page(source_file, page)` | Recover a page in reading order |
| `list_documents()` | List indexed sources and sections |
| `get_document_outline(doc_id)` | Map sections to chunks |
| `get_table(table_id)` | Retrieve a table chunk |

Resources:

```text
resource://documents
resource://documents/{doc_id}/outline
resource://documents/{source_file}/pages/{page}
resource://chunks/{chunk_id}
resource://tables/{table_id}
```

Example requests through an MCP client:

```text
Use enterprise-doc-kb to summarize the technical approach with citations.
Use enterprise-doc-kb to retrieve all chunks on page 3.
Use enterprise-doc-kb to find the table discussing runtime.
```

## 10. Test

With at least one local PDF or PPTX in `data/raw/` and a generated index:

```bash
.venv/bin/python client/test_client.py
.venv/bin/pytest
```

The equation merge regression test specifically verifies that detached
subscript text is consumed by a merged equation while adjacent prose is
preserved.

## Project Structure

```text
data/raw/                  local input PDF and PPTX files, ignored by Git
data/processed/            generated intermediate JSON, ignored by Git
pipeline/                  extraction, chunking, math merging, indexing
mcp_server/                FastMCP tools and resources
client/                    diagnostics, OCR/LLM math passes, reconstruction
deploy/                    public HTTP deployment bootstrap
docs/assets/               non-sensitive README illustrations
tests/                     retrieval, MCP, and equation-merge tests
output/                    generated reports/index/PDF reconstructions, ignored
server_logs/               optional local MCP verification logs, ignored
```
