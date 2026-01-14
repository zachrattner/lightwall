from __future__ import annotations

import serial
from typing import Dict
from .motor_state import MotorState, MotorAddress
from util.logger import info
import threading
import time

class MotorController:
    """Controller responsible for creating and managing all MotorState objects."""

    # Minimum interval between commands to any motor, in seconds.
    # This helps prevent overrunning the motor firmware with back-to-back
    # serial commands that are too close together.
    _MIN_CMD_INTERVAL = 0.1

    def __init__(self, hwmap: list, board_serials: Dict[str, serial.Serial]) -> None:
        self.motors: Dict[MotorAddress, MotorState] = {}
        self.board_serials = board_serials
        self._lock = threading.Lock()
        self._last_cmd_time = 0.0

        info("Initializing MotorController")

        for entry in hwmap:
            if entry.get("type") != "motor":
                continue

            board_name = entry["board_name"]
            address = entry["address"]

            if board_name not in self.board_serials:
                continue

            ser = self.board_serials[board_name]
            self.motors[address] = MotorState(address=address, ser=ser)
            info(f"Mapped motor {address} on {board_name}")

        info(f"MotorController initialized with {len(self.motors)} motors")

    def _throttle(self) -> None:
        """Ensure a minimum interval between motor commands."""
        now = time.monotonic()
        delta = now - self._last_cmd_time
        if delta < self._MIN_CMD_INTERVAL:
            sleep_time = self._MIN_CMD_INTERVAL - delta
            # Keep this log at info level for now so we can see when throttling occurs.
            info(f"MotorController: throttling commands for {sleep_time:.3f}s to respect min interval.")
            time.sleep(sleep_time)
        self._last_cmd_time = time.monotonic()

    def rotate(self, address: MotorAddress, direction: str, rpm: int) -> None:
        with self._lock:
            if address not in self.motors:
                raise KeyError(f"Unknown motor address: {address}")
            self._throttle()
            self.motors[address].rotate(direction, rpm)

    def move_to(self, address: MotorAddress, direction: str, position: int, duration_ms: int) -> None:
        with self._lock:
            if address not in self.motors:
                raise KeyError(f"Unknown motor address: {address}")
            self._throttle()
            self.motors[address].move_to(direction, position, duration_ms)

    def stop(self, address: MotorAddress) -> None:
        with self._lock:
            if address not in self.motors:
                raise KeyError(f"Unknown motor address: {address}")
            self._throttle()
            self.motors[address].stop()            

__all__ = ["MotorController"]
