#!/bin/bash
# Orion LLM Launcher
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate virtual environment
if [ -f "$SCRIPT_DIR/llm-env/bin/activate" ]; then
    source "$SCRIPT_DIR/llm-env/bin/activate"
elif [ -f ~/llm-env/bin/activate ]; then
    source ~/llm-env/bin/activate
elif [ -f ~/orion-llm/llm-env/bin/activate ]; then
    source ~/orion-llm/llm-env/bin/activate
fi

# Set model path and port defaults if not set
export MODEL_PATH="${MODEL_PATH:-$HOME/models/qwen2.5-0.5b-instruct-q4_k_m.gguf}"
export PORT="${PORT:-8000}"
export MODEL_NAME="${MODEL_NAME:-Qwen2.5-0.5B-Instruct}"

# Ensure storage mounts (SD Card & OneDrive daemon) are live
bash "$SCRIPT_DIR/mount_drives.sh" 2>/dev/null || true

# Run interactive Orion Agent CLI
python3 "$SCRIPT_DIR/ui_cli.py"
