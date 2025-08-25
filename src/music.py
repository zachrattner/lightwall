import random
import subprocess
import shutil
from typing import Optional
import threading
import time
import os

FADE_IN_TIME_MS = 500
FADE_OUT_TIME_MS = 500

class _MusicPlayer:
    """
    Singleton music player that represents the current music playback
    on this Mac at any point in time. It stores the selected file path
    and the underlying playback process.
    """

    _instance: Optional["_MusicPlayer"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Only initialize once in a singleton pattern
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._player_proc: Optional[subprocess.Popen] = None
        self.current_track: Optional[str] = None

    # --- Internal helpers ---
    def _choose_player(self) -> str:
        """Return path to the preferred audio player."""
        player = shutil.which("ffplay")
        if player is None:
            raise RuntimeError("No audio player found: install 'ffmpeg' to get 'ffplay' (e.g., brew install ffmpeg).")
        return player

    def _log_system_audio_state(self) -> None:
        """Log current macOS audio output device and volume/mute state.
        Uses SwitchAudioSource if available; falls back to AppleScript for volume.
        """
        try:
            sas = shutil.which("SwitchAudioSource")
            if sas:
                try:
                    subprocess.check_output([sas, "-c", "-t", "output"], text=True).strip()
                    subprocess.check_output([sas, "-a", "-t", "output"], text=True)
                except Exception:
                    pass
            # Volume & mute via AppleScript
            try:
                subprocess.check_output(["osascript", "-e", "output volume of (get volume settings)"], text=True).strip()
                subprocess.check_output(["osascript", "-e", "output muted of (get volume settings)"], text=True).strip()
            except Exception:
                pass
        except Exception:
            pass

    def _fade_out_system_volume(self, duration_ms: int) -> Optional[int]:
        """Fade out using macOS system output volume over duration_ms.
        Returns the original volume (0-100) if successful, else None.
        Controlled by env var AUDIO_FADE_OUT_SYSTEM=1.
        """
        if os.environ.get("AUDIO_FADE_OUT_SYSTEM") != "1":
            time.sleep(max(0, duration_ms) / 1000)
            return None
        try:
            muted = subprocess.check_output(["osascript", "-e", "output muted of (get volume settings)"] , text=True).strip().lower()
            vol_str = subprocess.check_output(["osascript", "-e", "output volume of (get volume settings)"], text=True).strip()
            try:
                start_vol = int(vol_str)
            except Exception:
                start_vol = 0
            if muted == "true":
                time.sleep(max(0, duration_ms) / 1000)
                return start_vol
            # Perform stepped fade to 0
            steps = max(5, min(40, duration_ms // 50))  # 50ms to ~200ms per step
            step_sleep = (duration_ms / 1000.0) / steps if steps else 0.05
            for i in range(1, steps + 1):
                new_vol = max(0, int(round(start_vol * (1 - i / steps))))
                try:
                    subprocess.check_call(["osascript", "-e", f"set volume output volume {new_vol}"])  # set volume
                except Exception:
                    pass
                time.sleep(step_sleep)
            return start_vol
        except Exception:
            time.sleep(max(0, duration_ms) / 1000)
            return None

    # --- Public API (mirrors previous module-level functions) ---
    def select_track(self) -> str:
        number = random.randint(1, 100)
        padded = str(number).zfill(3)
        self.current_track = f"audio/neutral-{padded}-stereo.wav"
        if not os.path.exists(self.current_track):
            pass
        return self.current_track


    def start_playing(self) -> str:
        """
        Start playing a randomly selected stereo track. If something is already playing,
        it will be stopped first. Returns the path to the started track.
        """
        # If a player is already running, stop it first
        if self._player_proc and self._player_proc.poll() is None:
            self.stop_playing()

        track = self.select_track()
        player = self._choose_player()

        # Log current system audio state
        self._log_system_audio_state()

        # Optionally switch output device via env var if SwitchAudioSource is available
        desired_dev = os.environ.get("AUDIO_OUTPUT_DEVICE")
        sas = shutil.which("SwitchAudioSource")
        if desired_dev and sas:
            try:
                subprocess.check_call([sas, "-s", desired_dev, "-t", "output"])  # set device
                subprocess.check_output([sas, "-c", "-t", "output"], text=True).strip()
            except subprocess.CalledProcessError:
                pass

        fade_in_sec = max(0.0, FADE_IN_TIME_MS / 1000.0)

        if not os.path.exists(track):
            return track

        afade_filter = f"afade=t=in:st=0:d={fade_in_sec}:curve=tri"
        cmd = [
            player,
            "-nodisp",
            "-autoexit",
            "-loglevel", "error",
            "-i", track,
            "-af", afade_filter,
        ]
        self._player_proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # Thread: forward ffplay stderr to our logs
        def _drain_stderr(proc: subprocess.Popen) -> None:
            try:
                if proc.stderr is None:
                    return
                for line in proc.stderr:
                    line = line.rstrip("\n")
                    if not line:
                        continue
            except Exception:
                pass

        t1 = threading.Thread(target=_drain_stderr, args=(self._player_proc,), daemon=True)
        t1.start()

        # Thread: log when process exits
        def _wait_and_log(proc: subprocess.Popen) -> None:
            try:
                proc.wait()
            except Exception:
                pass

        t2 = threading.Thread(target=_wait_and_log, args=(self._player_proc,), daemon=True)
        t2.start()

        return track

    # Note: ffplay does not expose a programmatic per-stream volume control API we can drive at runtime,
    # so we cannot apply a *true* fade-out on demand without touching system volume. We simulate timing below.
    def stop_playing(self) -> bool:
        """
        Stop playback (if running) and free player resources.
        Returns True if a player was stopped or cleared, False if nothing was running.
        """
        if self._player_proc is None:
            return False

        original_vol = self._fade_out_system_volume(FADE_OUT_TIME_MS)

        # If process still running, terminate it
        if self._player_proc.poll() is None:
            try:
                self._player_proc.terminate()
                try:
                    self._player_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._player_proc.kill()
            except Exception:
                # Ignore termination errors; we'll clear the handle below
                pass

        try:
            if original_vol is not None:
                subprocess.check_call(["osascript", "-e", f"set volume output volume {original_vol}"])
        except Exception:
            pass

        self._player_proc = None
        self.current_track = None
        return True


# --- Module-level compatibility shims (do not break callers) ---

# Keep a module-level singleton instance
_player_singleton = _MusicPlayer()


def select_track() -> str:
    return _player_singleton.select_track()


def start_playing() -> str:
    return _player_singleton.start_playing()


def stop_playing() -> bool:
    return _player_singleton.stop_playing()
