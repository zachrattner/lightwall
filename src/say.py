import sys
import os
import platform
import subprocess

# We add 'config=None' to handle the extra data main.py sends
def say(text, config=None):
    # Detect the Operating System
    system_os = platform.system()

    # 1. If we are on Mac (The Art Installation)
    if system_os == "Darwin":
        # Use the built-in Mac TTS
        # You might want to use config['voice'] here in the future
        subprocess.run(["say", text])

    # 2. If we are on Linux (Your Dev Machine)
    else:
        # Just print it nicely to the console
        # We also print the voice name just so you see it works
        voice_name = config.get('voice', 'Default') if config else 'Default'
        print(f"\n[🤖 AUDIO OUTPUT ({voice_name})]: {text}\n")

if __name__ == "__main__":
    # This allows you to run: python3 src/say.py "Hello world"
    if len(sys.argv) > 1:
        say(sys.argv[1])
