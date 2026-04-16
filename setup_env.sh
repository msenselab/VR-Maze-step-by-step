#!/usr/bin/env bash
# Setup virtual environment on macOS/Linux

set -e

if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "Creating virtual environment..."
uv venv .venv

echo "Installing dependencies..."
uv pip install --python .venv/bin/python -r requirements.txt

echo ""
echo "Done! Activate with:  source .venv/bin/activate"
