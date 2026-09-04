# tools/registry.py
"""
Unified Tool Registry for Orion LLM.
Integrates local built-in tools (Code editing, RAG, Web search, Calculator, DateTime)
and dynamically discovered MCP (Model Context Protocol) tools.
"""
import json
from typing import Dict, Any, List, Callable, Optional

from .calculator import calculator
from .dateTime import get_current_datetime
from .search import tavily_search
from .code_tools import read_file, write_file, replace_in_file, list_dir, search_code
from .rag_engine import rag_engine
from .mcp_client import mcp_manager
from storage import save_file, list_files, delete_file, cloud_status


class ToolRegistry:
    def __init__(self):
        self._local_tools: Dict[str, Dict[str, Any]] = {}
        self._register_builtins()

    def register_tool(
        self,
        name: str,
        func: Callable,
        description: str,
        parameters: Dict[str, Any],
    ):
        """Register a local Python function as a tool."""
        self._local_tools[name] = {
            "name": name,
            "func": func,
            "description": description,
            "parameters": parameters,
            "is_mcp": False,
        }

    def _register_builtins(self):
        # 1. Code modification & reading tools
        self.register_tool(
            name="read_file",
            func=read_file,
            description="Read the contents of a file with optional line numbers (start_line, end_line).",
            parameters={
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the file to read."},
                    "start_line": {"type": "integer", "description": "Starting line number (1-indexed)."},
                    "end_line": {"type": "integer", "description": "Ending line number (inclusive)."},
                },
                "required": ["filepath"],
            },
        )

        self.register_tool(
            name="write_file",
            func=write_file,
            description="Create or completely overwrite a file with the given content.",
            parameters={
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the file to write."},
                    "content": {"type": "string", "description": "Complete new content for the file."},
                },
                "required": ["filepath", "content"],
            },
        )

        self.register_tool(
            name="replace_in_file",
            func=replace_in_file,
            description="Replace an exact target block of code or text in a file with a replacement block. Target must be unique.",
            parameters={
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the file to modify."},
                    "target": {"type": "string", "description": "Exact text/code block to replace."},
                    "replacement": {"type": "string", "description": "New replacement text/code block."},
                },
                "required": ["filepath", "target", "replacement"],
            },
        )

        self.register_tool(
            name="list_dir",
            func=list_dir,
            description="List files and directories in a given folder path.",
            parameters={
                "type": "object",
                "properties": {
                    "dir_path": {"type": "string", "description": "Directory path to list. Defaults to '.' (current dir)."},
                },
                "required": [],
            },
        )

        self.register_tool(
            name="search_code",
            func=search_code,
            description="Search for a text pattern or regex across files in a directory.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Pattern or regex to search for."},
                    "dir_path": {"type": "string", "description": "Directory path to search in."},
                },
                "required": ["pattern"],
            },
        )

        # 2. RAG Tools
        self.register_tool(
            name="rag_index_directory",
            func=lambda dir_path: json.dumps(rag_engine.index_directory(dir_path), indent=2),
            description="Index a directory for semantic/lexical code search and retrieval.",
            parameters={
                "type": "object",
                "properties": {
                    "dir_path": {"type": "string", "description": "Directory path to index for RAG."},
                },
                "required": ["dir_path"],
            },
        )

        self.register_tool(
            name="rag_search_code",
            func=lambda query, top_k=3: json.dumps(rag_engine.query(query, top_k=int(top_k)), indent=2),
            description="Search the indexed codebase using RAG for relevant code chunks and functions.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Code search query or feature description."},
                    "top_k": {"type": "integer", "description": "Number of top results to return."},
                },
                "required": ["query"],
            },
        )

        # 3. Web search & Utilities
        self.register_tool(
            name="tavily_search",
            func=tavily_search,
            description="Search the live web for recent information, documentation, news, or answers.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "max_results": {"type": "integer", "description": "Maximum number of results (default 3)."},
                },
                "required": ["query"],
            },
        )

        self.register_tool(
            name="calculator",
            func=calculator,
            description="Safely evaluate basic mathematical or arithmetic expressions.",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression to evaluate."},
                },
                "required": ["expression"],
            },
        )

        self.register_tool(
            name="get_current_datetime",
            func=lambda: get_current_datetime(),
            description="Get the current date and time.",
            parameters={"type": "object", "properties": {}, "required": []},
        )

        # 4. Cloud storage tools
        self.register_tool(
            name="save_file_to_cloud",
            func=save_file,
            description="Save a local file to persistent cloud or local storage ('local', 'gdrive', or 'onedrive').",
            parameters={
                "type": "object",
                "properties": {
                    "source_path": {"type": "string", "description": "Local path of the file to save."},
                    "target": {"type": "string", "description": "Storage target: 'local', 'gdrive', or 'onedrive' (default 'local')."},
                    "dest_relative_path": {"type": "string", "description": "Optional destination path relative to storage root."},
                },
                "required": ["source_path"],
            },
        )

        self.register_tool(
            name="list_cloud_files",
            func=list_files,
            description="List files stored in cloud or local storage ('local', 'gdrive', or 'onedrive').",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Storage target: 'local', 'gdrive', or 'onedrive' (default 'local')."},
                    "dir_relative_path": {"type": "string", "description": "Subdirectory path relative to storage root (default '')."},
                },
                "required": [],
            },
        )

        self.register_tool(
            name="delete_cloud_file",
            func=delete_file,
            description="Delete a file from cloud or local storage ('local', 'gdrive', or 'onedrive').",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Storage target: 'local', 'gdrive', or 'onedrive' (default 'local')."},
                    "relative_path": {"type": "string", "description": "Relative path of file to delete from storage root."},
                },
                "required": ["relative_path"],
            },
        )

        self.register_tool(
            name="cloud_storage_status",
            func=cloud_status,
            description="Check status and availability of persistent storage backends (local storage path, Google Drive, and OneDrive mounts/rclone).",
            parameters={"type": "object", "properties": {}, "required": []},
        )


    def get_all_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return schema list for prompt and API function calling."""
        tools = []
        # Add local tools
        for t in self._local_tools.values():
            tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                }
            })

        # Add MCP tools
        mcp_tools = mcp_manager.get_all_tools()
        for mt in mcp_tools:
            name = f"mcp_{mt['_mcp_server']}_{mt['name']}"
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"[MCP: {mt['_mcp_server']}] {mt.get('description', '')}",
                    "parameters": mt.get("inputSchema", {"type": "object", "properties": {}}),
                },
                "_mcp_server": mt["_mcp_server"],
                "_mcp_tool_name": mt["name"],
            })

        return tools

    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Execute local or MCP tool by name."""
        # 1. Check local tools
        if name in self._local_tools:
            try:
                func = self._local_tools[name]["func"]
                return str(func(**arguments))
            except TypeError as te:
                return f"Error executing tool '{name}': invalid arguments {arguments} ({te})"
            except Exception as e:
                return f"Error executing tool '{name}': {e}"

        # 2. Check MCP tools
        if name.startswith("mcp_"):
            parts = name.split("_", 2)
            if len(parts) >= 3:
                server_name = parts[1]
                mcp_tool_name = parts[2]
                return mcp_manager.call_tool(server_name, mcp_tool_name, arguments)

        # 3. Direct MCP tool match
        for s_name, server in mcp_manager.servers.items():
            for t in server.tools:
                if t["name"] == name:
                    return server.call_tool(name, arguments)

        return f"Error: Tool '{name}' not found."


registry = ToolRegistry()
