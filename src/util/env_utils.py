import os
import json
from util.logger import warning

def load_env_file(path: str = ".env"):
    if not os.path.exists(path):
        return
    try:
        with open(path, 'r') as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith('#') or '=' not in s:
                    continue
                k, v = s.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())
    except Exception as e:
        warning(f"Failed to load {path}: {e}")

def load_personality(name: str):
    """Load personalities/<name>.json and validate required fields."""
    path = os.path.join("personalities", f"{name}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Personality file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    for k in ("voice", "speed", "systemPrompt"):
        if k not in cfg:
            raise KeyError(f"Personality '{name}' missing required key: {k}")
    return cfg