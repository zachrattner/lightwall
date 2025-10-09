#!/usr/bin/env bash
set -euo pipefail

# Priority to Zsh - re-execute in zsh if available and not already running in zsh
if [ -z "${ZSH_VERSION:-}" ] && command -v zsh >/dev/null 2>&1; then
  exec zsh "$0" "$@"
elif [ -z "${BASH_VERSION:-}" ] && command -v bash >/dev/null 2>&1; then
  exec bash "$0" "$@"
elif [ -z "${BASH_VERSION:-}" ] && [ -z "${ZSH_VERSION:-}" ]; then
  echo "Error: neither bash nor zsh found on this system."
  exit 1
fi

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
