import os
import numpy as np
import json
from logger import warning

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

def pcm16le_bytes(x: np.ndarray) -> bytes:
    """Convert float32 mono [-1,1] to PCM16LE bytes with clipping."""
    if x.dtype != np.float32:
        x = x.astype(np.float32, copy=False)
    # clip to [-1, 1]
    np.clip(x, -1.0, 1.0, out=x)
    # scale and cast to little-endian int16 explicitly
    i16 = (x * 32767.0).astype('<i2', copy=False)  # '<i2' = little-endian int16
    return i16.tobytes()

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