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

if [[ ! -d "./laserwall" ]]; then
  python3.11 -m venv ./laserwall
fi

# Activate venv
source ./laserwall/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install requirements
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
else
  echo "requirements.txt not found"
fi

echo "Virtual environment 'laserwall' created and requirements installed."