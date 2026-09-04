# code_tools.py
"""
Code inspection and modification tools for Orion LLM.
Supports reading, writing, exact block replacing, directory listing, and pattern searching.
"""
import os
import re
import difflib
from typing import Optional


def read_file(filepath: str, start_line: Optional[int] = 1, end_line: Optional[int] = None) -> str:
    """Read the contents of a file with optional line range (1-indexed)."""
    abs_path = os.path.abspath(filepath)
    if not os.path.exists(abs_path):
        return f"Error: File '{filepath}' does not exist."
    if not os.path.isfile(abs_path):
        return f"Error: '{filepath}' is not a regular file."

    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        start = max(1, start_line or 1)
        end = min(total_lines, end_line or total_lines)

        if start > total_lines:
            return f"Error: start_line ({start}) exceeds total lines ({total_lines})."

        selected = lines[start - 1 : end]
        output = [f"--- File: {filepath} (Lines {start}-{end} of {total_lines}) ---"]
        for idx, line in enumerate(selected, start=start):
            output.append(f"{idx:4d} | {line.rstrip()}")
        return "\n".join(output)
    except Exception as e:
        return f"Error reading file '{filepath}': {e}"


def write_file(filepath: str, content: str) -> str:
    """Write or overwrite a file with given content. Automatically creates parent directories."""
    try:
        abs_path = os.path.abspath(filepath)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} bytes to '{filepath}'."
    except Exception as e:
        return f"Error writing to file '{filepath}': {e}"


def replace_in_file(filepath: str, target: str, replacement: str) -> str:
    """
    Replace target string in a file with replacement string.
    Target must match exactly once in the file to avoid ambiguous edits.
    """
    abs_path = os.path.abspath(filepath)
    if not os.path.exists(abs_path):
        return f"Error: File '{filepath}' does not exist."

    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()

        count = original.count(target)
        if count == 0:
            return f"Error: Target text not found in '{filepath}'. Please verify the exact text to replace."
        if count > 1:
            return f"Error: Target text found {count} times in '{filepath}'. Please include more surrounding context to make it unique."

        modified = original.replace(target, replacement, 1)

        # Generate diff preview
        diff = list(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(filepath)}",
                tofile=f"b/{os.path.basename(filepath)}",
                n=3,
            )
        )

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(modified)

        diff_text = "".join(diff) if diff else "No changes detected."
        return f"Successfully updated '{filepath}'.\nDiff:\n{diff_text}"
    except Exception as e:
        return f"Error replacing content in '{filepath}': {e}"


def list_dir(dir_path: str = ".", max_entries: int = 50) -> str:
    """List directory contents with file types and sizes."""
    abs_path = os.path.abspath(dir_path)
    if not os.path.exists(abs_path):
        return f"Error: Directory '{dir_path}' does not exist."
    if not os.path.isdir(abs_path):
        return f"Error: '{dir_path}' is not a directory."

    try:
        entries = sorted(os.listdir(abs_path))
        lines = [f"Contents of '{dir_path}' ({len(entries)} items):"]
        count = 0
        for entry in entries:
            if count >= max_entries:
                lines.append(f"... and {len(entries) - max_entries} more items.")
                break
            full = os.path.join(abs_path, entry)
            if os.path.isdir(full):
                lines.append(f"  [DIR]  {entry}/")
            else:
                size = os.path.getsize(full)
                lines.append(f"  [FILE] {entry} ({size} bytes)")
            count += 1
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing directory '{dir_path}': {e}"


def search_code(pattern: str, dir_path: str = ".", max_matches: int = 30) -> str:
    """Search for regex or text pattern in files across directory recursively."""
    abs_path = os.path.abspath(dir_path)
    if not os.path.exists(abs_path):
        return f"Error: Path '{dir_path}' does not exist."

    ignored_dirs = {".git", "__pycache__", "node_modules", ".venv", "llm-env", ".agents", "venv"}
    ignored_exts = {".pyc", ".gguf", ".bin", ".tar.gz", ".zip", ".png", ".jpg", ".jpeg", ".pdf"}

    matches = []
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Invalid regex pattern '{pattern}': {e}"

    for root, dirs, files in os.walk(abs_path):
        dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ignored_exts:
                continue

            full_file = os.path.join(root, file)
            rel_file = os.path.relpath(full_file, abs_path)

            try:
                with open(full_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line_no, line in enumerate(f, start=1):
                        if regex.search(line):
                            matches.append(f"{rel_file}:{line_no}: {line.strip()}")
                            if len(matches) >= max_matches:
                                return f"Search results for '{pattern}' (capped at {max_matches}):\n" + "\n".join(matches)
            except Exception:
                continue

    if not matches:
        return f"No matches found for '{pattern}' in '{dir_path}'."
    return f"Search results for '{pattern}' ({len(matches)} matches):\n" + "\n".join(matches)
