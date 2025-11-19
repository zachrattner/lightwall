import os
import json
import time
from logger import info

# Mock Radar Data (Since we are on Linux/without hardware)
# In the real version, this would read from serial_util.py
def get_mock_distance():
    # Simulate a user walking closer over time
    seconds = int(time.time()) % 30
    if seconds < 10:
        return 5.0  # Far away
    elif seconds < 20:
        return 2.0  # Middle
    else:
        return 0.5  # Close

def get_personality_cfg(distance):
    """
    Returns the Python dict for the correct personality based on distance.
    """
    if distance < 1.0:
        name = "sassy"
    elif distance > 3.0:
        name = "poetic"
    else:
        name = "standard"
    
    filepath = os.path.join("personalities", f"{name}.json")
    
    try:
        with open(filepath, "r") as f:
            cfg = json.load(f)
            cfg["name"] = name # Inject name for logging
            return cfg
    except Exception as e:
        info(f"Error loading {name}: {e}")
        # Fallback to standard if file fails
        with open("personalities/standard.json", "r") as f:
            return json.load(f)
