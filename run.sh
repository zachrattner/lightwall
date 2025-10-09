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

# Activate virtual environment
source laserwall/bin/activate

echo "Starting the LLM server in the background..."
./run-llm-server.sh > /dev/null 2>&1 &

# Run main.py
python src/main.py "$@"