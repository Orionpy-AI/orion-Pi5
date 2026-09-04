# storage/cloud/onedrive_storage.py
"""
OneDrive backend for Orion, built on rclone.

Two modes, both supported:
1. Mount mode (default): reads/writes go through the rclone FUSE mount
   at ONEDRIVE_MOUNT_PATH (e.g. /mnt/onedrive), so plain file I/O works.
2. CLI mode: falls back to `rclone copy` / `rclone lsf` / `rclone delete`
   against the configured remote (ONEDRIVE_REMOTE, e.g. "onedrive:") for
   environments where the mount isn't up.
"""
import os
import shutil
import subprocess

ONEDRIVE_MOUNT_PATH = os.environ.get("ONEDRIVE_MOUNT_PATH", "/mnt/onedrive")
ONEDRIVE_REMOTE = os.environ.get("ONEDRIVE_REMOTE", "onedrive:")


def _mount_is_live() -> bool:
    """A mounted-but-dead rclone mount still exists as a path but errors on access."""
    if not os.path.ismount(ONEDRIVE_MOUNT_PATH) and not os.path.exists(ONEDRIVE_MOUNT_PATH):
        return False
    try:
        os.listdir(ONEDRIVE_MOUNT_PATH)
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


def save_to_onedrive(source_path: str, dest_relative_path: str = "") -> str:
    """Upload/copy a local file into OneDrive."""
    if not os.path.exists(source_path):
        return f"Error: source file '{source_path}' does not exist."

    dest_rel = dest_relative_path or os.path.basename(source_path)

    if _mount_is_live():
        dest_abs = os.path.join(ONEDRIVE_MOUNT_PATH, dest_rel.lstrip("/"))
        try:
            os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
            shutil.copy2(source_path, dest_abs)
            return f"Saved to OneDrive (via mount): {dest_rel}"
        except Exception as e:
            return f"Error saving via onedrive mount: {e}"

    # Fallback: rclone copyto via CLI
    dest_remote_path = f"{ONEDRIVE_REMOTE}{dest_rel.lstrip('/')}"
    try:
        result = _run_rclone(["copyto", source_path, dest_remote_path])
        if result.returncode != 0:
            return f"Error uploading to OneDrive: {result.stderr.strip()}"
        return f"Saved to OneDrive (via rclone): {dest_rel}"
    except Exception as e:
        return f"Error uploading to OneDrive: {e}"


def list_onedrive(dir_relative_path: str = "") -> str:
    """List files/folders in OneDrive."""
    if _mount_is_live():
        target = os.path.join(ONEDRIVE_MOUNT_PATH, dir_relative_path.lstrip("/"))
        if not os.path.exists(target):
            return f"Error: '{dir_relative_path}' does not exist in OneDrive."
        try:
            entries = sorted(os.listdir(target))
            if not entries:
                return f"OneDrive folder '{dir_relative_path or '/'}' is empty."
            lines = [f"OneDrive contents of '{dir_relative_path or '/'}':"]
            for e in entries:
                full = os.path.join(target, e)
                tag = "[DIR]" if os.path.isdir(full) else "[FILE]"
                lines.append(f"  {tag} {e}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing OneDrive: {e}"

    remote_path = f"{ONEDRIVE_REMOTE}{dir_relative_path.lstrip('/')}"
    try:
        result = _run_rclone(["lsf", remote_path])
        if result.returncode != 0:
            return f"Error listing OneDrive: {result.stderr.strip()}"
        entries = result.stdout.strip().splitlines()
        if not entries:
            return f"OneDrive folder '{dir_relative_path or '/'}' is empty."
        return f"OneDrive contents of '{dir_relative_path or '/'}':\n" + "\n".join(entries)
    except Exception as e:
        return f"Error listing OneDrive: {e}"


def delete_from_onedrive(relative_path: str) -> str:
    """Delete a file from OneDrive."""
    if _mount_is_live():
        target = os.path.join(ONEDRIVE_MOUNT_PATH, relative_path.lstrip("/"))
        if not os.path.exists(target):
            return f"Error: '{relative_path}' does not exist in OneDrive."
        try:
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
            return f"Deleted '{relative_path}' from OneDrive."
        except Exception as e:
            return f"Error deleting from OneDrive: {e}"

    remote_path = f"{ONEDRIVE_REMOTE}{relative_path.lstrip('/')}"
    try:
        result = _run_rclone(["deletefile", remote_path])
        if result.returncode != 0:
            return f"Error deleting from OneDrive: {result.stderr.strip()}"
        return f"Deleted '{relative_path}' from OneDrive."
    except Exception as e:
        return f"Error deleting from OneDrive: {e}"


def onedrive_status() -> str:
    """Report whether the OneDrive mount/remote is reachable."""
    if _mount_is_live():
        return f"OneDrive: connected (mounted at {ONEDRIVE_MOUNT_PATH})"
    try:
        result = _run_rclone(["lsd", ONEDRIVE_REMOTE], timeout=15)
        if result.returncode == 0:
            return f"OneDrive: connected (via rclone CLI, remote '{ONEDRIVE_REMOTE}')"
        return f"OneDrive: NOT reachable ({result.stderr.strip()})"
    except Exception as e:
        return f"OneDrive: NOT reachable ({e})"
