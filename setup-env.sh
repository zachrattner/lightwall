#!/usr/bin/env zsh
set -euo pipefail

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