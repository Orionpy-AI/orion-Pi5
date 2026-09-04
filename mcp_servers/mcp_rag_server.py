#!/usr/bin/env python3
# mcp_rag_server.py
"""
MCP server exposing the codebase RAG engine (index + BM25 search).
Launch via mcp_servers.json:
  "command": "python3", "args": ["mcp_servers/mcp_rag_server.py"]

Note: this process has its own in-memory index, separate from any index built
via the built-in `/rag` command in the main Orion process (indexes are not
shared across processes). Index it once per session with rag_index_directory.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root

from rag_engine import rag_engine
from mcp_stdio_base import run_server

TOOLS = [
    {
        "name": "rag_index_directory",
        "description": "Index a directory for lexical (BM25) code search and retrieval.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dir_path": {"type": "string", "description": "Directory path to index."},
            },
            "required": ["dir_path"],
        },
    },
    {
        "name": "rag_search_code",
        "description": "Search the indexed codebase for relevant code chunks and functions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Code search query or feature description."},
                "top_k": {"type": "integer", "description": "Number of top results to return (default 3)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "rag_status",
        "description": "Get current RAG index status (indexed path, file count, chunk count).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def dispatch(tool_name: str, arguments: dict) -> str:
    if tool_name == "rag_index_directory":
        return json.dumps(rag_engine.index_directory(arguments["dir_path"]), indent=2)
    if tool_name == "rag_search_code":
        top_k = int(arguments.get("top_k", 3))
        return json.dumps(rag_engine.query(arguments["query"], top_k=top_k), indent=2)
    if tool_name == "rag_status":
        return json.dumps(rag_engine.get_status(), indent=2)
    raise ValueError(f"Unknown tool: {tool_name}")


if __name__ == "__main__":
    run_server("orion-rag", TOOLS, dispatch)