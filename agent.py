# agent.py
"""
Orion Agent Engine.
Coordinates multi-turn reasoning, tool execution (Local, RAG, MCP), and code editing.
Supports both native JSON tool-calls and ReAct pattern fallback for edge LLMs.
"""
import json
import os
import re
import time
from typing import Dict, Any, List, Optional, Callable

import requests

from tools import registry, rag_engine, mcp_manager, read_file, save_file, cloud_status


class OrionAgent:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model_name: str = "Qwen2.5-0.5B-Instruct",
        max_iterations: int = 6,
        timeout: int = 120,
    ):
        self.base_url = base_url
        self.model_name = model_name
        self.max_iterations = max_iterations
        self.timeout = timeout
        self.active_file: Optional[str] = None

    def build_system_prompt(self, query: str = "", file_content: str = "") -> str:
        """Construct system prompt with tool definitions, active file, and RAG context."""
        tools_def = registry.get_all_tool_definitions()
        tools_summary = []
        for t in tools_def:
            fn = t["function"]
            tools_summary.append(
                f"- {fn['name']}: {fn['description']} (Parameters: {json.dumps(fn['parameters'].get('properties', {}))})"
            )

        rag_context = ""
        if rag_engine.indexed_path and query:
            rag_context = rag_engine.format_context_for_prompt(query, top_k=3)

        file_focus_context = ""
        if self.active_file:
            file_focus_context = f"\n### Focused Active File: `{self.active_file}`"
            if file_content:
                file_focus_context += f"\n```\n{file_content}\n```"

        prompt = f"""You are ORION, an expert AI software engineer and terminal assistant running locally.
You have access to tools for modifying files, reading code, searching codebases via RAG, executing MCP tools, web searching, and calculations.

### Available Tools:
{chr(10).join(tools_summary)}

### Code Modification Guidelines:
- To modify code, invoke `replace_in_file` with the exact target text and the new replacement text.
- To create or rewrite a file completely, invoke `write_file`.
- To read or inspect files, invoke `read_file`.
- To save files to persistent local, Google Drive, or OneDrive storage, use `save_file_to_cloud`.

### Tool Calling Format:
If you need to execute a tool, output ONLY the following JSON block:
```json
{{
  "tool": "tool_name",
  "arguments": {{
    "param_name": "value"
  }}
}}
```
When you receive the tool observation, explain the result or code changes to the user.

{rag_context}
{file_focus_context}
"""
        return prompt.strip()

    def _parse_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract tool calls from JSON blocks, ReAct actions, or XML tags."""
        # 1. Check for ```json { "tool": ... } ``` or ``` { "tool": ... }
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if "tool" in data and "arguments" in data:
                    return {"name": data["tool"], "arguments": data.get("arguments", {})}
                if "name" in data and "arguments" in data:
                    return {"name": data["name"], "arguments": data.get("arguments", {})}
            except Exception:
                pass

        # 2. Check for raw JSON {"tool": ..., "arguments": ...}
        raw_json_match = re.search(r'\{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"arguments"\s*:\s*(\{[\s\S]*?\})\s*\}', text)
        if raw_json_match:
            try:
                name = raw_json_match.group(1)
                args = json.loads(raw_json_match.group(2))
                return {"name": name, "arguments": args}
            except Exception:
                pass

        # 3. Check for ReAct "Action: tool_name\nAction Input: {...}"
        react_match = re.search(r"Action:\s*([a-zA-Z0-9_\-]+)\s*\nAction Input:\s*(\{[\s\S]*?\}|[^\n]+)", text)
        if react_match:
            name = react_match.group(1).strip()
            raw_input = react_match.group(2).strip()
            try:
                args = json.loads(raw_input)
            except Exception:
                args = {"query": raw_input} if "search" in name else {"input": raw_input}
            return {"name": name, "arguments": args}

        # 4. Check for <tool_call> tags
        tag_match = re.search(r"<tool_call>\s*(\{[\s\S]*?\})\s*</tool_call>", text)
        if tag_match:
            try:
                data = json.loads(tag_match.group(1))
                name = data.get("name") or data.get("tool")
                args = data.get("arguments", {})
                if name:
                    return {"name": name, "arguments": args}
            except Exception:
                pass

        return None

    def run_turn(
        self,
        history: List[Dict[str, str]],
        user_message: str,
        on_status_update: Optional[Callable[[str], None]] = None,
        on_tool_start: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_tool_finish: Optional[Callable[[str, str], None]] = None,
    ) -> str:
        """Execute one complete multi-turn reasoning and tool invocation turn."""
        edit_file_content = ""
        prompt_instruction = user_message

        # 1. Handle `/edit <filename> [instructions]`
        if user_message.startswith("/edit"):
            parts = user_message.split(maxsplit=2)
            if len(parts) == 1:
                return "Usage: `/edit <filename>` to focus a file, or `/edit <filename> <instructions>` to edit code directly."
            
            filename = parts[1]
            self.active_file = filename

            if len(parts) == 2:
                # Just focus file
                if os.path.exists(filename):
                    content = read_file(filename, 1, 15)
                    return f"Active file set to: [bold yellow]{filename}[/bold yellow].\n{content}\n\n[dim]To modify it, ask what to change or use: `/edit {filename} <your instruction>`[/dim]"
                else:
                    return f"Active file set to: [bold yellow]{filename}[/bold yellow] (new file). Give instructions to write content."

            # Has specific instruction: `/edit <filename> <instruction>`
            instruction = parts[2]
            if os.path.exists(filename):
                with open(filename, "r", encoding="utf-8", errors="replace") as f:
                    edit_file_content = f.read()

            prompt_instruction = (
                f"Please edit the file `{filename}` according to this instruction: {instruction}\n"
                f"Current file content of `{filename}`:\n```\n{edit_file_content}\n```\n"
                f"Use `replace_in_file` or `write_file` tool to apply the change."
            )

        # 2. Handle RAG indexing `/rag [path]` or `/index [path]`
        elif user_message.startswith("/rag") or user_message.startswith("/index"):
            parts = user_message.split(maxsplit=1)
            target_path = parts[1].strip() if len(parts) > 1 else "."
            if on_status_update:
                on_status_update(f"Indexing directory '{target_path}' for RAG...")
            res = rag_engine.index_directory(target_path)
            if res.get("success"):
                return f"Successfully indexed [bold green]{res['files_indexed']}[/bold green] files ({res['chunks_created']} chunks) from `{res['path']}` into RAG engine."
            else:
                return f"RAG indexing failed: {res.get('error')}"

        # 3. Handle tool listing `/tools`
        elif user_message.strip() in ("/tools", "/tool"):
            tools = registry.get_all_tool_definitions()
            lines = [f"Registered Tools ({len(tools)} available):"]
            for t in tools:
                fn = t["function"]
                prefix = "🛠️ [bold cyan]MCP[/bold cyan]" if "_mcp_server" in t else "⚡ [bold green]Local[/bold green]"
                lines.append(f"{prefix} **{fn['name']}**: {fn['description']}")
            return "\n".join(lines)

        # 4. Handle MCP server listing `/mcp`
        elif user_message.strip() in ("/mcp", "/servers"):
            servers = mcp_manager.servers
            failed = getattr(mcp_manager, "failed_servers", {})
            load_error = getattr(mcp_manager, "load_error", None)
            lines = []

            if servers:
                lines.append(f"Active MCP Servers ({len(servers)}):")
                for name, s in servers.items():
                    lines.append(f"- ✅ **{name}**: {len(s.tools)} tools loaded")
            else:
                lines.append("No external MCP servers are currently active.")

            if failed:
                lines.append("")
                lines.append(f"Failed to start ({len(failed)}):")
                for name, err in failed.items():
                    lines.append(f"- ❌ **{name}**: {err}")

            if not servers and not failed and load_error:
                lines.append("")
                lines.append(f"[dim]{load_error}[/dim]")
                lines.append(
                    "\nExample entry for `mcp_servers.json`:\n"
                    "```json\n"
                    "{\n"
                    '  "mcpServers": {\n'
                    '    "filesystem": {\n'
                    '      "command": "npx",\n'
                    '      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/pi/projects"]\n'
                    "    }\n"
                    "  }\n"
                    "}\n"
                    "```\n"
                    "Then restart Orion. Use `/mcp` again afterward to confirm it connected."
                )

            return "\n".join(lines)

        # 4b. Handle help menu `/help`
        elif user_message.strip() in ("/help", "/?", "help"):
            tools = registry.get_all_tool_definitions()
            local_count = sum(1 for t in tools if "_mcp_server" not in t)
            mcp_count = len(tools) - local_count
            return (
                "[bold]ORION Command Reference[/bold]\n\n"
                "[bold cyan]/help[/bold cyan]              Show this help menu\n"
                "[bold cyan]/edit <file>[/bold cyan]       Focus a file for editing (add instructions to edit directly)\n"
                "[bold cyan]/rag <path>[/bold cyan]        Index a directory for codebase search (alias: /index)\n"
                "[bold cyan]/tools[/bold cyan]             List all registered tools (local + MCP)\n"
                "[bold cyan]/mcp[/bold cyan]                Show MCP server connection status (alias: /servers)\n"
                "[bold cyan]/cloud[/bold cyan]              Show storage backend status (alias: /storage)\n"
                "[bold cyan]/save <file> [target][/bold cyan]  Save a file to local/gdrive/onedrive\n"
                "[bold cyan]/clear[/bold cyan]              Clear the screen and redraw the banner\n"
                "[bold cyan]exit[/bold cyan] / [bold cyan]quit[/bold cyan]        Quit Orion\n\n"
                f"[dim]{local_count} local tools, {mcp_count} MCP tools currently registered. "
                f"Anything not matching a command above (e.g. `/search ...`) is sent to the model "
                f"as a chat message, not run as a command — there is no built-in `/search` command; "
                f"just ask in plain English and the model can call the `tavily_search` tool itself.[/dim]"
            )

        # 5. Handle Cloud Storage status `/cloud`
        elif user_message.strip() in ("/cloud", "/storage"):
            return cloud_status()

        # 6. Handle `/save <filepath> [local|gdrive|onedrive]`
        elif user_message.startswith("/save"):
            parts = user_message.split()
            if len(parts) < 2:
                return "Usage: `/save <filepath> [local|gdrive|onedrive]` (e.g. `/save README.md onedrive`)"
            filepath = parts[1]
            target = parts[2] if len(parts) >= 3 else "local"
            if not os.path.exists(filepath):
                return f"Error: Source file '{filepath}' does not exist in '{os.getcwd()}'. Please specify an existing file (e.g. `/save README.md {target}`) or create '{filepath}' first."
            return save_file(source_path=filepath, target=target)

        # 5. Build conversation context
        system_prompt = self.build_system_prompt(query=prompt_instruction, file_content=edit_file_content)
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append(h)
        messages.append({"role": "user", "content": prompt_instruction})

        for iteration in range(self.max_iterations):
            if on_status_update:
                on_status_update(f"Reasoning (step {iteration + 1})...")

            try:
                resp = requests.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "messages": messages,
                        "temperature": 0.2,
                        "max_tokens": 600,
                    },
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                reply = resp.json()["choices"][0]["message"]["content"].strip()
            except requests.exceptions.RequestException as e:
                return f"Error contacting model server: {e}"

            # Check if model requested a tool
            tool_call = self._parse_tool_call(reply)
            if not tool_call:
                # No tool call, model provided direct answer
                return reply

            tool_name = tool_call["name"]
            tool_args = tool_call.get("arguments", {})

            if on_tool_start:
                on_tool_start(tool_name, tool_args)

            # Execute tool
            start_t = time.time()
            result = registry.execute_tool(tool_name, tool_args)
            duration = round(time.time() - start_t, 2)

            if on_tool_finish:
                on_tool_finish(tool_name, result)

            # If tool modified a file, update active file
            if tool_name in ("write_file", "replace_in_file") and "filepath" in tool_args:
                self.active_file = tool_args["filepath"]

            # Append to prompt messages
            messages.append({"role": "assistant", "content": reply})
            observation_msg = f"Tool Observation for '{tool_name}':\n{result}"
            messages.append({"role": "user", "content": observation_msg})

        return reply