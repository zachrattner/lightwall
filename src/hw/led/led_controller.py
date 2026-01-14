from __future__ import annotations

import serial
from typing import Dict
from .led_state import LEDState, LEDAddress
from util.logger import info
import threading

class LEDController:
    """Controller responsible for creating and managing all LEDState objects.

    The caller provides hwMap.json AND pre-opened serial interfaces for each
    board. The controller maps LED addresses to LEDState instances using the
    board's defined LED index.
    """

    def __init__(self, hwmap: list, board_serials: Dict[str, serial.Serial]) -> None:
        """Initialize the LED controller.

        hwmap: parsed hwMap JSON list
        board_serials: dict mapping board_name -> serial.Serial object
        """

        self.leds: Dict[LEDAddress, LEDState] = {}
        self.board_serials = board_serials
        self._lock = threading.Lock()

        info("Initializing LEDController")

        # Parse hwmap and create LEDState instances
        for entry in hwmap:
            if entry.get("type") != "light":
                continue

            board_name = entry["board_name"]
            mapping = entry.get("mapping", {})

            if board_name not in self.board_serials:
                continue  # caller did not provide a serial for this board

            info(f"Configuring light board {board_name}")

            ser = self.board_serials[board_name]

            for addr_str, index in mapping.items():
                addr: LEDAddress = addr_str
                self.leds[addr] = LEDState(address=addr, index=index, ser=ser)
                info(f"Mapped LED {addr} to index {index} on {board_name}")

        info(f"LEDController initialized with {len(self.leds)} LEDs")

    def set_brightness(self, address: LEDAddress, brightness: int, duration_ms: int) -> None:
        # info(f"Setting LED {address} to brightness {brightness} over {duration_ms} ms")

        with self._lock:
            if address not in self.leds:
                raise KeyError(f"Unknown LED address: {address}")

            self.leds[address].set_brightness(brightness, duration_ms)


__all__ = ["LEDController"]
