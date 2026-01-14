import threading
import time
import random
import os
import subprocess
import re
from typing import Optional

import numpy as np
import sounddevice as sd
import torch

from silero_vad import load_silero_vad, get_speech_timestamps

from util.logger import info, warning, error
from hw.hw_state import HWState
from hw.led.led_controller import LEDController
from hw.motor.motor_controller import MotorController
from hw.idle_sequence import IdleSequence
from hw.approaching_sequence import ApproachingSequence
from hw.engaged_sequence import EngagedSequence
from hw.leaving_sequence import LeavingSequence
from hw.speaker import Speaker
from util.env_utils import load_personality
from util.whisper import transcribe
from util.ollama import query_ollama
from util.audio_constants import SAMPLE_RATE, RMS_GATE, BUFFER_SIZE, VAD_MIN_SPEECH_MS, VAD_THRESHOLD, VAD_MIN_SILENCE_MS, SPEECH_PADDING_MS
#
# Adaptive RMS gate config and state (idea from original VAD-based version)
ADAPTIVE_RMS_ALPHA = 0.05        # EMA smoothing factor for baseline
ADAPTIVE_GATE_MULTIPLIER = 3.0   # dynamic gate = baseline * multiplier
ADAPTIVE_MIN_GATE = 0.001        # absolute floor on gate

# Debounced end-of-speech parameters
END_SILENCE_CONFIRM_SEC = 1.0

# How long we bias toward assuming a visitor is still present
# after the last good distance reading (in seconds).
EXIT_GRACE_SEC = 2.0

