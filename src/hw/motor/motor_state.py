from __future__ import annotations
from typing import List, Literal, Optional
import serial
import time
import threading

ALL_ADDRESSES: List[str] = [
    "B1", "C1", "D1", "E1",
    "B2", "C2", "D2", "E2",
    "B3", "C3", "D3", "E3",
]

MotorAddress = str

class MotorState:
    """Track and control the state of a single motor over a serial connection.

    This mirrors the pattern used in LEDState, but for motor commands.

    Each MotorState instance represents one logical motor (by address) that is
    connected to a specific serial port. The board on that serial port is
    expected to understand commands of the form:

        ROT DIR RPM
        STP DIR POS TIME

    where:
        DIR  = "CW" or "CCW"
        RPM  = integer 1..100 (inclusive)
        POS  = integer position, 0 = top, 180 = bottom, etc.
        TIME = integer milliseconds to move to that position
    """

    def __init__(self, address: MotorAddress, ser: serial.Serial) -> None:
        self.address = address
        self.ser = ser

        # Current high level mode of the motor.
        # "stopped"  = not actively commanded
        # "rotating" = continuous rotation via ROT
        # "stepping" = moving to a position via STP
        self.status: Literal["stopped", "rotating", "stepping"] = "stopped"

        # Last known command parameters
        self.direction: Optional[Literal["CW", "CCW"]] = None
        self.rpm: int = 0                 # valid when rotating
        self.position: int = 0            # valid when stepping
        self.duration_ms: int = 0         # valid when stepping

        # Timing information for motions that complete after a duration.
        self.start_at: Optional[float] = None
        self.end_at: Optional[float] = None

    # Public API
    def rotate(self, direction: Literal["CW", "CCW"], rpm: int) -> None:
        """Start continuous rotation in the given direction at a given RPM.

        RPM is clamped between 1 and 100 inclusive.
        This sends a ROT command immediately and updates the internal status.
        """
        rpm = int(rpm)
        rpm_clamped = max(1, min(100, rpm))

        self.direction = direction
        self.rpm = rpm_clamped
        self.duration_ms = 0
        self.position = 0
        self.status = "rotating"
        self.start_at = time.time()
        self.end_at = None

        self._send_rot()

    def stop(self) -> None:
        """Stop the motor immediately
        """
        self.status = "stopped"
        self.start_at = time.time()
        self.end_at = self.start_at

        self._send_stop()        

    def move_to(
        self,
        direction: Literal["CW", "CCW"],
        position: int,
        duration_ms: int,
    ) -> None:
        """Move the motor to a specific position over a given time.

        This sends a STP command and marks the motor as "stepping".
        Once the duration elapses, the status is updated to "stopped"
        via a non blocking timer callback.
        """
        position = int(position)
        duration_ms = max(0, int(duration_ms))

        self.direction = direction
        self.position = position
        self.duration_ms = duration_ms
        self.rpm = 0
        self.status = "stepping"
        self.start_at = time.time()
        self.end_at = self.start_at + (self.duration_ms / 1000.0) if self.duration_ms > 0 else self.start_at

        self._send_step()

        if self.duration_ms > 0:
            def _finish() -> None:
                # When the move completes, consider the motor as stopped and holding position.
                self.status = "stopped"

            threading.Timer(self.duration_ms / 1000.0, _finish).start()
        else:
            # Instant move, immediately mark as stopped.
            self.status = "stopped"

    # Private helpers

    def _send_rot(self) -> None:
        """Send the current rotation state as a ROT command."""
        if not hasattr(self, "ser") or self.ser is None:
            return
        if self.direction is None:
            return

        rpm = max(1, min(100, int(self.rpm)))
        cmd = f"ROT {self.direction} {rpm}\r\n"
        self._write(cmd)

    def _send_step(self) -> None:
        """Send the current step state as a STP command."""
        if not hasattr(self, "ser") or self.ser is None:
            return
        if self.direction is None:
            return

        pos = int(self.position)
        duration = max(0, int(self.duration_ms))
        cmd = f"STP {self.direction} {pos} {duration}\r\n"
        self._write(cmd)

    def _send_stop(self) -> None:
        """Send the stop signal as a STOP command"""
        if not hasattr(self, "ser") or self.ser is None:
            return

        cmd = "STOP\r\n"
        self._write(cmd)        

    def _write(self, cmd: str) -> None:
        """Low level write helper to protect the controller loop from errors."""
        try:
            self.ser.write(cmd.encode("ascii"))
        except Exception:
            # Hardware errors should not crash the controller loop.
            pass


__all__ = ["ALL_ADDRESSES", "MotorState", "MotorAddress"]
