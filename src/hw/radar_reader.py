import threading
import time
from typing import Optional

import serial

from util.logger import info, warning, error


RADAR_POLL_INTERVAL = 0.25  # seconds


class RadarReading:
    """Simple container for a single radar reading.

    Fields follow the existing firmware protocol:
      ts: timestamp in ms
      x:  x position in mm
      y:  y position in mm
      dist: distance in mm
      angle: angle in degrees
      speed: speed in cm/s
    """

    def __init__(self, ts: int, x: int, y: int, dist: int, angle: int, speed: int) -> None:
        self.timestamp_ms = ts
        self.x_mm = x
        self.y_mm = y
        self.distance_mm = dist
        self.angle_deg = angle
        self.speed_cm_s = speed

    def __repr__(self) -> str:
        return f"RadarReading(ts={self.timestamp_ms}, dist={self.distance_mm})"


class RadarReader:
    """Background radar poller that reads from the PAPA board.

    This class owns a polling thread that periodically sends READ to the
    radar serial device and stores the most recent RadarReading.

    It expects that HWState has already discovered and registered the radar
    serial connection, or you can pass a serial.Serial instance directly.
    """

    def __init__(
        self,
        radar_serial: Optional[serial.Serial],
        poll_interval: float = RADAR_POLL_INTERVAL,
    ) -> None:
        """Initialize a RadarReader with an existing radar_serial.

        The caller is responsible for creating and owning the serial.Serial
        instance and passing it in here.
        """
        self._serial = radar_serial
        self._poll_interval = poll_interval

        self._latest: Optional[RadarReading] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        if self._serial is None:
            warning("RadarReader initialized without a radar serial device")
        else:
            info("RadarReader initialized with radar serial device")

    # --------------------------
    # Public control methods
    # --------------------------

    def start(self) -> None:
        """Start the radar polling thread if a serial device is available."""
        if self._serial is None:
            warning("RadarReader.start called but no radar serial is available")
            return

        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        info("RadarReader polling thread started")

    def stop(self) -> None:
        """Stop the radar polling thread and wait briefly for it to exit."""
        if self._thread is None:
            return

        self._stop_event.set()
        self._thread.join(timeout=1.0)
        self._thread = None
        info("RadarReader polling thread stopped")

    # --------------------------
    # Data accessors
    # --------------------------

    def get_latest(self) -> Optional[RadarReading]:
        """Return the most recent RadarReading, or None if none yet."""
        with self._lock:
            return self._latest

    def get_distance_mm(self) -> Optional[int]:
        """Return the most recent distance in mm, or None if no reading."""
        reading = self.get_latest()
        if reading is None:
            return None
        return reading.distance_mm

    # --------------------------
    # Internal polling loop
    # --------------------------

    def _poll_loop(self) -> None:
        """Worker loop that sends READ and parses radar responses."""
        try:
            while not self._stop_event.is_set():
                try:
                    self._serial.write(b"READ\r\n")
                    line = self._serial.readline().decode("ascii", errors="ignore").strip()

                    if not line:
                        time.sleep(self._poll_interval)
                        continue

                    parts = line.split()
                    if len(parts) != 6:
                        warning(f"Unexpected format: {line}")
                        time.sleep(self._poll_interval)
                        continue

                    try:
                        vals = [int(p) for p in parts]
                    except Exception as e:
                        error(f"Parse error: {e}. Line='{line}'")
                        time.sleep(self._poll_interval)
                        continue

                    # vals: [ts, x, y, dist, angle, speed]
                    ts, x, y, dist, angle, speed = vals

                    # Ignore readings where all sensor values are zero
                    if ts == 0 and x == 0 and y == 0 and dist == 0 and angle == 0 and speed == 0:
                        reading = RadarReading(ts, x, y, dist, angle, speed)
                        info(
                            f"Ignoring all-zero reading "
                            f"ts={reading.timestamp_ms}, "
                            f"x={reading.x_mm}, y={reading.y_mm}, "
                            f"dist={reading.distance_mm}, "
                            f"angle={reading.angle_deg}, "
                            f"speed={reading.speed_cm_s}"
                        )
                    else:
                        reading = RadarReading(ts, x, y, dist, angle, speed)
                        with self._lock:
                            self._latest = reading
                        info(
                            f"reading ts={reading.timestamp_ms}, "
                            f"x={reading.x_mm}, y={reading.y_mm}, "
                            f"dist={reading.distance_mm}, "
                            f"angle={reading.angle_deg}, "
                            f"speed={reading.speed_cm_s}"
                        )

                except Exception as e:
                    error(f"Error during READ: {e}")

                time.sleep(self._poll_interval)

        except Exception as e:
            error(f"RadarReader polling loop crashed: {e}")