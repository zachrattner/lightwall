import sounddevice as sd
import numpy as np
import torch
import time
import argparse
from silero_vad import load_silero_vad, get_speech_timestamps
from utils import load_env_file, load_personality
from ollama import query_ollama
from say import say
from logger import info, warning, error
from whisper import transcribe
from audio_constants import SAMPLE_RATE, BUFFER_SIZE, VAD_MIN_SPEECH_MS, VAD_THRESHOLD, VAD_MIN_SILENCE_MS, RMS_GATE
from music import start_playing, stop_playing

# Load Silero VAD model
model = load_silero_vad()

personality_name = "robot"
personality_cfg = {}

in_speech = False
current_utt = np.array([], dtype=np.float32)

chat_messages = []

def postprocess_transcript(text: str):
    if text:
        info(f"transcript: {text}")
        try:
            if personality_cfg:
                chat_messages.append({"role": "user", "content": text})
                response = query_ollama(chat_messages)
                if response:
                    stop_playing()
                    info(f"response: {response}")
                    say(response, personality_cfg)
                    chat_messages.append({"role": "assistant", "content": response})
        except Exception as e:
            error(f"post-transcribe action failed: {e}")
    else:
        warning("TRANSCRIPT: [empty]")

def audio_callback(indata, frames, time_info, status):
    global in_speech, current_utt
    if status:
        info(f"Audio callback status: {status}")

    # Mono float32
    audio = indata.mean(axis=1) if indata.ndim > 1 else indata
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32, copy=False)

    # VAD path
    rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0
    audio_tensor = torch.from_numpy((audio * 32768).astype(np.int16))

    if RMS_GATE > 0.0 and rms < RMS_GATE:
        speech_timestamps = []
    else:
        # Use padding from config
        from audio_constants import SPEECH_PADDING_MS
        speech_timestamps = get_speech_timestamps(
            audio_tensor,
            model,
            return_seconds=True,
            threshold=VAD_THRESHOLD,
            min_speech_duration_ms=VAD_MIN_SPEECH_MS,
            min_silence_duration_ms=VAD_MIN_SILENCE_MS,
            speech_pad_ms=SPEECH_PADDING_MS,
        )

    speech_detected = len(speech_timestamps) > 0

    # Accumulate during speech
    if in_speech:
        current_utt = np.concatenate((current_utt, audio)) if current_utt.size else audio.copy()

    # Transitions: immediate start/end based on VAD
    if speech_detected:
        if not in_speech:
            in_speech = True
            info("speech started")
            current_utt = np.array([], dtype=np.float32)
        # when speech is detected, accumulate the current audio chunk
        current_utt = np.concatenate((current_utt, audio)) if current_utt.size else audio.copy()
    else:
        if in_speech:
            in_speech = False
            info("speech ended")
            utt = current_utt if current_utt.size else np.array([], dtype=np.float32)
            if utt.size > 0:
                start_playing()
                transcript = transcribe(utt)
                postprocess_transcript(transcript)
            else:
                warning("TRANSCRIPT: [no audio]")
            current_utt = np.array([], dtype=np.float32)

def parse_args():
    parser = argparse.ArgumentParser(description='Silero VAD mic monitor')
    parser.add_argument('--list-devices', action='store_true', help='List audio devices and exit')
    parser.add_argument('--device', type=int, default=None, help='Input device id to use')
    parser.add_argument('--personality', type=str, default=None, help='Personality name (JSON in personalities/<name>.json). Defaults to robot if not set.')
    return parser.parse_args()

def main():
    args = parse_args()

    info("loading env file")
    load_env_file()
    global personality_name, personality_cfg, chat_messages
    personality_name = args.personality if args.personality else "robot"
    try:
      info("loading personality")
      personality_cfg = load_personality(personality_name)
    except Exception as e:
      error(f"Failed to load personality {personality_name}: {e}")
      return

    info("selecting mic input device")
    if args.list_devices:
        devices = sd.query_devices()
        for idx, dev in enumerate(devices):
            info(f"{idx}: in_ch={dev['max_input_channels']} out_ch={dev['max_output_channels']} - {dev['name']}")
        return

    device_kw = {}
    if args.device is not None:
        device_kw['device'] = args.device

    # Initialize ollama
    info("initializing ollama")
    system_prompt = personality_cfg.get("systemPrompt", "")
    chat_messages = [
        {"role": "system", "content": system_prompt},
    ]
    query_ollama(chat_messages)

    info("Listening for speech... Press Ctrl+C to stop.")
    try:
        with sd.InputStream(channels=1, samplerate=SAMPLE_RATE, blocksize=BUFFER_SIZE, callback=audio_callback, dtype='float32', **device_kw):
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()