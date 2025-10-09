import torchaudio as ta
import torch
from chatterbox.tts import ChatterboxTTS
import os

# Automatically detect the best available device
if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available():
    device = "mps"
else:
    device = "cpu"

print(f"Using device: {device}")

model = ChatterboxTTS.from_pretrained(device=device)

text = "You Either Die a Hero, or You Live Long Enough To See Yourself Become the Villain."

audio_prompt_path = None    # generate audio based on a specific audio clip if needed
exaggeration: float = 0.5
cfg_weight: float = 0.5
temperature: float = 0.8

wav = model.generate(
    text,
    audio_prompt_path=audio_prompt_path,
    exaggeration=exaggeration,
    cfg_weight=cfg_weight,
    temperature=temperature
)

# Create output directory in root directory
output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
os.makedirs(output_dir, exist_ok=True)

# Generate audio filename based on parameters
filename = f"audio_{audio_prompt_path}_ex_{exaggeration}_cfg_{cfg_weight}_temp_{temperature}.wav"
output_path = os.path.join(output_dir, filename)

# Save model to output directory
ta.save(output_path, wav, model.sr)