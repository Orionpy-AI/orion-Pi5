# mcp_client.py
"""
Model Context Protocol (MCP) stdio client.
Supports launching MCP servers over JSON-RPC 2.0 stdio, discovery of tools,
and tool execution.
"""
import json
import os
import subprocess
import sys
import threading
from typing import Dict, List, Any, Optional


class MCPStdioServer:
    """Represents a connected stdio-based MCP server process."""
    def __init__(self, name: str, command: str, args: List[str] = None, env: Dict[str, str] = None, cwd: str = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = {**os.environ, **(env or {})}
        self.cwd = cwd
        self.process: Optional[subprocess.Popen] = None
        self.tools: List[Dict[str, Any]] = []
        self._req_id = 0
        self._lock = threading.Lock()
        self._is_ready = False
        self.last_error: Optional[str] = None

    def start(self) -> bool:
        command_bin = self.command
        if self.command in ("python3", "python") and sys.executable:
            command_bin = sys.executable
        cmd = [command_bin] + self.args
        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=self.env,
                cwd=self.cwd,
            )
        except FileNotFoundError:
            self.last_error = f"Command not found: '{self.command}'. Is it installed and on PATH?"
            self.tools = []
            return False
        except Exception as e:
            self.last_error = f"Failed to launch process: {e}"
            self.tools = []
            return False

        ok = self._initialize()
        if not ok:
            # Give the process a moment then check if it already died, and
            # surface stderr so failures aren't silent.
            if self.process.poll() is not None:
                try:
                    stderr_out = self.process.stderr.read()
                except Exception:
                    stderr_out = ""
                self.last_error = (
                    f"Server process exited with code {self.process.returncode}. "
                    f"Stderr: {stderr_out.strip()[:500]}"
                )
            elif not self.last_error:
                self.last_error = "Server did not respond to 'initialize' handshake (timed out or sent malformed JSON-RPC)."
        return ok

    def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not self.process or self.process.poll() is not None:
            return None

        with self._lock:
            self._req_id += 1
            request_id = self._req_id
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
            try:
                line = json.dumps(payload) + "\n"
                self.process.stdin.write(line)
                self.process.stdin.flush()

                # Read response line
                resp_line = self.process.stdout.readline()
                if not resp_line:
                    return None
                return json.loads(resp_line)
            except Exception:
                return None

    def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        if not self.process or self.process.poll() is not None:
            return
        with self._lock:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            }
            try:
                line = json.dumps(payload) + "\n"
                self.process.stdin.write(line)
                self.process.stdin.flush()
            except Exception:
                pass

    def _initialize(self) -> bool:
        init_params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "clientInfo": {
                "name": "Orion-LLM-MCP-Client",
                "version": "1.0.0",
            },
        }
        res = self._send_request("initialize", init_params)
        if not res:
            self.last_error = "No response from server during 'initialize' (process may have crashed or stdout is not valid JSON-RPC)."
            return False
        if "error" in res:
            self.last_error = f"Initialize error: {res['error']}"
            return False

        self._send_notification("notifications/initialized")
        self._is_ready = True
        self.fetch_tools()
        return True

    def fetch_tools(self) -> List[Dict[str, Any]]:
        """Fetch list of tools exported by this MCP server."""
        if not self._is_ready:
            return []
        res = self._send_request("tools/list")
        if res and "result" in res and "tools" in res["result"]:
            self.tools = res["result"]["tools"]
            return self.tools
        return []

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a specific tool on this MCP server."""
        if not self._is_ready:
            return f"Error: MCP server '{self.name}' is not running."

        res = self._send_request("tools/call", {"name": tool_name, "arguments": arguments})
        if not res:
            return f"Error: No response from MCP server '{self.name}'."
        if "error" in res:
            return f"MCP Error ({res['error'].get('code')}): {res['error'].get('message')}"

        result = res.get("result", {})
        content = result.get("content", [])
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif isinstance(item, str):
                    texts.append(item)
            return "\n".join(texts) if texts else json.dumps(result, indent=2)
        return str(result)

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
        self._is_ready = False


class MCPManager:
    """Manages all registered MCP servers."""
    def __init__(self, config_file: str = "mcp_servers.json"):
        self.config_file = config_file
        self.servers: Dict[str, MCPStdioServer] = {}
        # name -> error string, for servers that were configured but failed to start
        self.failed_servers: Dict[str, str] = {}
        self.load_error: Optional[str] = None

    def load_and_start_servers(self):
        """Read mcp_servers.json and start configured servers."""
        self.failed_servers = {}
        self.load_error = None

        if not os.path.exists(self.config_file):
            self.load_error = f"Config file '{self.config_file}' not found."
            return

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            self.load_error = f"Could not parse '{self.config_file}': {e}"
            return

        mcp_servers = config.get("mcpServers", {})
        if not mcp_servers:
            self.load_error = (
                f"'{self.config_file}' has no servers configured "
                f"(mcpServers is empty). Add an entry to enable MCP tools."
            )
            return

        for name, cfg in mcp_servers.items():
            cmd = cfg.get("command")
            args = cfg.get("args", [])
            env = cfg.get("env", {})
            cwd = cfg.get("cwd") or os.path.dirname(os.path.abspath(self.config_file))

            if not cmd:
                self.failed_servers[name] = "Missing 'command' field in config."
                continue

            server = MCPStdioServer(name=name, command=cmd, args=args, env=env, cwd=cwd)
            if server.start():
                self.servers[name] = server
            else:
                self.failed_servers[name] = server.last_error or "Unknown startup failure."

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Collect all tools from all running MCP servers."""
        tools = []
        for server_name, server in self.servers.items():
            for tool in server.tools:
                tool_copy = dict(tool)
                tool_copy["_mcp_server"] = server_name
                tools.append(tool_copy)
        return tools

    def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        server = self.servers.get(server_name)
        if not server:
            return f"Error: MCP Server '{server_name}' not found."
        return server.call_tool(tool_name, arguments)

    def shutdown(self):
        for server in self.servers.values():
            server.stop()
        self.servers.clear()


mcp_manager = MCPManager()