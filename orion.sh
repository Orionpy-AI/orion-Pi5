#!/bin/bash
# orion.sh — Orion interactive launcher script
# -----------------------------------------------------------------------------
# UPLOAD COMMAND (Run directly from Windows PowerShell / Command Prompt to update Pi):
#   scp -r C:\Users\Admin\Documents\Pi\orion-llm\* rpi@192.168.109.178:/home/rpi/orion-llm/
#   (or just double-click upload_to_pi.bat, which excludes models/, __pycache__, .git)
# -----------------------------------------------------------------------------

set -e  # stop the script if any command fails

# ---- CONFIGURATION --------------------------------------------------------
PI_USER="rpi"
PI_HOST="192.168.109.178"
PI_DEST="/home/rpi/orion-llm"

PROJECT_DIR="$HOME/orion-llm"                # dir to cd into (on the Pi)
VENV_DIR="$PROJECT_DIR/llm-env"              # path to your virtualenv
PYTHON_SCRIPT="ui_cli.py"
# ---------------------------------------------------------------------------

# Check if script was invoked with --upload / -u flag
if [ "$1" == "--upload" ] || [ "$1" == "-u" ]; then
    echo "==> Pushing codebase from Windows to Raspberry Pi 5 ($PI_USER@$PI_HOST:$PI_DEST)..."
    scp -r ./* "${PI_USER}@${PI_HOST}:${PI_DEST}/"
    echo "==> Upload complete!"
    exit 0
fi

echo "==> Moving into project directory: $PROJECT_DIR"
cd "$PROJECT_DIR"

echo "==> Ensuring drive mounts (SD Card & OneDrive daemon)..."
bash "$PROJECT_DIR/mount_drives.sh" 2>/dev/null || true

echo "==> Activating virtual environment..."
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
fi

echo "==> Running Orion interactive agent: $PYTHON_SCRIPT"
python3 "$PYTHON_SCRIPT"

echo "==> Done."