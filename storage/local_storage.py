# storage/local_storage.py
"""
Local storage backend for Orion.
Points LOCAL_STORAGE_PATH at your mounted 16GB SD card (/mnt/sdcard) or fallback folder.
"""
import os
import shutil
import subprocess
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

_PROJECT_STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "saved_files"))
os.makedirs(_PROJECT_STORAGE_DIR, exist_ok=True)


def ensure_sdcard_mounted() -> bool:
    """Check if /mnt/sdcard is mounted. If not, attempt to mount it if a block device exists."""
    mount_target = os.environ.get("LOCAL_STORAGE_PATH", "/mnt/sdcard")
    if os.path.ismount(mount_target):
        return True

    # Try running mount command if in fstab or block device is available
    if mount_target == "/mnt/sdcard":
        try:
            os.makedirs("/mnt/sdcard", exist_ok=True)
            res = subprocess.run(["sudo", "mount", "/mnt/sdcard"], capture_output=True, timeout=5)
            if os.path.ismount("/mnt/sdcard"):
                return True
        except Exception:
            pass

        # Try mounting common SD card block devices if present (Pi 5 SD slot is /dev/mmcblk0p1 or /dev/mmcblk0)
        candidate_devs = ["/dev/mmcblk0p1", "/dev/mmcblk0", "/dev/mmcblk1p1", "/dev/sdb1", "/dev/sda1"]
        for dev in candidate_devs:
            if os.path.exists(dev):
                try:
                    res = subprocess.run(["sudo", "mount", dev, "/mnt/sdcard"], capture_output=True, timeout=5)
                    if os.path.ismount("/mnt/sdcard"):
                        return True
                except Exception:
                    pass

    return os.path.ismount(mount_target)


def get_local_storage_dir() -> str:
    env_path = os.environ.get("LOCAL_STORAGE_PATH")
    if env_path:
        parent = os.path.dirname(env_path) if not os.path.exists(env_path) else env_path
        if os.access(parent if os.path.exists(parent) else "/", os.W_OK):
            return env_path

    # Check for automounts in /media/
    if os.path.exists("/media"):
        for root, dirs, _files in os.walk("/media"):
            for d in dirs:
                candidate = os.path.join(root, d)
                if os.path.ismount(candidate) and os.access(candidate, os.W_OK):
                    return candidate

    if os.path.exists("/mnt/sdcard") and os.access("/mnt/sdcard", os.W_OK):
        return "/mnt/sdcard"
    return _PROJECT_STORAGE_DIR


try:
    ensure_sdcard_mounted()
    LOCAL_STORAGE_PATH = get_local_storage_dir()
    os.makedirs(LOCAL_STORAGE_PATH, exist_ok=True)
except Exception:
    LOCAL_STORAGE_PATH = _PROJECT_STORAGE_DIR
    os.makedirs(LOCAL_STORAGE_PATH, exist_ok=True)


def _resolve(relative_path: str) -> str:
    current_path = get_local_storage_dir()
    try:
        os.makedirs(current_path, exist_ok=True)
    except Exception:
        current_path = _PROJECT_STORAGE_DIR
        os.makedirs(current_path, exist_ok=True)
    safe_rel = relative_path.lstrip("/")
    return os.path.abspath(os.path.join(current_path, safe_rel))


def save_to_local(source_path: str, dest_relative_path: str = "") -> str:
    """Copy a file from anywhere on disk into local storage (SD card / SSD)."""
    ensure_sdcard_mounted()
    current_path = get_local_storage_dir()
    if not os.path.exists(current_path):
        return f"Error: local storage path '{current_path}' is not mounted or accessible."
    if not os.path.exists(source_path):
        return f"Error: source file '{source_path}' does not exist."

    dest_rel = dest_relative_path or os.path.basename(source_path)
    dest_abs = _resolve(dest_rel)

    try:
        os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
        shutil.copy2(source_path, dest_abs)
        return f"Saved to local storage: {dest_abs}"
    except Exception as e:
        return f"Error saving to local storage: {e}"


def list_local(dir_relative_path: str = "") -> str:
    """List contents of a folder inside local storage."""
    ensure_sdcard_mounted()
    target = _resolve(dir_relative_path)
    if not os.path.exists(target):
        return f"Error: '{target}' does not exist in local storage."
    try:
        entries = sorted(os.listdir(target))
        if not entries:
            return f"'{dir_relative_path or '/'}' is empty."
        lines = [f"Local storage contents of '{dir_relative_path or '/'}':"]
        for e in entries:
            full = os.path.join(target, e)
            tag = "[DIR]" if os.path.isdir(full) else f"[FILE {os.path.getsize(full)}b]"
            lines.append(f"  {tag} {e}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing local storage: {e}"


def delete_local(relative_path: str) -> str:
    """Delete a file from local storage."""
    ensure_sdcard_mounted()
    target = _resolve(relative_path)
    if not os.path.exists(target):
        return f"Error: '{relative_path}' does not exist in local storage."
    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        return f"Deleted '{relative_path}' from local storage."
    except Exception as e:
        return f"Error deleting from local storage: {e}"


def get_local_usage() -> str:
    """Report free/used space on the local storage mount."""
    is_mounted = ensure_sdcard_mounted()
    current_path = get_local_storage_dir()
    if not os.path.exists(current_path):
        return f"Error: local storage path '{current_path}' is not mounted."
    total, used, free = shutil.disk_usage(current_path)
    gb = lambda x: round(x / (1024 ** 3), 2)
    mount_info = "mounted SD card" if (is_mounted or os.path.ismount(current_path)) else "unmounted, OS storage fallback"
    return (
        f"Local storage ({current_path} [{mount_info}]): "
        f"{gb(used)}GB used / {gb(total)}GB total ({gb(free)}GB free)"
    )