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
import time

ONEDRIVE_MOUNT_PATH = os.environ.get("ONEDRIVE_MOUNT_PATH", "/mnt/onedrive")
ONEDRIVE_REMOTE = os.environ.get("ONEDRIVE_REMOTE", "onedrive:")


def _check_mount_active() -> bool:
    """Check if OneDrive mount path is an active FUSE mount."""
    if not os.path.ismount(ONEDRIVE_MOUNT_PATH):
        return False
    try:
        os.listdir(ONEDRIVE_MOUNT_PATH)
        return True
    except Exception:
        return False


def ensure_onedrive_mounted() -> bool:
    """Ensure the rclone mount for OneDrive is active. If not, attempt daemonized mount."""
    if _check_mount_active():
        return True
    try:
        os.makedirs(ONEDRIVE_MOUNT_PATH, exist_ok=True)
        res = subprocess.run(["rclone", "version"], capture_output=True, timeout=5)
        if res.returncode == 0:
            cmd = [
                "rclone", "mount", ONEDRIVE_REMOTE, ONEDRIVE_MOUNT_PATH,
                "--vfs-cache-mode", "writes",
                "--daemon"
            ]
            subprocess.run(cmd, capture_output=True, timeout=10)
            time.sleep(1)
            return _check_mount_active()
    except Exception:
        pass
    return _check_mount_active()


def _mount_is_live() -> bool:
    """Ensure mount is attempted and check if live."""
    return ensure_onedrive_mounted()


def _run_rclone(args: list, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["rclone"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def save_to_onedrive(source_path: str, dest_relative_path: str = "") -> str:
    """Upload/copy a local file into OneDrive permanently."""
    if not os.path.exists(source_path):
        return f"Error: source file '{source_path}' does not exist."

    dest_rel = dest_relative_path or os.path.basename(source_path)

    # 1. Always attempt upload directly via rclone CLI to guarantee cloud persistence
    dest_remote_path = f"{ONEDRIVE_REMOTE}{dest_rel.lstrip('/')}"
    try:
        result = _run_rclone(["copyto", source_path, dest_remote_path])
        if result.returncode == 0:
            if _mount_is_live():
                dest_abs = os.path.join(ONEDRIVE_MOUNT_PATH, dest_rel.lstrip("/"))
                try:
                    os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
                    shutil.copy2(source_path, dest_abs)
                except Exception:
                    pass
            return f"Saved to OneDrive (permanently uploaded): {dest_rel}"
    except Exception:
        pass

    # 2. Fallback to mount copy if rclone CLI is not directly reachable
    if _mount_is_live():
        dest_abs = os.path.join(ONEDRIVE_MOUNT_PATH, dest_rel.lstrip("/"))
        try:
            os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
            shutil.copy2(source_path, dest_abs)
            return f"Saved to OneDrive (via mount): {dest_rel}"
        except Exception as e:
            return f"Error saving via onedrive mount: {e}"

    return f"Error: Failed to upload '{source_path}' to OneDrive."


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
