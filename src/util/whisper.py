import numpy as np
from util.audio_utils import pcm16le_bytes
from util.logger import warning, error
import wave
import os
import subprocess
from util.audio_constants import SAMPLE_RATE, MIN_UTTERANCE_DURATION_MS

def transcribe(utt: np.ndarray):
    global chat_messages
    """Write utterance to current-utterance.wav (PCM16LE), call whisper-cli once, and return the transcript."""
    # Ensure float32 mono in [-1,1]
    if utt.dtype != np.float32:
        utt = utt.astype(np.float32, copy=False)
    np.clip(utt, -1.0, 1.0, out=utt)

    # Ignore very short utterances (<5s)
    duration_msec = 1000 * (utt.size / SAMPLE_RATE)
    if duration_msec < MIN_UTTERANCE_DURATION_MS:
        warning(f"Ignored short utterance ({duration_msec} ms)")
        return

    out_wav = "current-utterance.wav"
    # Write PCM16LE WAV
    with wave.open(out_wav, 'wb') as ww:
        ww.setnchannels(1)
        ww.setsampwidth(2)
        ww.setframerate(SAMPLE_RATE)
        ww.setcomptype('NONE', 'not compressed')
        ww.writeframes(pcm16le_bytes(utt))

    # Call whisper-cli once
    model_key = os.environ.get('SPEECH_RECOGNITION_MODEL', 'large-v3-turbo')
    model_path = f"./whisper.cpp/models/ggml-{model_key}.bin"
    cli = "./whisper.cpp/build/bin/whisper-cli"
    cmd = [cli, '-m', model_path, out_wav, '--output-txt']
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        error("whisper-cli not found at ./whisper.cpp/build/bin/whisper-cli")
        return
    except subprocess.CalledProcessError as e:
        error(f"whisper-cli failed with code {e.returncode}")
        return

    # Read transcript from generated TXT
    txt_path = out_wav + '.txt'
    text = ''
    try:
        with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read().strip().replace('\n', ' ')
    except Exception as e:
        warning(f"Could not read transcript: {e}")
        return

    return text