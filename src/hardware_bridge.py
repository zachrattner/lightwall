import re
from logger import info

# This function finds the tags like [LIGHTS:RED]
def extract_hardware_commands(text):
    """
    Separates the spoken text from the hardware commands.
    Returns: (clean_text, command)
    """
    # Regex to find [LIGHTS:...]
    match = re.search(r'\[LIGHTS:([A-Z]+)\]', text)
    
    if match:
        command = match.group(1) # e.g., "RED"
        # Remove the tag from the text so the voice doesn't say "Bracket Lights Red Bracket"
        clean_text = re.sub(r'\[LIGHTS:[A-Z]+\]', '', text).strip()
        return clean_text, command
    
    return text, None

def send_light_command(color):
    """
    On Mac: Sends Serial command to Arduino.
    On Linux: Prints visual simulation.
    """
    # Map colors to emojis for Linux Visualization
    emoji_map = {
        "RED": "🔴🔴🔴 RED LIGHTS 🔴🔴🔴",
        "PURPLE": "🟣🟣🟣 PURPLE LIGHTS 🟣🟣🟣",
        "CYAN": "🔵🔵🔵 CYAN LIGHTS 🔵🔵🔵",
        "WHITE": "⚪⚪⚪ WHITE LIGHTS ⚪⚪⚪",
        "OFF": "⚫⚫⚫ LIGHTS OFF ⚫⚫⚫",
        "FADE": "🌫️🌫️🌫️ FADING 🌫️🌫️🌫️"
    }
    
    visual = emoji_map.get(color, f"UNKNOWN COLOR: {color}")
    info(f"[HARDWARE CONTROL] {visual}")

