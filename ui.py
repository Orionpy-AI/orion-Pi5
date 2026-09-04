# ui.py
import os
import sys
import time
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.spinner import SPINNERS
from rich.syntax import Syntax
from rich import box

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

console = Console()

ORION_ASCII = """
  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗
 ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║
 ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║
 ██║   ██║██╔══██╗██║██║   ██║██║╚██╗██║
 ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║
  ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝ 
"""

# Register custom "ORION orb" spinner
SPINNERS["orion_orb"] = {
    "interval": 110,
    "frames": ["◜", "◠", "◝", "◞", "◡", "◟"],
}

_MASCOT_FRAMES = [
    "   ⟡   ",
    "  ⟡·   ",
    " ⟡··   ",
    "⟡···   ",
    " ·⟡··  ",
    "  ··⟡· ",
    "   ···⟡",
    "  ··⟡· ",
    " ·⟡··  ",
    "⟡···   ",
    " ⟡··   ",
    "  ⟡·   ",
]


def hex_to_rgb(hex_str: str) -> tuple:
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))


def get_gradient_ascii() -> Text:
    lines = ORION_ASCII.strip("\n").split("\n")
    gradient_text = Text()
    total_lines = len(lines)
    
    start_r, start_g, start_b = hex_to_rgb("#5FC3E4")
    end_r, end_g, end_b = hex_to_rgb("#E55D87")
    
    for i, line in enumerate(lines):
        ratio = i / max(1, total_lines - 1)
        r = int(start_r + (end_r - start_r) * ratio)
        g = int(start_g + (end_g - start_g) * ratio)
        b = int(start_b + (end_b - start_b) * ratio)
        gradient_text.append(line + "\n", style=f"rgb({r},{g},{b})")
        
    return gradient_text


def play_mascot_intro(duration_seconds: float = 1.2):
    """Cosmetic pulsing orb animation at startup."""
    try:
        start = time.time()
        i = 0
        with Live(console=console, refresh_per_second=12, transient=True) as live:
            while time.time() - start < duration_seconds:
                frame = _MASCOT_FRAMES[i % len(_MASCOT_FRAMES)]
                live.update(Text(f"  {frame}  ORION AI Engine online [RAG + MCP Ready]", style="bright_cyan"))
                time.sleep(0.09)
                i += 1
    except Exception:
        pass


def render_banner(
    memory_count: int = 0,
    active_file: Optional[str] = None,
    rag_status: str = "Off",
    tools_count: int = 0,
    voice_enabled: bool = False,
    model_name: str = "Local Model",
):
    """Render Gemini/Claude Code styled top banner with gradient art and system status."""
    os.system('cls' if os.name == 'nt' else 'clear')
    
    console.print(get_gradient_ascii())
    
    info_text = Text()
    info_text.append(" ✦ MODEL: ", style="bold dim white")
    info_text.append(f"{model_name} ", style="bright_blue")
    info_text.append("│ ", style="dim white")

    info_text.append("RAG: ", style="bold dim white")
    info_text.append(f"{rag_status} ", style="bright_green" if rag_status != "Off" else "dim white")
    info_text.append("│ ", style="dim white")

    info_text.append("TOOLS: ", style="bold dim white")
    info_text.append(f"{tools_count} active ", style="bright_cyan")
    info_text.append("│ ", style="dim white")

    info_text.append("ACTIVE FILE: ", style="bold dim white")
    info_text.append(f"{active_file if active_file else 'None'}\n", style="bright_yellow")

    try:
        from storage import get_banner_storage_summary
        st = get_banner_storage_summary()
        info_text.append(" 💾 STORAGE: ", style="bold dim white")
        info_text.append("Local SD: ", style="dim white")
        info_text.append(f"{st['local']} ", style="bright_green" if "Active" in st['local'] else "dim red")
        info_text.append("│ ", style="dim white")
        info_text.append("GDrive: ", style="dim white")
        info_text.append(f"{st['gdrive']} ", style="bright_green" if "Mounted" in st['gdrive'] else "dim yellow")
        info_text.append("│ ", style="dim white")
        info_text.append("OneDrive: ", style="dim white")
        info_text.append(f"{st['onedrive']}", style="bright_green" if "Mounted" in st['onedrive'] else "dim yellow")
    except Exception:
        pass

    console.print(
        Panel(
            info_text,
            subtitle="[dim]Commands: [bold white]/help[/bold white] │ [bold white]/cloud[/bold white] │ [bold white]/save <file> [target][/bold white] │ [bold white]/rag <path>[/bold white] │ [bold white]/tools[/bold white] │ [bold white]/mcp[/bold white] │ [bold white]/edit <file>[/bold white] │ [bold white]exit[/bold white][/dim]",
            subtitle_align="right",
            border_style="bright_blue",
            padding=(0, 1),
        )
    )
    console.print()


def print_card(title: str, content: str, style: str = "cyan", subtitle: str = ""):
    """Wraps text in a rounded Rich card container."""
    panel = Panel(
        content,
        title=f"[bold {style}]✦ {title} ✦[/bold {style}]",
        title_align="left",
        subtitle=f"[dim]{subtitle}[/dim]" if subtitle else None,
        box=box.ROUNDED,
        border_style=style,
        padding=(1, 2),
    )
    console.print(panel)


def print_tool_card(tool_name: str, arguments: dict, result: str):
    """Render a clean card displaying tool execution and its output."""
    body = Text()
    body.append("Arguments: ", style="bold dim white")
    body.append(f"{arguments}\n\n", style="bright_yellow")

    if "Diff:\n" in result:
        parts = result.split("Diff:\n", 1)
        body.append(parts[0] + "\n", style="green")
        syntax = Syntax(parts[1], "diff", theme="monokai", line_numbers=False)
        console.print(
            Panel(
                syntax,
                title=f"[bold magenta]⚡ Tool: {tool_name}[/bold magenta]",
                subtitle="[dim]Code Modified[/dim]",
                box=box.ROUNDED,
                border_style="magenta",
            )
        )
        return

    output_preview = result if len(result) <= 600 else result[:600] + "\n... (truncated)"
    body.append("Result:\n", style="bold dim white")
    body.append(output_preview, style="white")

    console.print(
        Panel(
            body,
            title=f"[bold magenta]⚡ Tool Executed: {tool_name}[/bold magenta]",
            box=box.ROUNDED,
            border_style="magenta",
            padding=(0, 2),
        )
    )