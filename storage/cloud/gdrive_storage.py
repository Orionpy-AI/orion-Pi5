# tools/cloud/gdrive_storage.py
"""
Google Drive backend for Orion, built on rclone.

Two modes, both supported:
1. Mount mode (default): reads/writes go through the rclone FUSE mount
   at GDRIVE_MOUNT_PATH (e.g. /mnt/gdrive), so plain file I/O works.
2. CLI mode: falls back to `rclone copy` / `rclone lsjson` / `rclone delete`
   against the configured remote (GDRIVE_REMOTE, e.g. "gdrive:") for
   environments where the mount isn't up.

This same module works for any other rclone remote you configure
(Dropbox, OneDrive, etc.) — just point GDRIVE_REMOTE / GDRIVE_MOUNT_PATH
at that remote instead, or copy this file per-remote.
"""
import os
import shutil
import subprocess
from typing import Optional

GDRIVE_MOUNT_PATH = os.environ.get("GDRIVE_MOUNT_PATH", "/mnt/gdrive")
GDRIVE_REMOTE = os.environ.get("GDRIVE_REMOTE", "gdrive:")


def _mount_is_live() -> bool:
    """A mounted-but-dead rclone mount still exists as a path but errors on access."""
    if not os.path.ismount(GDRIVE_MOUNT_PATH) and not os.path.exists(GDRIVE_MOUNT_PATH):
        return False
    try:
        os.listdir(GDRIVE_MOUNT_PATH)
        return True
    except Exception:
        return False


def _run_rclone(args: list, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["rclone"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def save_to_gdrive(source_path: str, dest_relative_path: str = "") -> str:
    """Upload/copy a local file into Google Drive."""
    if not os.path.exists(source_path):
        return f"Error: source file '{source_path}' does not exist."

    dest_rel = dest_relative_path or os.path.basename(source_path)

    if _mount_is_live():
        dest_abs = os.path.join(GDRIVE_MOUNT_PATH, dest_rel.lstrip("/"))
        try:
            os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
            shutil.copy2(source_path, dest_abs)
            return f"Saved to Google Drive (via mount): {dest_rel}"
        except Exception as e:
            return f"Error saving via gdrive mount: {e}"

    # Fallback: rclone copyto via CLI
    dest_remote_path = f"{GDRIVE_REMOTE}{dest_rel.lstrip('/')}"
    try:
        result = _run_rclone(["copyto", source_path, dest_remote_path])
        if result.returncode != 0:
            return f"Error uploading to Google Drive: {result.stderr.strip()}"
        return f"Saved to Google Drive (via rclone): {dest_rel}"
    except Exception as e:
        return f"Error uploading to Google Drive: {e}"


def list_gdrive(dir_relative_path: str = "") -> str:
    """List files/folders in Google Drive."""
    if _mount_is_live():
        target = os.path.join(GDRIVE_MOUNT_PATH, dir_relative_path.lstrip("/"))
        if not os.path.exists(target):
            return f"Error: '{dir_relative_path}' does not exist in Google Drive."
        try:
            entries = sorted(os.listdir(target))
            if not entries:
                return f"Google Drive folder '{dir_relative_path or '/'}' is empty."
            lines = [f"Google Drive contents of '{dir_relative_path or '/'}':"]
            for e in entries:
                full = os.path.join(target, e)
                tag = "[DIR]" if os.path.isdir(full) else "[FILE]"
                lines.append(f"  {tag} {e}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing Google Drive: {e}"

    remote_path = f"{GDRIVE_REMOTE}{dir_relative_path.lstrip('/')}"
    try:
        result = _run_rclone(["lsf", remote_path])
        if result.returncode != 0:
            return f"Error listing Google Drive: {result.stderr.strip()}"
        entries = result.stdout.strip().splitlines()
        if not entries:
            return f"Google Drive folder '{dir_relative_path or '/'}' is empty."
        return f"Google Drive contents of '{dir_relative_path or '/'}':\n" + "\n".join(entries)
    except Exception as e:
        return f"Error listing Google Drive: {e}"


def delete_from_gdrive(relative_path: str) -> str:
    """Delete a file from Google Drive."""
    if _mount_is_live():
        target = os.path.join(GDRIVE_MOUNT_PATH, relative_path.lstrip("/"))
        if not os.path.exists(target):
            return f"Error: '{relative_path}' does not exist in Google Drive."
        try:
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
            return f"Deleted '{relative_path}' from Google Drive."
        except Exception as e:
            return f"Error deleting from Google Drive: {e}"

    remote_path = f"{GDRIVE_REMOTE}{relative_path.lstrip('/')}"
    try:
        result = _run_rclone(["deletefile", remote_path])
        if result.returncode != 0:
            return f"Error deleting from Google Drive: {result.stderr.strip()}"
        return f"Deleted '{relative_path}' from Google Drive."
    except Exception as e:
        return f"Error deleting from Google Drive: {e}"


def gdrive_status() -> str:
    """Report whether the Google Drive mount/remote is reachable."""
    if _mount_is_live():
        return f"Google Drive: connected (mounted at {GDRIVE_MOUNT_PATH})"
    try:
        result = _run_rclone(["lsd", GDRIVE_REMOTE], timeout=15)
        if result.returncode == 0:
            return f"Google Drive: connected (via rclone CLI, remote '{GDRIVE_REMOTE}')"
        return f"Google Drive: NOT reachable ({result.stderr.strip()})"
    except Exception as e:
        return f"Google Drive: NOT reachable ({e})"