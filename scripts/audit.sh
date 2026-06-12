#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "=== 🏴‍☠️ Thatch Code Audit ==="

# Check if ruff is installed globally or in venv
if [ -f "venv/bin/activate" ]; then
    echo "[*] Activating virtual environment..."
    source venv/bin/activate
fi

if ! command -v ruff &> /dev/null
then
    echo "[!] Ruff no está instalado."
    echo "    Instalándolo en tu entorno..."
    pip install ruff || { echo "Usa: sudo pacman -S ruff o pipx install ruff"; exit 1; }
fi

echo "[*] Running Ruff Linter (fixing safe errors and removing unused imports)..."
ruff check . --fix

echo "[*] Running Ruff Formatter (standardizing code style)..."
ruff format .

echo "=== ✅ Audit completed successfully! ==="