# Ignore very short utterances (do not transcribe or play music)
MIN_UTTERANCE_SEC = 0.60  # 600 ms (keeps sub-0.6s clips away from Whisper's short-utterance guard)
class EngagementController:
    """High level controller that drives HWState based on radar distance.
    """

    def __init__(
        self,
        hw_state: HWState,
        led_controller: LEDController,
        motor_controller: MotorController,
        poll_interval: float = 0.1,
        idle_threshold_mm: int = 3000,
        engaged_threshold_mm: int = 1500,
    ) -> None:
        self.hw_state = hw_state
        self.led_controller = led_controller
        self.motor_controller = motor_controller
        self.poll_interval = poll_interval
        self.idle_threshold_mm = idle_threshold_mm
        self.engaged_threshold_mm = engaged_threshold_mm

        # Timestamp of the last confirmed presence reading (in seconds since epoch)
        self._last_presence_ts: float = 0.0

        self.idle_sequence = IdleSequence(
            led_controller=self.led_controller,
            motor_controller=self.motor_controller,
        )

        self.approaching_sequence = ApproachingSequence(
            led_controller=self.led_controller,
            motor_controller=self.motor_controller,
        )

        self.engaged_sequence = EngagedSequence(
            led_controller=self.led_controller,
            motor_controller=self.motor_controller,
        )

        self.leaving_sequence = LeavingSequence(
            led_controller=self.led_controller,
            motor_controller=self.motor_controller,
        )

        self.speaker = Speaker()
        self._is_speaking = False
        self._last_assistant_reply: Optional[str] = None
        self._last_spoke_at: float | None = None
        self._speaking_until: float | None = None

        # Silero VAD model and streaming state
        self._vad_model = load_silero_vad()
        self._in_speech: bool = False
        self._current_utt: np.ndarray = np.array([], dtype=np.float32)

        # Adaptive RMS baseline and quiet window after TTS
        self._rms_baseline: Optional[float] = None
        self._quiet_until_ts: float = 0.0
        self._pending_end_ts: Optional[float] = None

        # Speech rate used for TTS, default to 80 until conversation loop sets it
        self._speech_rate: int = 80

        # Core control-loop events / threads
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Conversation-loop events / threads
        self._conversation_stop_event = threading.Event()
        self._conversation_thread: Optional[threading.Thread] = None

        # Load environment and personality config for the conversational brain
        personality_name = os.getenv("LIGHTWALL_PERSONALITY", "lightwall")
        try:
            self._personality_cfg = load_personality(personality_name)
            system_prompt = self._personality_cfg.get("systemPrompt", "")
            info(f"Loaded personality '{personality_name}' for engagement controller.")
        except Exception as e:
            warning(f"Failed to load personality '{personality_name}': {e}")
            self._personality_cfg = {}
            system_prompt = ""
        self._system_prompt = system_prompt

        # Audio directory for thinking audio tracks
        self._audio_directory = os.getenv("AUDIO_DIRECTORY", "")

        # Chat history shared with the LLM
        self._chat_messages: list[dict] = []
        self._reset_chat_history()

    def _estimate_speech_duration(self, text: str, rate: int) -> float:
        """Estimate how long text-to-speech will take, in seconds.

        macOS 'say' uses 'rate' as words per minute, so we approximate
        duration as 60 * words / rate, with a small safety margin.
        """
        try:
            words = max(1, len(text.split()))
            wpm = max(60, rate)  # avoid absurdly low values
            base = 60.0 * words / float(wpm)
            return base * 1.2  # 20 percent margin
        except Exception:
            # Fallback to a conservative default
            return 3.0

    def _speak(self, text: str, rate: int) -> None:
        """Speak text while marking that the system is currently speaking.

        This flag is used by the conversation loop to avoid listening
        while the robot is talking, which helps prevent feedback loops.
        """
        self._is_speaking = True
        self._last_spoke_at = time.time()
        try:
            self.speaker.say(text=text, rate=rate)
        except Exception as e:
            error(f"Error while speaking: {e}")
        finally:
            self._is_speaking = False

    def _update_rms_baseline(self, rms: float) -> None:
        """Update EMA baseline with the current RMS value."""
        if not np.isfinite(rms):
            return
        if self._rms_baseline is None:
            self._rms_baseline = rms
        else:
            self._rms_baseline = (1.0 - ADAPTIVE_RMS_ALPHA) * self._rms_baseline + ADAPTIVE_RMS_ALPHA * rms

    def _current_rms_gate(self) -> float:
        """Return the effective RMS gate combining static and adaptive thresholds."""
        base_gate = RMS_GATE if RMS_GATE > 0.0 else 0.0
        dynamic = (self._rms_baseline or 0.0) * ADAPTIVE_GATE_MULTIPLIER
        return max(ADAPTIVE_MIN_GATE, base_gate, dynamic)

    def _tts_is_active(self) -> bool:
        """Return True if a macOS 'say' process appears to be running.

        This is used to gate VAD so that Lightwall does not listen to its
        own TTS output. If the check fails, we fall back to assuming TTS
        is not active.
        """
        try:
            # pgrep -x 'say' returns 0 if any exact 'say' process exists.
            result = subprocess.run(
                ["pgrep", "-x", "say"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return result.returncode == 0
        except Exception as e:
            warning(f"Conversation: failed to check TTS activity: {e}")
            return False

    def _reset_chat_history(self) -> None:
        """Reset chat history so new visitors do not inherit prior conversations.

        Keeps the current system prompt (personality) but drops all user/assistant
        messages. This should be called whenever a visitor fully leaves and the
        system returns to an idle state.
        """
        self._chat_messages = []
        # Prefer the stored system prompt if available. Fall back to personality cfg.
        system_prompt = getattr(self, "_system_prompt", None)
        if not system_prompt and hasattr(self, "_personality_cfg"):
            system_prompt = self._personality_cfg.get("systemPrompt", "")
        if system_prompt:
            self._chat_messages.append({"role": "system", "content": system_prompt})

    # --------------------------
    # Public lifecycle
    # --------------------------

    def start(self) -> None:
        """Start radar monitoring and engagement loop."""
        if self._thread is not None and self._thread.is_alive():
            return

        # Ensure radar reader is running
        self.hw_state.start_monitoring_radar()

        # Apply LED behavior for the current state (likely IDLE)
        self._apply_led_behavior_for(self.hw_state.get_state(), None)

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

        self.speaker.say("I'm ready to go now")

        info("EngagementController started")

    def stop(self) -> None:
        """Stop the engagement loop and turn off all LEDs."""
        if self._thread is None:
            return

        self._stop_event.set()

        # Stop any active conversation loop
        self._stop_conversation()

        # Turn off all LEDs
        try:
            for addr in self.led_controller.leds.keys():
                try:
                    self.led_controller.set_brightness(addr, 0, 1000)
                except KeyError:
                    continue
        except Exception as e:
            error(f"Failed to turn off LEDs on stop: {e}")

        try:
            if hasattr(self, "idle_sequence") and self.idle_sequence.is_running():
                self.idle_sequence.stop()
            if hasattr(self, "approaching_sequence") and self.approaching_sequence.is_running():
                self.approaching_sequence.stop()
            if hasattr(self, "engaged_sequence") and self.engaged_sequence.is_running():
                self.engaged_sequence.stop()
            if hasattr(self, "leaving_sequence") and self.leaving_sequence.is_running():
                self.leaving_sequence.stop()
        except Exception as e:
            error(f"Failed to stop sequences on stop: {e}")

        # Return all motors to home position on exit
        try:
            for addr in self.motor_controller.motors.keys():
                try:
                    self.motor_controller.move_to(addr, "CW", 0, 1000)
                except Exception as e:
                    error(f"Failed to return motor {addr} to position 0: {e}")
        except Exception as e:
            error(f"Motor reset loop failed: {e}")

        self._thread.join(timeout=1.0)
        self._thread = None
        info("EngagementController stopped and LEDs turned off")

    # --------------------------
    # Core loop
    # --------------------------

    def _loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                radar = self.hw_state.radar_reader
                if radar is None:
                    warning("EngagementController has no radar reader yet")
                    time.sleep(self.poll_interval)
                    continue

                distance = radar.get_distance_mm()
                now_ts = time.time()

                # Any valid reading within the idle_threshold_mm counts as presence
                if distance is not None and distance > 0 and distance <= self.idle_threshold_mm:
                    self._last_presence_ts = now_ts

                prev_state = self.hw_state.get_state()
                new_state = self._determine_state(distance, prev_state, now_ts)

                if new_state != prev_state:
                    self.hw_state.set_state(new_state)
                    self._apply_led_behavior_for(new_state, prev_state)

                time.sleep(self.poll_interval)

        except Exception as e:
            error(f"EngagementController loop crashed: {e}")

    # --------------------------
    # State transition logic
    # --------------------------

    def _determine_state(
        self,
        distance_mm: Optional[int],
        previous_state: str,
        now_ts: float,
    ) -> str:
        """Determine the next state based on distance, current state, and time.

        Rules, using mm units (1m = 1000mm) and a small hysteresis:

          1) If distance is None or not positive, treat as "far" but only
             exit ENGAGED/LEAVING after a grace window.
          2) When in IDLE:
               - 1m < d <= 2m -> APPROACHING
               - d <= 1m      -> ENGAGED (jump directly for resilience)
          3) When in APPROACHING:
               - d < 1m       -> ENGAGED
               - d > 2m       -> IDLE (after grace window)
          4) When in ENGAGED:
               - d > 2m       -> LEAVING (or IDLE if grace expired)
               - 1m < d <= 2m -> LEAVING
               - d <= 1m      -> stay ENGAGED
          5) When in LEAVING:
               - d < 1m       -> ENGAGED
               - d > 2m       -> IDLE (after grace window)
               - 1m < d <= 2m -> stay LEAVING

        This shape is resilient to missed samples and jumps since
        distance and time together always map back into a consistent state
        region, and state corrections follow on the next iteration.
        """
        idle_thresh = self.idle_threshold_mm
        engaged_thresh = self.engaged_threshold_mm

        # Treat missing or invalid readings as "far" for distance purposes.
        # Hysteresis based on _last_presence_ts will decide when to really exit.
        if distance_mm is None or distance_mm <= 0:
            d = idle_thresh + 1
        else:
            d = distance_mm

        # How long since we last clearly saw someone within the idle threshold
        time_since_presence = None
        if self._last_presence_ts > 0.0:
            time_since_presence = now_ts - self._last_presence_ts

        # IDLE
        if previous_state == HWState.IDLE:
            if d > idle_thresh:
                return HWState.IDLE
            if d > engaged_thresh:
                return HWState.APPROACHING
            return HWState.ENGAGED

        # APPROACHING
        if previous_state == HWState.APPROACHING:
            if d > idle_thresh:
                # If we recently saw someone, stay in APPROACHING for a while
                if time_since_presence is not None and time_since_presence < EXIT_GRACE_SEC:
                    return HWState.APPROACHING
                return HWState.IDLE
            if d <= engaged_thresh:
                return HWState.ENGAGED
            return HWState.APPROACHING

        # ENGAGED
        if previous_state == HWState.ENGAGED:
            if d > idle_thresh:
                # If we recently saw someone, assume they are just stepping back.
                # Move to LEAVING instead of immediately going IDLE.
                if time_since_presence is not None and time_since_presence < EXIT_GRACE_SEC:
                    return HWState.LEAVING
                return HWState.IDLE
            if d > engaged_thresh:
                return HWState.LEAVING
            return HWState.ENGAGED

        # LEAVING
        if previous_state == HWState.LEAVING:
            if d > idle_thresh:
                # Bias toward assuming the visitor is still nearby for a short time.
                if time_since_presence is not None and time_since_presence < EXIT_GRACE_SEC:
                    return HWState.LEAVING
                return HWState.IDLE
            if d <= engaged_thresh:
                return HWState.ENGAGED
            return HWState.LEAVING

        # Fallback for unexpected previous_state values
        warning(f"Unknown previous_state '{previous_state}', defaulting to IDLE")
        return HWState.IDLE

    # --------------------------
    # LED behavior
    # --------------------------

    def _apply_led_behavior_for(self, state: str, previous_state: Optional[str] = None) -> None:
        """Run or stop LED sequences based on the current state.

        - In IDLE, run the idle LED sequence.
        - In APPROACHING, run the approaching LED sequence.
        - In ENGAGED, run the engaged LED sequence.
        - In LEAVING, run the leaving LED sequence.
        - In any other state, stop all sequences and turn off LEDs.
        """
        # IDLE: idle on, others off
        if state == HWState.IDLE:
            # If we are returning to idle from ENGAGED or LEAVING, generate a farewell
            if previous_state in (HWState.ENGAGED, HWState.LEAVING):
                farewells = [
                    "Goodbye. Come back soon.",
                    "Thanks for visiting. Travel safely.",
                    "It was good to see you. Don't be a stranger.",
                    "I will be here when you return.",
                    "Thanks for sharing this moment with me. Goodbye.",
                    "Farewell until our paths cross again.",
                    "May your path stay bright.",
                    "I hope to see you again soon.",
                    "Goodbye for now."
                ]
                text = random.choice(farewells)
                self._speak(text=text, rate=80)

            # Reset chat so the next visitor starts fresh
            self._reset_chat_history()

            # Stop non idle sequences if running
            if self.approaching_sequence.is_running():
                info("Entering IDLE. Stopping approaching sequence.")
                self.approaching_sequence.stop()
            if self.engaged_sequence.is_running():
                info("Entering IDLE. Stopping engaged sequence.")
                self.engaged_sequence.stop()
            if self.leaving_sequence.is_running():
                info("Entering IDLE. Stopping leaving sequence.")
                self.leaving_sequence.stop()

            # Stop conversation when returning to IDLE
            self._stop_conversation()

            # Start combined idle sequence when in IDLE
            if not self.idle_sequence.is_running():
                info("Entering IDLE. Starting combined idle sequence.")
                self.idle_sequence.start()
            return

        # APPROACHING: approaching on, others off
        if state == HWState.APPROACHING:
            # Stop idle sequence when leaving IDLE-like behavior
            if self.idle_sequence.is_running():
                info("Entering APPROACHING. Stopping combined idle sequence.")
                self.idle_sequence.stop()

            # Stop other sequences
            if self.engaged_sequence.is_running():
                info("Entering APPROACHING. Stopping engaged sequence.")
                self.engaged_sequence.stop()
            if self.leaving_sequence.is_running():
                info("Entering APPROACHING. Stopping leaving sequence.")
                self.leaving_sequence.stop()

            # Conversation is only active in ENGAGED, ensure it is stopped here
            self._stop_conversation()

            # Start combined approaching sequence when in APPROACHING
            if not self.approaching_sequence.is_running():
                info("Entering APPROACHING. Starting approaching sequence.")
                self.approaching_sequence.start()
            return

        # ENGAGED: run engaged sequence and speak greeting on transition
        if state == HWState.ENGAGED:
            engaged_lines = [
                "Hello there, it is good to see you.",
                "Welcome. I am glad you are here.",
                "Hi there! Thank you for coming.",
                "Hello. It is nice to share this moment with you.",
                "Hi. Your presence brightens me.",
                "Good to see you. Stay as long as you like.",
                "Hello, I am so glad you are here.",
                "Hi! is good to see you.",
                "Hello my friend. I can sense your presence.",
                "Hello. I am glad you came by."
            ]
            text = random.choice(engaged_lines)
            self._speak(text=text, rate=80)

            # Stop idle and other sequences
            if self.idle_sequence.is_running():
                info("Entering ENGAGED. Stopping combined idle sequence.")
                self.idle_sequence.stop()
            if self.approaching_sequence.is_running():
                info("Entering ENGAGED. Stopping approaching sequence.")
                self.approaching_sequence.stop()
            if self.leaving_sequence.is_running():
                info("Entering ENGAGED. Stopping leaving sequence.")
                self.leaving_sequence.stop()

            # Start conversation loop while ENGAGED
            self._start_conversation()

            # Start engaged sequence while ENGAGED
            if not self.engaged_sequence.is_running():
                info("Entering ENGAGED. Starting engaged sequence.")
                self.engaged_sequence.start()
            return

        # LEAVING: run leaving sequence
        if state == HWState.LEAVING:
            # Stop idle and other sequences
            if self.idle_sequence.is_running():
                info("Entering LEAVING. Stopping combined idle sequence.")
                self.idle_sequence.stop()
            if self.approaching_sequence.is_running():
                info("Entering LEAVING. Stopping approaching sequence.")
                self.approaching_sequence.stop()
            if self.engaged_sequence.is_running():
                info("Entering LEAVING. Stopping engaged sequence.")
                self.engaged_sequence.stop()

            # Stop conversation when visitor is leaving
            self._stop_conversation()

            # Start combined leaving sequence while LEAVING
            if not self.leaving_sequence.is_running():
                info("Entering LEAVING. Starting leaving sequence.")
                self.leaving_sequence.start()
            return

        # Any other state: stop all sequences and turn off LEDs
        stopped_any = False
        for name, seq in (
            ("idle", self.idle_sequence),
            ("approaching", self.approaching_sequence),
            ("engaged", self.engaged_sequence),
            ("leaving", self.leaving_sequence),
        ):
            if seq.is_running():
                info(f"Stopping {name} sequence due to state={state}.")
                seq.stop()
                stopped_any = True

        if stopped_any:
            info(f"All sequences stopped due to unknown state={state}. Turning LEDs off.")
            # Also stop any conversation loop in an unknown state
            self._stop_conversation()

        try:
            for addr in self.led_controller.leds.keys():
                try:
                    self.led_controller.set_brightness(addr, 0, 2000)
                except KeyError:
                    continue
        except Exception as e:
            error(f"Error while turning off LEDs for state {state}: {e}")

    def _play_thinking_audio(self) -> bool:
        """Play a random 'wonder' track while the LLM is thinking.

        Returns True if playback was successfully started, False otherwise.
        """
        if not self._audio_directory:
            return False

        # Pick a random track: wonder-###-stereo.wav with ### in [001, 100]
        idx = random.randint(1, 100)
        filename = f"wonder-{idx:03d}-stereo.wav"
        path = os.path.join(self._audio_directory, "wonder", filename)

        info(f"Starting thinking audio from: {path}")
        try:
            # Speaker.play is assumed to start non-blocking playback.
            self.speaker.play(path)
            return True
        except Exception as e:
            error(f"Failed to start thinking audio '{path}': {e}")
            return False

    # --------------------------
    # Conversation / LLM loop
    # --------------------------

    def _start_conversation(self) -> None:
        """Start the speech recognition + LLM loop in a background thread."""
        if self._conversation_thread is not None and self._conversation_thread.is_alive():
            return
        self._conversation_stop_event.clear()
        self._conversation_thread = threading.Thread(
            target=self._conversation_loop,
            daemon=True,
        )
        self._conversation_thread.start()
        info("EngagementController conversation loop started.")

    def _stop_conversation(self) -> None:
        """Stop the speech recognition + LLM loop if it is running."""
        if self._conversation_thread is None:
            return
        self._conversation_stop_event.set()
        try:
            self._conversation_thread.join(timeout=1.0)
        except Exception as e:
            warning(f"Error while stopping conversation thread: {e}")
        self._conversation_thread = None
        info("EngagementController conversation loop stopped.")

    def _process_transcript(self, text: str) -> None:
        """Handle a finalized transcript: update chat, query LLM, and speak the reply."""
        if not text:
            warning("Conversation: empty transcript, ignoring.")
            return

        clean_text = text.strip()
        if not clean_text:
            warning("Conversation: transcript empty after stripping, ignoring.")
            return

        info(f"Conversation: finalized user transcript: {clean_text!r}")

        # Ignore placeholder/marker transcripts (e.g., music or empty markers)
        marker = clean_text.lower()
        if marker in {"*music*", "(empty)", "[empty]"}:
            warning(f'Conversation: ignored placeholder transcript "{marker}"')
            return

        # Append user message
        self._chat_messages.append({"role": "user", "content": clean_text})

        # Query the LLM after speech finishes
        info(f"Conversation: querying Ollama, chat_messages={len(self._chat_messages)}, last_user_len={len(clean_text)}")
        
        # Log the last few messages (role + truncated content) to help debug context issues
        try:
            tail = self._chat_messages[-6:]
            for i, m in enumerate(tail, start=max(0, len(self._chat_messages) - len(tail))):
                role = m.get("role", "?")
                content = (m.get("content", "") or "")
                snippet = content.replace("\n", " ")
                if len(snippet) > 240:
                    snippet = snippet[:240] + "…"
                info(f"Conversation: chat[{i}] role={role} content='{snippet}'")
        except Exception as e:
            warning(f"Conversation: failed to log chat tail: {e}")

        started = time.time()
        try:
            response = query_ollama(self._chat_messages)
        except Exception as e:
            elapsed = time.time() - started
            error(f"Conversation: error while querying LLM after {elapsed:.2f}s: {e}")
            return

        elapsed = time.time() - started
        info(f"Conversation: Ollama returned in {elapsed:.2f}s")

        # Log raw response details (type + repr snippet) to debug unexpected return shapes
        try:
            rtype = type(response).__name__
            rrepr = repr(response)
            if len(rrepr) > 800:
                rrepr = rrepr[:800] + "…"
            info(f"Conversation: Ollama raw response type={rtype} repr={rrepr}")
        except Exception as e:
            warning(f"Conversation: failed to log raw Ollama response: {e}")

        if response is None:
            warning("Conversation: Ollama response is None.")
            return

        # Some wrappers might return empty strings or objects with empty content
        if isinstance(response, str):
            reply_text = response.strip()
        else:
            reply_text = getattr(response, "content", None)
            if reply_text is None:
                reply_text = str(response)
            reply_text = (reply_text or "").strip()

        if not reply_text:
            warning("Conversation: empty response text after parsing Ollama response.")
            return

        # Log the parsed reply text (truncated) for debugging
        try:
            snippet = reply_text.replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:300] + "…"
            info(f"Conversation: parsed reply_text_len={len(reply_text)} snippet='{snippet}'")
        except Exception as e:
            warning(f"Conversation: failed to log parsed reply snippet: {e}")

        # Append assistant reply and track for echo suppression
        self._chat_messages.append({"role": "assistant", "content": reply_text})
        self._last_assistant_reply = reply_text

        # Speak the reply
        # Some models include special tokens like </start_of_turn>. Strip common tag-like tokens
        # so macOS `say` receives clean natural language.
        cleaned_reply = reply_text
        try:
            cleaned_reply = re.sub(r"</?start_of_turn>|</?end_of_turn>", "", cleaned_reply)
            cleaned_reply = re.sub(r"<\|[^>]*\|>", "", cleaned_reply)  # e.g., <|endoftext|>
            cleaned_reply = cleaned_reply.replace("\u0000", "")
            cleaned_reply = cleaned_reply.strip()
        except Exception as e:
            warning(f"Conversation: failed to sanitize reply text: {e}")
            cleaned_reply = reply_text

        info(
            f"Conversation: speaking reply len={len(cleaned_reply)} rate={self._speech_rate} preview={cleaned_reply[:120]!r}"
        )
        self._speak(text=cleaned_reply, rate=self._speech_rate)

        # After TTS ends, enter a short quiet window to recalibrate baseline
        quiet_duration = 0.2
        self._quiet_until_ts = time.time() + quiet_duration
        info(f"Conversation: entering adaptive quiet window for {quiet_duration:.1f}s")

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        """Audio callback that uses Silero VAD to segment speech and trigger transcription."""
        if status:
            info(f"Conversation audio callback status: {status}")

        # Mono float32
        audio = indata.mean(axis=1) if indata.ndim > 1 else indata
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32, copy=False)

        # Compute RMS and current time
        rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0
        now_ts = time.time()

        # If the macOS 'say' TTS process is active, completely ignore this chunk
        # for VAD and transcription. This keeps our own voice from becoming an
        # utterance, without relying on an estimated speaking duration.
        if self._tts_is_active():
            info("Conversation audio callback: ignored chunk while 'say' TTS process is active.")
            return

        effective_gate = self._current_rms_gate()

        # During the post-TTS quiet window, force silence and keep adapting the baseline
        if now_ts < self._quiet_until_ts:
            self._update_rms_baseline(rms)
            speech_timestamps = []
        # If energy is below the effective gate, treat as silence and adapt baseline
        elif rms < effective_gate:
            self._update_rms_baseline(rms)
            speech_timestamps = []
        else:
            # Energy above gate: run VAD on this chunk
            audio_tensor = torch.from_numpy((audio * 32768).astype(np.int16))
            speech_timestamps = get_speech_timestamps(
                audio_tensor,
                self._vad_model,
                return_seconds=True,
                threshold=VAD_THRESHOLD,
                min_speech_duration_ms=VAD_MIN_SPEECH_MS,
                min_silence_duration_ms=VAD_MIN_SILENCE_MS,
                speech_pad_ms=SPEECH_PADDING_MS,
            )

        speech_detected = len(speech_timestamps) > 0

        # Transitions: debounced end-of-speech (require sustained silence)
        if speech_detected:
            if not self._in_speech:
                self._in_speech = True
                info("Conversation: speech started")
                self._current_utt = np.array([], dtype=np.float32)
            # Any detected speech cancels a pending end
            self._pending_end_ts = None
            # When speech is detected, accumulate the current audio chunk
            if self._current_utt.size:
                self._current_utt = np.concatenate((self._current_utt, audio))
            else:
                self._current_utt = audio.copy()
        else:
            if self._in_speech:
                if self._pending_end_ts is None:
                    # First silent frame after speech: start the end confirmation timer
                    self._pending_end_ts = now_ts
                else:
                    # If we have stayed silent long enough, finalize the utterance
                    if (now_ts - self._pending_end_ts) >= END_SILENCE_CONFIRM_SEC:
                        self._in_speech = False
                        self._pending_end_ts = None
                        info("Conversation: speech ended")
                        utt = self._current_utt if self._current_utt.size else np.array([], dtype=np.float32)
                        self._current_utt = np.array([], dtype=np.float32)
                        if utt.size > 0:
                            utt_dur_sec = float(utt.size) / float(SAMPLE_RATE)
                            if utt_dur_sec < MIN_UTTERANCE_SEC:
                                warning(f"TRANSCRIPT: [ignored short utterance {utt_dur_sec*1000:.0f} ms]")
                            else:
                                transcript = transcribe(utt)
                                self._process_transcript(transcript)
                        else:
                            warning("Conversation: no audio to process at end of speech.")
            # If we're already not in_speech, do nothing

    def _conversation_loop(self) -> None:
        """Stream audio from the mic, use VAD to detect speech, and drive the LLM."""
        info("Conversation loop running (ENGAGED state, VAD-based).")
        # Ensure we have a system prompt at the front of the chat history
        if not self._chat_messages or self._chat_messages[0].get("role") != "system":
            system_prompt = self._personality_cfg.get("systemPrompt", "") if hasattr(self, "_personality_cfg") else ""
            if system_prompt:
                self._chat_messages.insert(0, {"role": "system", "content": system_prompt})

        # Use personality speed if available, otherwise default to 80
        default_rate = 80
        try:
            rate = int(self._personality_cfg.get("speed", default_rate))
        except Exception:
            rate = default_rate
        self._speech_rate = rate

        # Open an InputStream and let the callback handle VAD + conversation
        try:
            with sd.InputStream(
                channels=1,
                samplerate=SAMPLE_RATE,
                blocksize=BUFFER_SIZE,
                callback=self._audio_callback,
                dtype="float32",
            ):
                while not self._conversation_stop_event.is_set():
                    time.sleep(0.1)
        except Exception as e:
            error(f"Conversation loop error: {e}")

        info("Conversation loop exiting.")
