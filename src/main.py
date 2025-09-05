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

# Trailing-silence tuning (Idea 1): require longer quiet to end an utterance
# Use at least 800 ms or the configured value, whichever is larger.
from music import start_playing, stop_playing

# Load Silero VAD model
model = load_silero_vad()

personality_name = "robot"
personality_cfg = {}

in_speech = False
current_utt = np.array([], dtype=np.float32)

chat_messages = []

# Adaptive RMS gate config and state (idea 5)
ADAPTIVE_RMS_ALPHA = 0.05        # EMA smoothing factor for baseline
ADAPTIVE_GATE_MULTIPLIER = 3.0   # dynamic gate = baseline * multiplier
ADAPTIVE_MIN_GATE = 0.001        # absolute floor on gate

rms_baseline = None              # updated during detected silence
quiet_until_ts = 0.0             # cooldown window after TTS completes

# Debounced end-of-speech: require continued silence before finalizing
END_SILENCE_CONFIRM_SEC = 1.0
pending_end_ts = None  # None means no pending end; otherwise holds candidate end timestamp

# Ignore very short utterances (don’t transcribe or play music)
MIN_UTTERANCE_SEC = 0.50  # 500 ms

def update_rms_baseline(rms: float):
    """Update EMA baseline with the current RMS value."""
    global rms_baseline
    if not np.isfinite(rms):
        return
    if rms_baseline is None:
        rms_baseline = rms
    else:
        rms_baseline = (1.0 - ADAPTIVE_RMS_ALPHA) * rms_baseline + ADAPTIVE_RMS_ALPHA * rms


def current_rms_gate() -> float:
    """Return the effective RMS gate combining static and adaptive thresholds."""
    base_gate = RMS_GATE if RMS_GATE > 0.0 else 0.0
    dynamic = (rms_baseline or 0.0) * ADAPTIVE_GATE_MULTIPLIER
    return max(ADAPTIVE_MIN_GATE, base_gate, dynamic)

def postprocess_transcript(text: str):
    global quiet_until_ts
    if text:
        info(f"transcript: {text}")
        # Ignore placeholder/marker transcripts (e.g., music or empty markers)
        _marker = text.strip().lower()
        if _marker in {"*music*", "(empty)", "[empty]"}:
            warning(f'TRANSCRIPT: [ignored placeholder "{_marker}"]')
            return
        try:
            if personality_cfg:
                chat_messages.append({"role": "user", "content": text})
                response = query_ollama(chat_messages)
                if response:
                    stop_playing()
                    info(f"response: {response}")
                    try:
                        # Speak the reply; this call is assumed to be blocking
                        say(response, personality_cfg)
                    finally:
                        # After TTS ends, enter a short quiet window to recalibrate baseline
                        from time import time as _now
                        quiet_duration = 0.2 # seconds
                        quiet_until_ts = _now() + quiet_duration
                        info(f"Entering adaptive quiet window for {quiet_duration:.1f}s")
                    chat_messages.append({"role": "assistant", "content": response})
        except Exception as e:
            error(f"post-transcribe action failed: {e}")
    else:
        warning("TRANSCRIPT: [empty]")

def audio_callback(indata, frames, time_info, status):
    global in_speech, current_utt, rms_baseline, quiet_until_ts, pending_end_ts
    if status:
        info(f"Audio callback status: {status}")

    # Mono float32
    audio = indata.mean(axis=1) if indata.ndim > 1 else indata
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32, copy=False)

    # VAD path with adaptive RMS gate
    rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0
    now_ts = time.time()

    # Determine effective gate and optionally update baseline
    effective_gate = current_rms_gate()

    # During the post-TTS quiet window, force silence and keep adapting the baseline
    if now_ts < quiet_until_ts:
        update_rms_baseline(rms)
        speech_timestamps = []
    # If energy is below the effective gate, treat as silence and adapt baseline
    elif rms < effective_gate:
        update_rms_baseline(rms)
        speech_timestamps = []
    else:
        # Energy above gate: run VAD on this chunk
        audio_tensor = torch.from_numpy((audio * 32768).astype(np.int16))
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

    #info(f"rms={rms:.6f} gate={effective_gate:.6f} speech={speech_detected}")

    # Transitions: debounced end-of-speech (require sustained silence)
    if speech_detected:
        if not in_speech:
            in_speech = True
            info("speech started")
            current_utt = np.array([], dtype=np.float32)
        # Any detected speech cancels a pending end
        pending_end_ts = None
        # when speech is detected, accumulate the current audio chunk
        current_utt = np.concatenate((current_utt, audio)) if current_utt.size else audio.copy()
    else:
        if in_speech:
            if pending_end_ts is None:
                # First silent frame after speech: start the end confirmation timer
                pending_end_ts = now_ts
            else:
                # If we have stayed silent long enough, finalize the utterance
                if (now_ts - pending_end_ts) >= END_SILENCE_CONFIRM_SEC:
                    in_speech = False
                    pending_end_ts = None
                    info("speech ended")
                    utt = current_utt if current_utt.size else np.array([], dtype=np.float32)
                    if utt.size > 0:
                        utt_dur_sec = float(utt.size) / float(SAMPLE_RATE)
                        if utt_dur_sec < MIN_UTTERANCE_SEC:
                            warning(f"TRANSCRIPT: [ignored short utterance {utt_dur_sec*1000:.0f} ms]")
                        else:
                            start_playing()
                            transcript = transcribe(utt)
                            postprocess_transcript(transcript)
                    else:
                        warning("TRANSCRIPT: [no audio]")
                    current_utt = np.array([], dtype=np.float32)
        # If we're already not in_speech, do nothing

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