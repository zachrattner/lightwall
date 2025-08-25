#!/bin/zsh
set -euo pipefail

source .env

function command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if Ollama is installed
if ! command_exists ollama; then
    echo "Ollama is not installed on this system."
    echo "Please download and install Ollama from: https://ollama.ai"
    echo "Once installed, re-run this script."
    exit 1
fi

echo "Downloading ${BASE_MODEL}..."
ollama pull "${BASE_MODEL}"

echo "Done!"
