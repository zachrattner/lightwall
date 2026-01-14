import threading
import time
from typing import Sequence, Optional

from util.logger import info, warning, error
from .led.led_controller import LEDController
from .led.led_state import LEDAddress
from .motor.motor_controller import MotorController
from .motor.motor_state import MotorAddress

class ApproachingSequence:
    """Approaching animation that marches LEDs along the top and bottom rows.

    This class owns a background thread that periodically calls
    LEDController.set_brightness while the sequence is running, and can also
    drive motors in sync with the LEDs during the approaching phase.
    """

    def __init__(
        self,
        led_controller: LEDController,
        motor_controller: Optional[MotorController] = None,
        top_row: Sequence[LEDAddress] = ["B0", "C0", "D0", "E0"],
        bottom_row: Sequence[LEDAddress] = ["E4", "D4", "C4", "B4"],
        fade_in_ms: int = 400,
        hold_ms: int = 150,
        fade_out_ms: int = 1000,
        next_led_delay: float = 0.7,
        max_brightness: int = 128,
        min_brightness: int = 10,
    ) -> None:
        """
        :param led_controller: Shared LEDController instance
        :param motor_controller: Shared MotorController instance or None
        :param top_row: Ordered LED addresses for the top row
        :param bottom_row: Ordered LED addresses for the bottom row
        :param fade_in_ms: Fade in duration sent to the controller
        :param hold_ms: Hold duration at max brightness
        :param fade_out_ms: Fade out duration sent to the controller
        :param next_led_delay: Delay before moving to the next LED
        :param max_brightness: Brightness of the LED at peak
        :param min_brightness: Minimum brightness of the LED
        """
        self.led_controller = led_controller
        self.motor_controller = motor_controller
        self.top_row = list(top_row)
        self.bottom_row = list(bottom_row)

        # Timing and brightness borrowed from Fibonacci sparkle script
        # FADE_IN_MS  = 500
        # HOLD_MS     = 200
        # FADE_OUT_MS = 1200
        # NEXT_LED_DELAY = 0.8
        # MAX_BRIGHTNESS = 64
        # MIN_BRIGHTNESS = 0
        self.fade_in_ms = fade_in_ms
        self.hold_ms = hold_ms
        self.fade_out_ms = fade_out_ms
        self.next_led_delay = next_led_delay
        self.max_brightness = max_brightness
        self.min_brightness = min_brightness

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

        # Cache the list of LED addresses known to the controller
        self._addresses: list[LEDAddress] = list(self.led_controller.leds.keys())

        if not self._addresses:
            warning("ApproachingSequence created with no LED addresses")

        # Build a continuous path that runs along the top and back along the bottom
        self._path: list[LEDAddress] = self.top_row + list(reversed(self.bottom_row))

        if not self._path:
            warning("ApproachingSequence created with an empty path")

        # Simple motor approaching behavior configuration
        # Each time an LED becomes active, the mapped motor will move
        # a fixed number of steps clockwise using a move_to command.
        self._steps_per_move: int = 100
        self._move_time_ms: int = 1000

        # Mapping from LED address to corresponding motor address
        self._led_to_motor: dict[LEDAddress, MotorAddress] = {
            "B0": "B1",
            "C0": "C1",
            "D0": "D1",
            "E0": "E1",
            "B4": "B3",
            "C4": "C3",
            "D4": "D3",
            "E4": "E3",
        }

    def start(self) -> None:
        """Start the approaching animation in a background thread."""
        if self._running:
            return

        if not self._path:
            warning("ApproachingSequence cannot start because path is empty")
            return
        
        # Turn off all LEDs before starting
        if self._addresses:
            for addr in self._addresses:
                try:
                    self.led_controller.set_brightness(addr, 0, 500)
                except Exception:
                    pass        

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._running = True
        info("ApproachingSequence started")

    def stop(self) -> None:
        """Stop the approaching animation and wait briefly for the thread to exit."""
        if not self._running:
            return

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._running = False
        info("ApproachingSequence stopped")

    def is_running(self) -> bool:
        """Return True if the idle sequence is currently running."""
        return self._running

    def _drive_motor_for_led(self, addr: LEDAddress) -> None:
        """If a motor_controller is present, move the mapped motor 100 steps CW."""
        if self.motor_controller is None:
            return

        motor_addr = self._led_to_motor.get(addr)
        if motor_addr is None:
            return

        if motor_addr not in self.motor_controller.motors:
            # Motor is not available, skip
            return

        move_time_s = self._move_time_ms / 1000.0
        info(
            f"ApproachingSequence: LED {addr} mapped to motor {motor_addr}. "
            f"move_to CW {self._steps_per_move} steps over {move_time_s:.3f}s."
        )

        try:
            self.motor_controller.move_to(
                motor_addr,
                "CW",
                self._steps_per_move,
                self._move_time_ms,
            )
        except Exception as e:
            warning(f"ApproachingSequence: error issuing move_to for motor {motor_addr}: {e}")

    def _run_loop(self) -> None:
        """Worker loop that advances the approaching animation until stop is requested.

        Pattern for each LED in the path:
          1) Fade in to max_brightness over fade_in_ms
          2) Hold at max_brightness for hold_ms
          3) Fade out to min_brightness over fade_out_ms
          4) Wait next_led_delay seconds before the next LED
        """
        try:
            if not self._path:
                warning("Approaching sequence run loop has empty path, exiting")
                return

            while not self._stop_event.is_set():
                for addr in self._path:
                    if self._stop_event.is_set():
                        break

                    # Kick off the corresponding motor move, if configured
                    self._drive_motor_for_led(addr)

                    # 1. Fade IN
                    try:
                        self.led_controller.set_brightness(addr, self.max_brightness, self.fade_in_ms)
                    except KeyError:
                        warning(f"Approaching sequence tried to set unknown LED {addr}")
                        continue
                    except Exception as e:
                        error(f"Approaching sequence error while setting {addr} during fade in: {e}")
                        continue

                    # Wait for fade in and hold
                    time.sleep(self.fade_in_ms / 1000.0)
                    time.sleep(self.hold_ms / 1000.0)

                    # 2. Fade OUT
                    try:
                        self.led_controller.set_brightness(addr, self.min_brightness, self.fade_out_ms)
                    except Exception as e:
                        error(f"Approaching sequence error while setting {addr} during fade out: {e}")

                    # 3. Tempo between LEDs
                    elapsed = 0.0
                    while elapsed < self.next_led_delay and not self._stop_event.is_set():
                        chunk = min(0.05, self.next_led_delay - elapsed)
                        time.sleep(chunk)
                        elapsed += chunk

        except Exception as e:
            # Catch any unexpected exceptions to avoid killing the daemon thread silently
            error(f"Approaching sequence run loop crashed: {e}")