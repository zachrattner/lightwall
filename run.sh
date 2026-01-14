#!/usr/bin/env zsh
set -euo pipefail

if [[ -f ".env" ]]; then
  echo "[run] Loading .env file..."
else
  echo "[run] Warning: .env file not found, continuing without it."
fi

source .env

if [[ ! -d "./lightwall" ]]; then
    echo "No virtual environment, cannot continue. Setup via setup-env.sh"
    exit 1
fi

say "Hi there! I just woke up. I need about 45 seconds to calibrate my lights and motors."

echo "[run] Activating virtualenv 'lightwall'..."
source ./lightwall/bin/activate

# Ollama v0.13.3 has abug that breaks Gemma models
# So force overwrite to v0.13.2 when zip is found
# Bug: https://github.com/ollama/ollama/issues/13444 
OLLAMA_ZIP="$HOME/Desktop/Ollama-darwin.zip"
if [[ -f "$OLLAMA_ZIP" ]]; then
  echo "[run] Found $OLLAMA_ZIP, installing Ollama..."

  echo "[run] Unzipping Ollama..."
  if ! unzip -oq "$OLLAMA_ZIP" -d "$HOME/Desktop"; then
    echo "[run] Warning: unzip failed, continuing anyway."
  fi

  echo "[run] Removing existing /Applications/Ollama.app (if any)..."
  if ! rm -rf "/Applications/Ollama.app"; then
    echo "[run] Warning: failed to remove /Applications/Ollama.app, continuing anyway."
  fi

  if [[ -d "$HOME/Desktop/Ollama.app" ]]; then
    echo "[run] Moving $HOME/Desktop/Ollama.app into /Applications..."
    if ! mv "$HOME/Desktop/Ollama.app" "/Applications/"; then
      echo "[run] Warning: mv into /Applications failed, trying with sudo..."
      if ! sudo mv "$HOME/Desktop/Ollama.app" "/Applications/"; then
        echo "[run] Error: failed to move Ollama.app into /Applications, continuing anyway."
      fi
    fi
  else
    echo "[run] Warning: expected $HOME/Desktop/Ollama.app after unzip, but it was not found. Continuing anyway."
  fi

  # Start LLM server only if Ollama is not already running
  if pgrep -f "ollama" > /dev/null 2>&1; then
    echo "[run] Ollama already running, skipping LLM server startup."
  else
    echo "Starting the LLM server in the background..."
    ./run-llm-server.sh > /dev/null 2>&1 &
  fi

  sleep 5

  if pgrep -f "ollama" > /dev/null 2>&1; then
    echo "[run] Ollama is running now!"
  else
    echo "Failed to run Ollama after trying!"
  fi  

  echo "[run] Checking ollama CLI version..."
  if command -v ollama >/dev/null 2>&1; then
    OLLAMA_VERSION_OUTPUT="$(ollama --version 2>/dev/null || true)"
    if [[ "$OLLAMA_VERSION_OUTPUT" != *"0.13.2"* ]]; then
      echo "[run] Error: expected ollama version 0.13.2, got: $OLLAMA_VERSION_OUTPUT"
    else
      echo "[run] Ollama version OK: $OLLAMA_VERSION_OUTPUT"
    fi
  else
    echo "[run] Error: 'ollama' CLI not found in PATH. Continuing anyway."
  fi
else
  echo "[run] No $OLLAMA_ZIP found, skipping Ollama install steps."
fi


echo "[run] Setting system audio levels"
osascript -e "set volume input volume 75"
osascript -e "set volume output volume 100"

python src/main.py "$@"
