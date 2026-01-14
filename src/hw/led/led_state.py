from __future__ import annotations
from typing import List
import serial
from typing import Literal, Optional
import time
import threading

ALL_ADDRESSES: List[str] = [
    "A1", "A2", "A3",
    "B0", "B4",
    "C0", "C4",
    "D0", "D4",
    "E0", "E4",
    "F1", "F2", "F3",
]

LEDAddress = str

class LEDState:
    def __init__(self, address: LEDAddress, ser: serial.Serial, index: int) -> None:
        self.address = address
        self.index = index
        self.ser = ser
        self.status: Literal["off", "on", "fading"] = "off"
        self.brightness: int = 0
        self.prev_brightness: int = 0
        self.duration_ms: int = 0
        self.start_at: Optional[float] = None
        self.end_at: Optional[float] = None
        self._send()

    def set_brightness(self, brightness: int, duration_ms: int) -> None:
        """Set brightness with an optional fade duration.

        This method sends the command immediately and then schedules
        a status update after the fade duration has elapsed.
        """
        self.prev_brightness = self.brightness
        self.brightness = max(0, min(255, brightness))
        self.duration_ms = max(0, duration_ms)

        # If there is no duration, treat this as an instant change.
        if self.duration_ms == 0:
            self.start_at = time.time()
            self.end_at = self.start_at
            self.status = "on" if self.brightness > 0 else "off"
            self._send()
            return

        # Fade case
        self.start_at = time.time()
        self.end_at = self.start_at + (self.duration_ms / 1000.0)
        self.status = "fading"
        self._send()

        # Schedule a non-blocking callback to mark completion.
        def _finish():
            self.status = "on" if self.brightness > 0 else "off"

        threading.Timer(self.duration_ms / 1000.0, _finish).start()

    def _send(self) -> None:
        """Send the current state to the hardware over the attached serial port.

        The caller is responsible for constructing LEDState with the correct
        serial port and LED index (from hwMap.json).
        """
        if not hasattr(self, "ser") or self.ser is None:
            return

        value = max(0, min(255, int(self.brightness)))
        duration = max(0, int(self.duration_ms))
        cmd = f"SET {self.index} {value} {duration}\r\n"
        try:
            self.ser.write(cmd.encode("ascii"))
        except Exception:
            # Hardware errors should not crash the controller loop
            pass

__all__ = ["ALL_ADDRESSES", "LEDState", "LEDAddress"]
