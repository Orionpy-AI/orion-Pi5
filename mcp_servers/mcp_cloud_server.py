#!/usr/bin/env python3
# mcp_cloud_server.py
"""
MCP server exposing local/Google Drive/OneDrive storage management.
Launch via mcp_servers.json:
  "command": "python3", "args": ["mcp_servers/mcp_cloud_server.py"]
Reuses storage.py from the project root (same backend the built-in
/cloud, /save commands use).
"""
import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_proj_dir = os.path.dirname(_this_dir)
if _proj_dir not in sys.path:
    sys.path.insert(0, _proj_dir)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from storage import save_file, list_files, delete_file, cloud_status
from mcp_stdio_base import run_server

TOOLS = [
    {
        "name": "cloud_status",
        "description": "Check status and free space of local storage, Google Drive, and OneDrive mounts.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "save_file",
        "description": "Save/copy a local file into persistent storage ('local', 'gdrive', or 'onedrive').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_path": {"type": "string", "description": "Local path of the file to save."},
                "target": {"type": "string", "description": "Storage target: 'local', 'gdrive', or 'onedrive' (default 'local')."},
                "dest_relative_path": {"type": "string", "description": "Optional destination path relative to storage root."},
            },
            "required": ["source_path"],
        },
    },
    {
        "name": "list_files",
        "description": "List files stored in a storage target ('local', 'gdrive', or 'onedrive').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Storage target: 'local', 'gdrive', or 'onedrive' (default 'local')."},
                "dir_relative_path": {"type": "string", "description": "Subdirectory relative to storage root (default '')."},
            },
            "required": [],
        },
    },
    {
        "name": "delete_file",
        "description": "Delete a file from a storage target ('local', 'gdrive', or 'onedrive').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Storage target: 'local', 'gdrive', or 'onedrive' (default 'local')."},
                "relative_path": {"type": "string", "description": "Relative path of the file to delete."},
            },
            "required": ["relative_path"],
        },
    },
]


def dispatch(tool_name: str, arguments: dict) -> str:
    if tool_name == "cloud_status":
        return cloud_status()
    if tool_name == "save_file":
        return save_file(
            source_path=arguments["source_path"],
            target=arguments.get("target", "local"),
            dest_relative_path=arguments.get("dest_relative_path"),
        )
    if tool_name == "list_files":
        return list_files(
            target=arguments.get("target", "local"),
            dir_relative_path=arguments.get("dir_relative_path", ""),
        )
    if tool_name == "delete_file":
        return delete_file(
            target=arguments.get("target", "local"),
            relative_path=arguments["relative_path"],
        )
    raise ValueError(f"Unknown tool: {tool_name}")


if __name__ == "__main__":
    run_server("orion-cloud-management", TOOLS, dispatch)