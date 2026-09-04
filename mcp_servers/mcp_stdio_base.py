# mcp_stdio_base.py
"""
Minimal MCP (Model Context Protocol) stdio server loop.
Shared by all Orion-provided MCP servers (tavily, cloud, rag) so each can run
as its own long-lived subprocess and be launched from mcp_servers.json exactly
like any third-party MCP server.

Protocol: JSON-RPC 2.0 over stdin/stdout, one message per line.
Supports: initialize, notifications/initialized, tools/list, tools/call.
"""
import json
import sys
import traceback
from typing import Any, Callable, Dict, List


def _write(msg: Dict[str, Any]):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _text_result(text: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def run_server(
    server_name: str,
    tools: List[Dict[str, Any]],
    dispatch: Callable[[str, Dict[str, Any]], str],
):
    """
    tools: list of {"name": ..., "description": ..., "inputSchema": {...}}
    dispatch(tool_name, arguments) -> str result text. Raise Exception on error.
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params", {}) or {}

        # Notifications (no id) never get a response.
        if method == "notifications/initialized":
            continue

        if method == "initialize":
            _write({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": server_name, "version": "1.0.0"},
                },
            })
            continue

        if method == "tools/list":
            _write({"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}})
            continue

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {}) or {}
            try:
                result_text = dispatch(tool_name, arguments)
                _write({"jsonrpc": "2.0", "id": req_id, "result": _text_result(str(result_text))})
            except Exception as e:
                _write({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": f"{e}\n{traceback.format_exc(limit=2)}"},
                })
            continue

        # Unknown method
        if req_id is not None:
            _write({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })