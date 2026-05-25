from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from mcp_server.server import mcp
from pipeline.generate_docs import generate_pdf, generate_pptx


RAW_DIR = Path("data/raw")


def _enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _source_files() -> list[Path]:
    return sorted(path for path in RAW_DIR.glob("*") if path.suffix.lower() in {".pdf", ".pptx"})


def prepare_index() -> None:
    if not _source_files():
        if not _enabled("GENERATE_DEMO_DATA"):
            raise RuntimeError("No source documents found. Supply data/raw files or set GENERATE_DEMO_DATA=true.")
        generate_pdf()
        generate_pptx()
    subprocess.run([sys.executable, "-m", "pipeline.run_pipeline"], check=True)


def main() -> None:
    prepare_index()
    host = os.getenv("MCP_HOST", os.getenv("HOST", "0.0.0.0"))
    port = int(os.getenv("PORT", os.getenv("MCP_PORT", "8080")))
    mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()
