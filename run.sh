#!/usr/bin/env zsh
set -euo pipefail

source .env

# Activate virtual environment
source laserwall/bin/activate

echo "Starting the LLM server in the background..."
./run-llm-server.sh > /dev/null 2>&1 &

# Run main.py
python src/main.py "$@"