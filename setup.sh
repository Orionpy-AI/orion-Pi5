#!/bin/bash
# setup.sh
# Orion LLM setup script for Raspberry Pi & Linux
# Installs dependencies, sets up virtualenv, and configures Docker/Compose.

set -e

echo "=== Orion LLM Setup ==="

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "Python3 is not installed. Installing..."
    sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv build-essential cmake git
fi

# Create virtual environment if not existing
if [ ! -d "llm-env" ]; then
    echo "Creating virtual environment 'llm-env'..."
    python3 -m venv llm-env
fi

echo "Activating virtual environment..."
source llm-env/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Making scripts executable..."
chmod +x chat.sh ui_cli.py

echo ""
echo "=== Orion LLM Ready! ==="
echo "Run standalone chat: ./chat.sh"
echo "Or with python directly: python3 ui_cli.py"
echo ""
