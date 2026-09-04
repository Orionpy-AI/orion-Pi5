# tools/__init__.py
"""
Tools package for Orion LLM.
Exports:
- registry: Unified tool registry
- rag_engine: Codebase RAG indexing and retrieval engine
- mcp_manager: Model Context Protocol client manager
"""
from .registry import registry, ToolRegistry
from .rag_engine import rag_engine, CodeRAGEngine
from .mcp_client import mcp_manager, MCPManager
from .code_tools import read_file, write_file, replace_in_file, list_dir, search_code
from .search import tavily_search
from .calculator import calculator
from .dateTime import get_current_datetime
from storage import save_file, list_files, delete_file, cloud_status

__all__ = [
    "registry",
    "ToolRegistry",
    "rag_engine",
    "CodeRAGEngine",
    "mcp_manager",
    "MCPManager",
    "read_file",
    "write_file",
    "replace_in_file",
    "list_dir",
    "search_code",
    "tavily_search",
    "calculator",
    "get_current_datetime",
    "save_file",
    "list_files",
    "delete_file",
    "cloud_status",
]

