import subprocess
from logger import warning

def say(text: str, config: dict):
    voice = str(config.get("voice", "Fred"))
    speed = int(config.get("speed", 150))
    try:
        subprocess.run(["say", "-v", voice, "-r", str(speed), text], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        warning(f"say failed: {e}")