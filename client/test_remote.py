from __future__ import annotations

import argparse
import asyncio
import json

from fastmcp import Client


async def verify_remote(endpoint: str, query: str) -> None:
    async with Client(endpoint) as client:
        tools = await client.list_tools()
        response = await client.call_tool("answer_with_citations", {"query": query, "top_k": 3})
    tool_names = [tool.name for tool in tools]
    print(f"endpoint={endpoint}")
    print(f"tools={tool_names}")
    print(json.dumps(response.data, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a remotely deployed Streamable HTTP MCP endpoint.")
    parser.add_argument("endpoint", help="Full MCP endpoint URL, for example https://service.example/mcp")
    parser.add_argument("--query", default="What was APAC revenue growth?")
    args = parser.parse_args()
    asyncio.run(verify_remote(args.endpoint, args.query))


if __name__ == "__main__":
    main()
