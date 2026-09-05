#!/usr/bin/env python3
"""
Orion CLI: Rich-based Interactive Chat & Agent Engine.
Integrates local LLM execution, MCP tools, Codebase RAG, and Safe Code Modification.
"""
import argparse
import os
import signal
import subprocess
import sys
import time

import requests
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from ui import render_banner, print_card, print_tool_card, console, play_mascot_intro
from tools import registry, rag_engine, mcp_manager
from agent import OrionAgent

_stop = False


def _handle_stop(_sig, _frame):
    global _stop
    _stop = True


def cmd_banner(args):
    render_banner(
        memory_count=args.memories,
        active_file=args.file,
        voice_enabled=args.voice,
        model_name=args.model,
    )


def cmd_prompt(_args):
    console.print("[bold bright_magenta]You[/bold bright_magenta] [dim]›[/dim] ", end="")


def cmd_spinner(args):
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    spinner = Spinner("orion_orb", text=Text(f" {args.text}", style="bright_cyan"))
    with Live(spinner, console=console, refresh_per_second=12, transient=True):
        while not _stop:
            time.sleep(0.08)


def cmd_card(args):
    print_card(title=args.title, content=args.content, style=args.style, subtitle=args.subtitle)


# ---- Full Interactive Agent Chat --------------------------------------------

def _find_model_path() -> str:
    explicit = os.environ.get("MODEL_PATH")
    if explicit and os.path.exists(explicit):
        return explicit
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "models", "qwen2.5-0.5b-instruct-q4_k_m.gguf"),
        os.path.expanduser("~/models/qwen2.5-0.5b-instruct-q4_k_m.gguf"),
        os.path.expanduser("~/orion-llm/models/qwen2.5-0.5b-instruct-q4_k_m.gguf"),
        "/models/qwen2.5-0.5b-instruct-q4_k_m.gguf",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return explicit or candidates[0]

MODEL_PATH = _find_model_path()
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 8000))
N_CTX = 2048
BASE_URL = f"http://localhost:{PORT}"
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen2.5-0.5B-Instruct")

_server_process = None


def _start_server():
    global _server_process
    threads = str(os.cpu_count() or 4)
    cmd = [
        sys.executable, "-m", "llama_cpp.server",
        "--model", MODEL_PATH,
        "--host", HOST,
        "--port", str(PORT),
        "--n_ctx", str(N_CTX),
        "--n_threads", threads,
        "--n_batch", "512",
        "--mlock",
    ]
    log_file = open("/tmp/llama-server.log" if os.name != "nt" else "llama-server.log", "w")
    _server_process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)


def _check_server_running() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/v1/models", timeout=0.5)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


def _wait_for_server(timeout: int = 120) -> bool:
    start = time.time()
    with console.status("[bold cyan]Loading model into RAM...", spinner="orion_orb"):
        while time.time() - start < timeout:
            if _check_server_running():
                return True
            time.sleep(0.5)
    return False


def _stop_server():
    global _server_process
    if _server_process and _server_process.poll() is None:
        _server_process.terminate()
        try:
            _server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _server_process.kill()


def _handle_sigint(_signum, _frame):
    console.print("\n[dim]Shutting down ORION and MCP servers...[/dim]")
    mcp_manager.shutdown()
    _stop_server()
    sys.exit(0)


def run_chat():
    signal.signal(signal.SIGINT, _handle_sigint)
    signal.signal(signal.SIGTERM, _handle_sigint)

    # 1. Load MCP servers
    mcp_manager.load_and_start_servers()
    all_tools = registry.get_all_tool_definitions()

    if mcp_manager.failed_servers:
        for name, err in mcp_manager.failed_servers.items():
            console.print(f"[bold red]✗ MCP server '{name}' failed to start:[/bold red] {err}")
    elif mcp_manager.load_error:
        console.print(f"[dim]ℹ MCP: {mcp_manager.load_error}[/dim]")

    # 2. Check if llama-cpp server is already running for instant connection
    is_running = _check_server_running()

    # 3. Render banner
    rag_status = f"{rag_engine.total_files} files" if rag_engine.indexed_path else "Off"
    render_banner(
        memory_count=0,
        active_file=None,
        rag_status=rag_status,
        tools_count=len(all_tools),
        model_name=MODEL_NAME,
    )

    if not is_running:
        if os.path.exists(MODEL_PATH):
            console.print(f"[dim]Starting llama-cpp server (4 CPU threads, mlock enabled)...[/dim]")
            _start_server()
            if not _wait_for_server():
                console.print("[bold red]Server failed to start. Check llama-server.log[/bold red]")
                _stop_server()
                mcp_manager.shutdown()
                sys.exit(1)
        else:
            console.print(f"[dim]Connecting to background llama-server at {BASE_URL}...[/dim]")
    else:
        play_mascot_intro(duration_seconds=0.3)

    console.print("[bold bright_green]✦ Orion Agent Online [Instant Connection].[/bold bright_green] Type your message or a command (/rag, /tools, /mcp, /edit, exit).\n")

    agent = OrionAgent(base_url=BASE_URL, model_name=MODEL_NAME)
    history = []

    try:
        while True:
            try:
                user_input = console.input("\n[bold bright_magenta]You[/bold bright_magenta] [dim]›[/dim] ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                break

            if user_input.lower() in ("/clear", "clear"):
                rag_status = f"{rag_engine.total_files} files" if rag_engine.indexed_path else "Off"
                render_banner(
                    memory_count=len(history),
                    active_file=agent.active_file,
                    rag_status=rag_status,
                    tools_count=len(registry.get_all_tool_definitions()),
                    model_name=MODEL_NAME,
                )
                continue

            current_tool_info = {"name": None, "args": {}}

            def on_status_update(status_text: str):
                pass

            def on_tool_start(tool_name: str, args: dict):
                current_tool_info["name"] = tool_name
                current_tool_info["args"] = args

            def on_tool_finish(tool_name: str, result: str):
                print_tool_card(tool_name, current_tool_info.get("args", {}), result)

            with console.status("[bold cyan]Thinking...", spinner="orion_orb"):
                reply = agent.run_turn(
                    history=history,
                    user_message=user_input,
                    on_status_update=on_status_update,
                    on_tool_start=on_tool_start,
                    on_tool_finish=on_tool_finish,
                )

            # Store history
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": reply})

            print_card("ORION", reply, style="cyan")

    finally:
        mcp_manager.shutdown()
        _stop_server()
        console.print("[dim]Orion offline. Goodbye.[/dim]")


# ---- Entry point -------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=False)

    b = sub.add_parser("banner")
    b.add_argument("--model", default="Local Model")
    b.add_argument("--memories", type=int, default=0)
    b.add_argument("--file", default=None)
    b.add_argument("--voice", action="store_true")
    b.set_defaults(func=cmd_banner)

    p = sub.add_parser("prompt")
    p.set_defaults(func=cmd_prompt)

    s = sub.add_parser("spinner")
    s.add_argument("--text", default="Thinking")
    s.set_defaults(func=cmd_spinner)

    c = sub.add_parser("card")
    c.add_argument("--title", default="ORION")
    c.add_argument("--content", required=True)
    c.add_argument("--style", default="cyan")
    c.add_argument("--subtitle", default="")
    c.set_defaults(func=cmd_card)

    args = parser.parse_args()

    if args.cmd is None:
        run_chat()
    else:
        args.func(args)


if __name__ == "__main__":
    main()