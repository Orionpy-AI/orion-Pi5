#!/usr/bin/env python3
# mcp_tavily_server.py
"""
MCP server exposing live web search via Tavily.
Launch via mcp_servers.json:
  "command": "python3", "args": ["mcp_servers/mcp_tavily_server.py"]
Requires TAVILY_API_KEY in the environment or a .env file in the project root.
"""
import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_proj_dir = os.path.dirname(_this_dir)
if _proj_dir not in sys.path:
    sys.path.insert(0, _proj_dir)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from tools.search import tavily_search
from mcp_stdio_base import run_server

TOOLS = [
    {
        "name": "web_search",
        "description": "Search the live web for current information, news, documentation, or answers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "max_results": {"type": "integer", "description": "Maximum number of results (default 3)."},
            },
            "required": ["query"],
        },
    }
]


def dispatch(tool_name: str, arguments: dict) -> str:
    if tool_name == "web_search":
        query = arguments.get("query", "")
        max_results = int(arguments.get("max_results", 3))
        return tavily_search(query, max_results=max_results)
    raise ValueError(f"Unknown tool: {tool_name}")


if __name__ == "__main__":
    run_server("orion-tavily-search", TOOLS, dispatch)
