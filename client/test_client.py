from __future__ import annotations

import json
from pathlib import Path

from mcp_server import kb


LOG_DIR = Path("server_logs")


def main() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    documents = kb.list_documents()
    (LOG_DIR / "successful_connection.log").write_text(
        "Connected to local MCP knowledge-base module.\n"
        f"Documents: {json.dumps(documents, indent=2)}\n",
        encoding="utf-8",
    )

    query = "What does the report say about motion planning?"
    result = kb.answer_with_citations(query)
    (LOG_DIR / "tool_call_search.log").write_text(
        f"tool=answer_with_citations\nquery={query}\nresponse={json.dumps(result, indent=2)}\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
