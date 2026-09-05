#!/bin/bash
# mount_drives.sh
# Orion LLM Mount Helper Script
# Ensures 16GB SD card and OneDrive rclone FUSE mounts are initialized in daemon mode.

SDCARD_MOUNT="/mnt/sdcard"
ONEDRIVE_MOUNT="/mnt/onedrive"
ONEDRIVE_REMOTE="onedrive:"

echo "=== Orion Drive Mount Initialization ==="

# 1. Mount 16GB SD Card if not mounted
if ! mountpoint -q "$SDCARD_MOUNT"; then
    echo "Attempting to mount 16GB SD card at $SDCARD_MOUNT..."
    sudo mkdir -p "$SDCARD_MOUNT"
    
    # Try mounting from fstab or candidate block devices (Pi 5 SD card slot is /dev/mmcblk0p1 or /dev/mmcblk0)
    if sudo mount "$SDCARD_MOUNT" 2>/dev/null; then
        echo "✓ SD card mounted successfully via fstab."
    elif [ -b "/dev/mmcblk0p1" ]; then
        sudo mount /dev/mmcblk0p1 "$SDCARD_MOUNT" && echo "✓ Mounted /dev/mmcblk0p1 at $SDCARD_MOUNT"
    elif [ -b "/dev/mmcblk0" ]; then
        sudo mount /dev/mmcblk0 "$SDCARD_MOUNT" && echo "✓ Mounted /dev/mmcblk0 at $SDCARD_MOUNT"
    elif [ -b "/dev/mmcblk1p1" ]; then
        sudo mount /dev/mmcblk1p1 "$SDCARD_MOUNT" && echo "✓ Mounted /dev/mmcblk1p1 at $SDCARD_MOUNT"
    elif [ -b "/dev/sdb1" ]; then
        sudo mount /dev/sdb1 "$SDCARD_MOUNT" && echo "✓ Mounted /dev/sdb1 at $SDCARD_MOUNT"
    elif [ -b "/dev/sda1" ]; then
        sudo mount /dev/sda1 "$SDCARD_MOUNT" && echo "✓ Mounted /dev/sda1 at $SDCARD_MOUNT"
    else
        echo "ℹ No dedicated SD card device found mounted. Local storage will fall back to active mount path."
    fi
else
    echo "✓ SD card already mounted at $SDCARD_MOUNT"
fi

# 2. Mount OneDrive via rclone daemon if not mounted
if ! mountpoint -q "$ONEDRIVE_MOUNT"; then
    if command -v rclone &> /dev/null; then
        echo "Attempting to mount OneDrive remote ($ONEDRIVE_REMOTE) at $ONEDRIVE_MOUNT in daemon mode..."
        mkdir -p "$ONEDRIVE_MOUNT"
        rclone mount "$ONEDRIVE_REMOTE" "$ONEDRIVE_MOUNT" --vfs-cache-mode writes --daemon
        sleep 1
        if mountpoint -q "$ONEDRIVE_MOUNT"; then
            echo "✓ OneDrive mounted successfully in daemon mode."
        else
            echo "⚠ Could not mount OneDrive. Check 'rclone config' for remote '$ONEDRIVE_REMOTE'."
        fi
    else
        echo "⚠ rclone command not found. Install rclone to enable OneDrive mount."
    fi
else
    echo "✓ OneDrive already mounted at $ONEDRIVE_MOUNT"
fi

echo "=== Mount Status Check Complete ==="
