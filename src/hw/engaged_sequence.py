import threading
import time
from typing import Sequence, Optional
import random

from util.logger import info, warning, error
from .led.led_controller import LEDController
from .led.led_state import LEDAddress
from .motor.motor_controller import MotorController
from .motor.motor_state import MotorAddress

class EngagedSequence:
    """Engaged animation where LEDs sparkle and mapped motors move in response.

    This class owns a background thread that periodically calls
    LEDController.set_brightness while the sequence is running, and also
    drives motors whose LEDs are currently the brightest in the engaged phase.
    """

    def __init__(
        self,
        led_controller: LEDController,
        motor_controller: Optional[MotorController] = None,
        top_row: Sequence[LEDAddress] = ["B0", "C0", "D0", "E0"],
        bottom_row: Sequence[LEDAddress] = ["E4", "D4", "C4", "B4"],
        left_side: Sequence[LEDAddress] = ["A1", "A2", "A3"],
        right_side: Sequence[LEDAddress] = ["F1", "F2", "F3"],
        fade_in_ms: int = 400,
        hold_ms: int = 750,
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
        :param left_side: Ordered LED addresses for the left side (top to bottom)
        :param right_side: Ordered LED addresses for the right side (top to bottom)
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
        self.left_side = list(left_side)
        self.right_side = list(right_side)

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
            warning("EngagedSequence created with no LED addresses")

        # Build a continuous path that runs around the perimeter:
        # left side (top to bottom), top row, right side (top to bottom),
        # then back along the bottom.
        self._path: list[LEDAddress] = (
            self.left_side
            + self.top_row
            + self.right_side
            + list(reversed(self.bottom_row))
        )

        if not self._path:
            warning("EngagedSequence created with an empty path")

        # Simple motor engaged behavior configuration
        # When LEDs are at peak brightness, their mapped motors perform slow moves.
        self._steps_per_move: int = 100
        self._move_time_ms: int = 1000

        # Mapping from LED address to corresponding motor address
        self._led_to_motor: dict[LEDAddress, MotorAddress] = {
            "A1": "B1",
            "A2": "B2",
            "A3": "B3",
            "B0": "B1",
            "C0": "C1",
            "D0": "D1",
            "E0": "E1",
            "B4": "B3",
            "C4": "C3",
            "D4": "D3",
            "E4": "E3",
            "F1": "E1",
            "F2": "E2",
            "F3": "E3"
        }

        # Motor scheduling: stagger slow 5–15 second movements so mapped motors do not move at once
        self._motor_next_move: dict[MotorAddress, float] = {}
        self._min_motor_move_s: float = 5.0
        self._max_motor_move_s: float = 15.0

        if self.motor_controller is not None:
            now = time.monotonic()
            for motor_addr in self.motor_controller.motors.keys():
                # Stagger initial moves randomly within the maximum window
                delay = random.uniform(0.0, self._max_motor_move_s)
                self._motor_next_move[motor_addr] = now + delay

    def start(self) -> None:
        """Start the engaged animation in a background thread."""
        if self._running:
            return

        if not self._path:
            warning("EngagedSequence cannot start because path is empty")
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
        info("EngagedSequence started")

    def stop(self) -> None:
        """Stop the engaged animation and wait briefly for the thread to exit."""
        if not self._running:
            return

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._running = False
        info("EngagedSequence stopped")

    def is_running(self) -> bool:
        """Return True if the engaged sequence is currently running."""
        return self._running

    def _drive_motors_for_leds(self, addrs: list[LEDAddress]) -> None:
        """Use the LED to motor mapping to move motors for the brightest LEDs.

        Motors are only triggered for LEDs in the current sparkle group and use
        the same slow, staggered scheduling as before so they do not move at once.
        """
        if self.motor_controller is None:
            return

        if not addrs:
            return

        now = time.monotonic()
        for addr in addrs:
            motor_addr = self._led_to_motor.get(addr)
            if motor_addr is None:
                continue
            if motor_addr not in self.motor_controller.motors:
                continue

            next_move_at = self._motor_next_move.get(motor_addr, now)
            if now < next_move_at:
                continue

            # Choose a random duration between the configured min and max
            duration_s = random.uniform(self._min_motor_move_s, self._max_motor_move_s)
            duration_ms = int(duration_s * 1000)
            direction = random.choice(["CW", "CCW"])

            info(
                f"EngagedSequence: LED {addr} mapped to motor {motor_addr}, "
                f"moving {direction} for {duration_s:.1f}s using move_to with {self._steps_per_move} steps."
            )

            try:
                self.motor_controller.move_to(
                    motor_addr,
                    direction,
                    self._steps_per_move,
                    duration_ms,
                )
            except Exception as e:
                warning(f"EngagedSequence: error issuing move_to for motor {motor_addr}: {e}")

            # Schedule the next move for this motor after this one finishes, plus a random pause
            pause_s = random.uniform(self._min_motor_move_s, self._max_motor_move_s)
            self._motor_next_move[motor_addr] = now + duration_s + pause_s

    def _run_loop(self) -> None:
        """Worker loop that advances the engaged animation until stop is requested.

        Pattern:
          - 2-3 LEDs sparkle at a time by randomly fading in and out together.
          - When LEDs reach peak brightness, their mapped motors move slowly,
            with scheduling so not all mapped motors move at once.
        """
        try:
            if not self._path:
                warning("Engaged sequence run loop has empty path, exiting")
                return

            while not self._stop_event.is_set():
                # Sparkle effect: pick 2–3 random LEDs from the path
                if not self._path:
                    continue

                num_leds = min(len(self._path), random.randint(2, 3))
                try:
                    addrs = random.sample(self._path, num_leds)
                except ValueError:
                    # Fallback if sample fails for some reason
                    addrs = [random.choice(self._path)]

                # Drive motors corresponding to the LEDs that are about to turn on
                self._drive_motors_for_leds(addrs)

                # 1. Fade IN on the selected LEDs
                for addr in addrs:
                    try:
                        self.led_controller.set_brightness(addr, self.max_brightness, self.fade_in_ms)
                    except KeyError:
                        warning(f"Engaged sequence tried to set unknown LED {addr}")
                        continue
                    except Exception as e:
                        error(f"Engaged sequence error while setting {addr} during fade in: {e}")
                        # Do not break the whole cycle; continue with other LEDs
                        continue

                # Wait for fade in and hold
                time.sleep(self.fade_in_ms / 1000.0)
                time.sleep(self.hold_ms / 1000.0)

                # 2. Fade OUT on the same LEDs
                for addr in addrs:
                    try:
                        self.led_controller.set_brightness(addr, self.min_brightness, self.fade_out_ms)
                    except Exception as e:
                        error(f"Engaged sequence error while setting {addr} during fade out: {e}")

                # 3. Tempo between sparkles
                elapsed = 0.0
                while elapsed < self.next_led_delay and not self._stop_event.is_set():
                    chunk = min(0.05, self.next_led_delay - elapsed)
                    time.sleep(chunk)
                    elapsed += chunk

        except Exception as e:
            # Catch any unexpected exceptions to avoid killing the daemon thread silently
            error(f"Engaged sequence run loop crashed: {e}")