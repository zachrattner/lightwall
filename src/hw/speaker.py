import subprocess
import threading
from pathlib import Path
from typing import Optional

_say_lock = threading.Lock()

class Speaker:
    """Simple interface to system audio output.

    Uses macOS `say` for text to speech and `afplay` for audio playback.
    """

    def stop(self) -> None:
        """Stop all audio playback, including afplay and say.

        This uses killall to terminate macOS audio processes because the
        worker threads use blocking subprocess.run calls and do not expose
        process handles.
        """
        try:
            subprocess.run(["killall", "afplay"], check=False)
        except Exception:
            pass
        try:
            subprocess.run(["killall", "say"], check=False)
        except Exception:
            pass

    def _say_worker(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        prefix: Optional[str] = None,
    ) -> None:
        """Internal worker that performs the blocking `say` call under a mutex."""
        if not text:
            return

        with _say_lock:
            try:
                cmd = ["say"]

                # Optional prefix
                if prefix:
                    text = f"{prefix} {text}"

                # Optional voice
                if voice:
                    cmd.extend(["-v", voice])

                # Optional rate
                if rate is not None:
                    cmd.extend(["-r", str(rate)])

                cmd.append(text)

                subprocess.run(cmd, check=False)
            except FileNotFoundError:
                # `say` is not available on this system
                pass
            except Exception:
                # Fail silently for other errors
                pass

    def _play_worker(self, filepath: str) -> None:
        """Internal worker that performs the blocking `afplay` call."""
        if not filepath:
            return

        path = Path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"Audio file does not exist: {path}")

        try:
            subprocess.run(["afplay", str(path)], check=False)
        except FileNotFoundError:
            # `afplay` is not available on this system
            pass
        except Exception:
            # Fail silently for other errors
            pass

    def say(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        prefix: Optional[str] = None,
    ) -> None:
        """Speak the given text using macOS `say` in a background thread.

        A module level mutex ensures that only one underlying `say` call
        runs at a time so audio does not overlap, but the caller returns
        immediately.
        """
        if not text:
            return

        thread = threading.Thread(
            target=self._say_worker,
            args=(text, voice, rate, prefix),
            daemon=True,
        )
        thread.start()

    def play(self, filepath: str) -> None:
        """Play an audio file at the given path using `afplay` in a background thread."""
        if not filepath:
            return

        thread = threading.Thread(
            target=self._play_worker,
            args=(filepath,),
            daemon=True,
        )
        thread.start()
