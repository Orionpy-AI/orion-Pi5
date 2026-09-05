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

from tools import registry, rag_engine, mcp_manager, read_file, save_file, list_files, delete_file, cloud_status


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
- To save files to persistent local (SD card), Google Drive, or OneDrive storage, use `save_file_to_cloud` or `save_file`.
- When asked to save files or manage storage, check current available space on targets and automatically select the backend with the highest free capacity unless specified.
- Automatically monitor drive mount status and attempt re-mounting if a target drive is disconnected or unmounted.

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

        # 1. Handle `/edit` command & subcommands
        if user_message.startswith("/edit"):
            parts = user_message.split(maxsplit=2)
            if len(parts) == 1:
                return (
                    "[bold]Usage for `/edit`:[/bold]\n"
                    "- `/edit <file>`: Set active file focus\n"
                    "- `/edit <file> <instruction>`: Edit active file directly\n"
                    "- `/edit clear` / `/edit reset`: Clear active file focus\n"
                    "- `/edit status` / `/edit active`: Show active file status"
                )

            subcmd = parts[1].lower().strip()
            if subcmd in ("clear", "reset"):
                old = self.active_file
                self.active_file = None
                return f"Cleared active file focus (was: `{old or 'None'}`)."

            if subcmd in ("status", "active"):
                if not self.active_file:
                    return "No active file currently focused."
                if os.path.exists(self.active_file):
                    line_count = len(open(self.active_file, "r", encoding="utf-8", errors="replace").readlines())
                    return f"Active file: [bold yellow]{self.active_file}[/bold yellow] ({line_count} lines)."
                return f"Active file set to: [bold yellow]{self.active_file}[/bold yellow] (new file)."

            filename = parts[1]
            self.active_file = filename

            if len(parts) == 2:
                if os.path.exists(filename):
                    content = read_file(filename, 1, 15)
                    return f"Active file set to: [bold yellow]{filename}[/bold yellow].\n{content}\n\n[dim]To modify it, ask what to change or use: `/edit {filename} <your instruction>`[/dim]"
                else:
                    return f"Active file set to: [bold yellow]{filename}[/bold yellow] (new file). Give instructions to write content."

            instruction = parts[2]
            if os.path.exists(filename):
                with open(filename, "r", encoding="utf-8", errors="replace") as f:
                    edit_file_content = f.read()

            prompt_instruction = (
                f"Please edit the file `{filename}` according to this instruction: {instruction}\n"
                f"Current file content of `{filename}`:\n```\n{edit_file_content}\n```\n"
                f"Use `replace_in_file` or `write_file` tool to apply the change."
            )

        # 2. Handle RAG commands & subcommands `/rag` / `/index`
        elif user_message.startswith("/rag") or user_message.startswith("/index"):
            parts = user_message.split(maxsplit=2)
            subcmd = parts[1].lower().strip() if len(parts) > 1 else ""

            if subcmd in ("clear", "reset"):
                rag_engine.indexed_path = None
                rag_engine.documents = []
                rag_engine.index = None
                return "RAG search index cleared."

            if subcmd in ("status", "info"):
                if not rag_engine.indexed_path:
                    return "RAG index is currently empty. Run `/rag <path>` or `/rag index <path>` to index a codebase."
                doc_count = len(rag_engine.documents)
                return (
                    f"[bold]RAG Index Status:[/bold]\n"
                    f"- Indexed Path: `{rag_engine.indexed_path}`\n"
                    f"- Document Chunks: {doc_count}\n"
                    f"- Status: Active"
                )

            if subcmd in ("query", "search", "find") and len(parts) >= 3:
                query_str = parts[2]
                matches = rag_engine.query(query_str, top_k=3)
                if not matches:
                    return f"No matches found in RAG index for query: '{query_str}'."
                lines = [f"[bold]RAG Results for '{query_str}':[/bold]"]
                for i, m in enumerate(matches, 1):
                    lines.append(f"\n{i}. **{m['rel_path']}** (score: {m['score']}):\n```\n{m['content'][:300]}...\n```")
                return "\n".join(lines)

            target_path = parts[2] if subcmd == "index" and len(parts) >= 3 else (parts[1] if len(parts) > 1 else ".")
            if on_status_update:
                on_status_update(f"Indexing directory '{target_path}' for RAG...")
            res = rag_engine.index_directory(target_path)
            if res.get("success"):
                return f"Successfully indexed [bold green]{res['files_indexed']}[/bold green] files ({res['chunks_created']} chunks) from `{res['path']}` into RAG engine."
            else:
                return f"RAG indexing failed: {res.get('error')}"

        # 3. Handle tool listing `/tools`
        elif user_message.startswith("/tools") or user_message.startswith("/tool"):
            parts = user_message.split()
            subcmd = parts[1].lower().strip() if len(parts) > 1 else ""
            tools = registry.get_all_tool_definitions()

            if subcmd in ("local", "builtin"):
                tools = [t for t in tools if "_mcp_server" not in t]
            elif subcmd == "mcp":
                tools = [t for t in tools if "_mcp_server" in t]

            lines = [f"Registered Tools ({len(tools)} available):"]
            for t in tools:
                fn = t["function"]
                prefix = "🛠️ [bold cyan]MCP[/bold cyan]" if "_mcp_server" in t else "⚡ [bold green]Local[/bold green]"
                lines.append(f"{prefix} **{fn['name']}**: {fn['description']}")
            return "\n".join(lines)

        # 4. Handle MCP server commands & subcommands `/mcp` / `/servers`
        elif user_message.startswith("/mcp") or user_message.startswith("/servers"):
            parts = user_message.split()
            subcmd = parts[1].lower().strip() if len(parts) > 1 else "status"

            if subcmd in ("reload", "restart", "refresh"):
                if on_status_update:
                    on_status_update("Reloading MCP servers...")
                mcp_manager.load_servers()
                for server_name, server in mcp_manager.servers.items():
                    for tool in server.tools:
                        registry.register_mcp_tool(server_name, tool, server.call_tool)
                return f"MCP servers reloaded. Active servers: {len(mcp_manager.servers)}."

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

            return "\n".join(lines)

        # 4b. Handle help menu `/help`
        elif user_message.strip() in ("/help", "/?", "help"):
            tools = registry.get_all_tool_definitions()
            local_count = sum(1 for t in tools if "_mcp_server" not in t)
            mcp_count = len(tools) - local_count
            return (
                "[bold]ORION Commands & Sub-commands Reference[/bold]\n\n"
                "[bold cyan]/help[/bold cyan]                                  Show this help menu\n\n"
                "[bold cyan]/edit <file>[/bold cyan]                           Focus a file for editing context\n"
                "[bold cyan]/edit <file> <instruction>[/bold cyan]             Edit a file directly with instructions\n"
                "[bold cyan]/edit status[/bold cyan] | [bold cyan]/edit clear[/bold cyan]            View active file status or clear focus\n\n"
                "[bold cyan]/rag <path>[/bold cyan]                            Index codebase directory for RAG search\n"
                "[bold cyan]/rag query <search_term>[/bold cyan]              Perform semantic BM25 query on codebase\n"
                "[bold cyan]/rag status[/bold cyan] | [bold cyan]/rag clear[/bold cyan]             Show index metrics or reset RAG engine\n\n"
                "[bold cyan]/cloud[/bold cyan] | [bold cyan]/cloud status[/bold cyan]                 Show local + cloud storage status\n"
                "[bold cyan]/cloud list [local|gdrive|onedrive][/bold cyan]  List stored files on target drive\n"
                "[bold cyan]/cloud mount[/bold cyan]                          Re-initialize & auto-mount all drives\n"
                "[bold cyan]/cloud delete <target> <file>[/bold cyan]         Delete a file from cloud/local storage\n\n"
                "[bold cyan]/save <file> [local|gdrive|onedrive][/bold cyan]   Save file to specified storage\n"
                "[bold cyan]/save <file> auto[/bold cyan]                     Save to storage with highest free space\n\n"
                "[bold cyan]/tools[/bold cyan] | [bold cyan]/tools [local|mcp][/bold cyan]           List all registered tools (or filter)\n"
                "[bold cyan]/mcp status[/bold cyan] | [bold cyan]/mcp reload[/bold cyan]              View active MCP servers or reload configuration\n"
                "[bold cyan]/clear[/bold cyan]                                  Clear screen and redraw banner\n"
                "[bold cyan]exit[/bold cyan] / [bold cyan]quit[/bold cyan]                            Quit Orion agent\n\n"
                f"[dim]{local_count} local tools, {mcp_count} MCP tools registered.[/dim]"
            )

        # 5. Handle Cloud Storage commands & subcommands `/cloud` / `/storage`
        elif user_message.startswith("/cloud") or user_message.startswith("/storage"):
            parts = user_message.split(maxsplit=3)
            subcmd = parts[1].lower().strip() if len(parts) > 1 else "status"

            if subcmd in ("mount", "remount", "init"):
                import subprocess
                try:
                    res = subprocess.run(["bash", "mount_drives.sh"], capture_output=True, text=True, timeout=15)
                    return f"Drive mount initialization output:\n```\n{res.stdout.strip()}\n```"
                except Exception as e:
                    return f"Error executing mount_drives.sh: {e}"

            if subcmd in ("list", "ls"):
                target = parts[2] if len(parts) >= 3 else "local"
                rel_path = parts[3] if len(parts) >= 4 else ""
                return list_files(target=target, dir_relative_path=rel_path)

            if subcmd in ("delete", "rm", "del"):
                if len(parts) < 3:
                    return "Usage: `/cloud delete <target> <relative_filepath>` (e.g. `/cloud delete onedrive report.pdf`)"
                target = parts[2]
                rel_path = parts[3] if len(parts) >= 4 else ""
                return delete_file(target=target, relative_path=rel_path)

            return cloud_status()

        # 6. Handle `/save` command & subcommands
        elif user_message.startswith("/save"):
            parts = user_message.split()
            if len(parts) < 2:
                return (
                    "[bold]Usage for `/save`:[/bold]\n"
                    "- `/save <filepath>`: Save file to local SD card storage\n"
                    "- `/save <filepath> <local|gdrive|onedrive>`: Save to specific target\n"
                    "- `/save <filepath> auto`: Auto-select target with highest free space"
                )
            filepath = parts[1]
            target = parts[2] if len(parts) >= 3 else "local"

            if target.lower() == "auto":
                from storage import get_banner_storage_summary
                summary = get_banner_storage_summary()
                best_target = "local"
                max_free = -1.0
                for tgt, val_str in summary.items():
                    if "(" in val_str and "GB free" in val_str:
                        try:
                            free_val = float(val_str.split("(")[1].split("GB free")[0].strip())
                            if free_val > max_free:
                                max_free = free_val
                                best_target = tgt
                        except Exception:
                            pass
                target = best_target

            if not os.path.exists(filepath):
                return f"Error: Source file '{filepath}' does not exist in '{os.getcwd()}'."
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