#!/usr/bin/env zsh
set -euo pipefail

echo "[setup-env] Starting setup in zsh..."
echo "[setup-env] Current shell: $SHELL"
echo "[setup-env] Script: $0"

if [[ -f ".env" ]]; then
  echo "[setup-env] Loading .env file..."
else
  echo "[setup-env] Warning: .env file not found, continuing without it."
fi

source .env

if [[ ! -d "./lightwall" ]]; then
  echo "[setup-env] Virtualenv 'lightwall' not found. Creating with python3.11..."
  python3.11 -m venv ./lightwall
  echo "[setup-env] Virtualenv 'lightwall' created."
else
  echo "[setup-env] Virtualenv 'lightwall' already exists. Skipping creation."
fi

echo "[setup-env] Activating virtualenv 'lightwall'..."
# Activate venv
source ./lightwall/bin/activate

# Upgrade pip
echo "[setup-env] Upgrading pip..."
pip install --upgrade pip
echo "[setup-env] pip upgrade complete."

# Install requirements
if [[ -f "requirements.txt" ]]; then
  echo "[setup-env] Installing requirements from requirements.txt..."
  pip install -r requirements.txt
  echo "[setup-env] Requirements installation complete."
else
  echo "[setup-env] Warning: requirements.txt not found, skipping package installation."
fi

echo "[setup-env] Done. Virtual environment 'lightwall' is ready."