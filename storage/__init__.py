# storage/__init__.py
"""
Top-level storage package for Orion — lives at orion-llm/storage/, as a
SIBLING of tools/ (not nested inside it). Holds both the storage code
(this package) and, by default, the actual saved files themselves —
target='local' writes right into this same folder unless LOCAL_STORAGE_PATH
overrides it to point at a mounted SD card / SSD.

`tools/` imports from this package (see tools/__init__.py and
tools/registry.py) rather than containing its own copy.

local    -> this storage/ folder by default (or your mounted SD card/SSD
            path if you set LOCAL_STORAGE_PATH, e.g. /mnt/cloudstore)
gdrive   -> Google Drive, via the rclone mount at /mnt/gdrive
onedrive -> Microsoft OneDrive, via the rclone mount at /mnt/onedrive
"""
from .local_storage import (
    save_to_local,
    list_local,
    delete_local,
    get_local_usage,
    get_local_storage_dir,
    LOCAL_STORAGE_PATH,
)
from .cloud.gdrive_storage import (
    save_to_gdrive,
    list_gdrive,
    delete_from_gdrive,
    gdrive_status,
    GDRIVE_MOUNT_PATH,
)
from .cloud.onedrive_storage import (
    save_to_onedrive,
    list_onedrive,
    delete_from_onedrive,
    onedrive_status,
    ONEDRIVE_MOUNT_PATH,
)

VALID_TARGETS = ("local", "gdrive", "onedrive")


def save_file(source_path: str, target: str = "local", dest_relative_path: str = "") -> str:
    """Save a file to 'local' (SD card/SSD), 'gdrive' (Google Drive), or 'onedrive' (OneDrive)."""
    target_clean = target.lower().strip()
    if target_clean not in VALID_TARGETS:
        return f"Error: target must be one of {VALID_TARGETS}, got '{target}'."
    if target_clean == "local":
        return save_to_local(source_path, dest_relative_path)
    elif target_clean == "gdrive":
        return save_to_gdrive(source_path, dest_relative_path)
    else:
        return save_to_onedrive(source_path, dest_relative_path)


def list_files(target: str = "local", dir_relative_path: str = "") -> str:
    """List files on 'local', 'gdrive', or 'onedrive'."""
    target_clean = target.lower().strip()
    if target_clean not in VALID_TARGETS:
        return f"Error: target must be one of {VALID_TARGETS}, got '{target}'."
    if target_clean == "local":
        return list_local(dir_relative_path)
    elif target_clean == "gdrive":
        return list_gdrive(dir_relative_path)
    else:
        return list_onedrive(dir_relative_path)


def delete_file(target: str = "local", relative_path: str = "") -> str:
    """Delete a file from 'local', 'gdrive', or 'onedrive'."""
    target_clean = target.lower().strip()
    if target_clean not in VALID_TARGETS:
        return f"Error: target must be one of {VALID_TARGETS}, got '{target}'."
    if target_clean == "local":
        return delete_local(relative_path)
    elif target_clean == "gdrive":
        return delete_from_gdrive(relative_path)
    else:
        return delete_from_onedrive(relative_path)


def cloud_status() -> str:
    """Report status of all cloud/local storage backends."""
    lines = [get_local_usage(), gdrive_status(), onedrive_status()]
    return "\n".join(lines)


def get_banner_storage_summary() -> dict:
    """Return quick storage status dict with dynamic free/total space amounts from system/cloud providers for the UI banner."""
    import shutil
    import os
    import subprocess
    import json

    def _get_cloud_about(remote_name: str) -> dict:
        try:
            res = subprocess.run(
                ["rclone", "about", remote_name, "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                total = data.get("total")
                free = data.get("free")
                used = data.get("used")
                if total is not None:
                    if free is None and used is not None:
                        free = total - used
                    return {
                        "total_gb": round(total / (1024 ** 3), 1),
                        "free_gb": round((free or 0) / (1024 ** 3), 1),
                    }
        except Exception:
            pass
        return {}

    local_str = "Active"
    try:
        from .local_storage import ensure_sdcard_mounted
        ensure_sdcard_mounted()
        current_local_path = get_local_storage_dir()
        if os.path.exists(current_local_path):
            total, _, free = shutil.disk_usage(current_local_path)
            free_gb = round(free / (1024 ** 3), 1)
            total_gb = round(total / (1024 ** 3), 1)
            # If current path is unmounted OS root, check if /sys/block/mmcblk0 exists for real SD card size
            if not os.path.ismount(current_local_path) and os.path.exists("/sys/block/mmcblk0/size"):
                try:
                    with open("/sys/block/mmcblk0/size", "r") as f:
                        blocks = int(f.read().strip())
                        sd_gb = round((blocks * 512) / (1024 ** 3), 1)
                        if sd_gb > 0:
                            total_gb = sd_gb
                            if free_gb > total_gb:
                                free_gb = round(total_gb * 0.75, 1)
                except Exception:
                    pass
            local_str = f"Active ({free_gb}GB free / {total_gb}GB)"
        else:
            local_str = "Not Found"
    except Exception:
        local_str = "Active"

    from .cloud.gdrive_storage import _mount_is_live as gdrive_mounted, GDRIVE_REMOTE, GDRIVE_MOUNT_PATH
    from .cloud.onedrive_storage import _mount_is_live as onedrive_mounted, ONEDRIVE_REMOTE, ONEDRIVE_MOUNT_PATH

    gdrive_str = "CLI/Off"
    g_about = _get_cloud_about(GDRIVE_REMOTE)
    if g_about:
        gdrive_str = f"Mounted ({g_about['free_gb']}GB free / {g_about['total_gb']}GB)"
    elif gdrive_mounted():
        try:
            total_g, _, free_g = shutil.disk_usage(GDRIVE_MOUNT_PATH)
            free_gb = round(free_g / (1024 ** 3), 1)
            total_gb = round(total_g / (1024 ** 3), 1)
            gdrive_str = f"Mounted ({free_gb}GB free / {total_gb}GB)"
        except Exception:
            gdrive_str = "Mounted"

    onedrive_str = "CLI/Off"
    o_about = _get_cloud_about(ONEDRIVE_REMOTE)
    if o_about:
        onedrive_str = f"Mounted ({o_about['free_gb']}GB free / {o_about['total_gb']}GB)"
    elif onedrive_mounted():
        try:
            total_o, _, free_o = shutil.disk_usage(ONEDRIVE_MOUNT_PATH)
            free_gb = round(free_o / (1024 ** 3), 1)
            total_gb = round(total_o / (1024 ** 3), 1)
            onedrive_str = f"Mounted ({free_gb}GB free / {total_gb}GB)"
        except Exception:
            onedrive_str = "Mounted"

    return {
        "local": local_str,
        "gdrive": gdrive_str,
        "onedrive": onedrive_str,
    }


__all__ = [
    "save_file",
    "list_files",
    "delete_file",
    "cloud_status",
    "get_banner_storage_summary",
    "save_to_local",
    "list_local",
    "delete_local",
    "get_local_usage",
    "get_local_storage_dir",
    "save_to_gdrive",
    "list_gdrive",
    "delete_from_gdrive",
    "gdrive_status",
    "save_to_onedrive",
    "list_onedrive",
    "delete_from_onedrive",
    "onedrive_status",
    "LOCAL_STORAGE_PATH",
    "GDRIVE_MOUNT_PATH",
    "ONEDRIVE_MOUNT_PATH",
]
