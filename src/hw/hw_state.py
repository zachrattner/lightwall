import threading
import os
import sys
import json
import time
import glob
import serial
from util.logger import info, warning, error
from hw.radar_reader import RadarReader


class HWState:
    """
    Singleton that stores global hardware state for Lightwall.

    Holds:
      • LED serial instances
      • Motor serial instances
      • Radar serial instance
      • Current interaction state machine (IDLE, APPROACHING, ENGAGED, LEAVING)
    """

    BAUD_RATE = 115200

    _instance = None
    _lock = threading.Lock()

    # Valid state machine labels
    IDLE = "IDLE"
    APPROACHING = "APPROACHING"
    ENGAGED = "ENGAGED"
    LEAVING = "LEAVING"

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        # Prevent __init__ from running twice
        if self._initialized:
            return

        # Storage for serial devices
        self.led_serials = {}       # dict[str, serial.Serial]
        self.motor_serials = {}     # dict[str, serial.Serial]
        self.radar_serial = None    # serial.Serial or None
        self.radar_reader = None    # RadarReader or None

        # Hardware map loaded from hwMap.json
        self.hw_map = []            # list[dict]

        # State machine
        self._state = HWState.IDLE

        self._initialized = True
        info("HWState initialized with state IDLE")

    def load_hw_map(self):
        """Load hwMap.json to understand the peripheral devices connected."""
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        hw_map_path = os.path.join(script_dir, "hw", "hwMap.json")

        try:
            with open(hw_map_path, "r", encoding="utf-8") as f:
                self.hw_map = json.load(f)
        except FileNotFoundError:
            error(f"Could not find hwMap.json at {hw_map_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            error(f"Failed to parse hwMap.json: {e}")
            sys.exit(1)

        if not isinstance(self.hw_map, list):
            error("hwMap.json must contain a top level JSON array")
            sys.exit(1)

        info(f"Loaded hwMap.json with {len(self.hw_map)} entries.")

    def connect_peripherals(self):
        """Probe all /dev/cu.usb* devices, send NAME, and update hw_map.

        Returns a dict mapping board_name -> open serial connection for
        light boards only.
        """
        info("Auto discovering boards")

        potential_ports = glob.glob("/dev/cu.usb*")
        if not potential_ports:
            error("No USB devices found matching /dev/cu.usb*")
            return {}

        info(f"Found {len(potential_ports)} candidate device(s). Probing...")

        board_serials = {}

        for port in potential_ports:
            info(f"Probing {port}...")
            try:
                s = serial.Serial(port, self.BAUD_RATE, timeout=2, write_timeout=1)
            except serial.SerialException as e:
                error(f"Failed to open {port}: {e}")
                continue
            except Exception as e:
                error(f"Unexpected error opening {port}: {e}")
                continue

            # Give the board a moment to boot and clear any noise
            time.sleep(2)
            s.reset_input_buffer()

            # Ask for NAME with clean timeout handling
            try:
                s.write(b"NAME\r\n")
            except serial.SerialTimeoutException as e:
                error(f"Write timeout when sending NAME to {port}: {e}")
                s.close()
                continue
            except Exception as e:
                error(f"Error sending NAME to {port}: {e}")
                s.close()
                continue

            try:
                response = s.readline().decode("ascii", errors="ignore").strip()
            except Exception as e:
                error(f"Error reading NAME response from {port}: {e}")
                s.close()
                continue

            if not response:
                warning(f"No NAME response from {port} (timeout or empty)")
                s.close()
                continue

            hw_entry = self.find_hw_entry_by_name(response)
            if hw_entry is None:
                warning(f"Unrecognized device. NAME='{response}' on {port}")
                s.close()
                continue

            # We have a known board. Update its port in the hw map.
            hw_entry["port"] = port

            info(
                f"Matched board '{response}' to {port} "
                f"(type={hw_entry.get('type', 'unknown')})"
            )

            device_type = hw_entry.get("type")

            if device_type == "light":
                board_serials[response] = s
                self.register_led_serial(response, s)
            elif device_type == "motor":
                board_serials[response] = s
                self.register_motor_serial(response, s)
            elif device_type == "radar":
                board_serials[response] = s
                self.register_radar_serial(response, s)
            else:
                warning(f"Unknown board type '{device_type}' for board '{response}'")
                s.close()

        # Log any boards from hwMap.json that did not get a port assigned
        missing = [e["board_name"] for e in self.hw_map if e.get("port") in (None, "")]
        if missing:
            warning("No connected devices found for boards: " + ", ".join(missing))

        if not board_serials:
            error("No valid light boards found. Exiting.")
            sys.exit(1)

        return board_serials
    
    def register_led_serial(self, name, ser):
        """Register a serial connection belonging to an LED controller board."""
        self.led_serials[name] = ser
        info(f"Registered LED serial '{name}'")

    def register_motor_serial(self, name, ser):
        """Register a serial connection for a motor controller board."""
        self.motor_serials[name] = ser
        info(f"Registered motor serial '{name}'")

    def register_radar_serial(self, name, ser):
        """Register the serial connection for the radar board."""
        self.radar_serial = ser
        info(f"Registered radar serial '{name}'")

    def start_monitoring_radar(self):
        """Create and start a RadarReader if a radar serial device is available."""
        if self.radar_serial is None:
            warning("start_monitoring_radar called but no radar serial is registered")
            return

        if self.radar_reader is not None:
            # Already created, just ensure it is running
            self.radar_reader.start()
            return

        self.radar_reader = RadarReader(self.radar_serial)
        self.radar_reader.start()
        info("Radar monitoring started")

    def stop_monitoring_radar(self):
        """Stop the RadarReader polling loop if it is running."""
        if self.radar_reader is None:
            return

        self.radar_reader.stop()
        info("Radar monitoring stopped")

    def set_state(self, new_state):
        """Update the global behavior state machine."""
        if new_state not in [
            HWState.IDLE,
            HWState.APPROACHING,
            HWState.ENGAGED,
            HWState.LEAVING,
        ]:
            warning(f"Attempted to set invalid HWState '{new_state}'")
            return

        if self._state != new_state:
            info(f"HWState transition: {self._state} → {new_state}")
            self._state = new_state

    def get_state(self):
        """Return the current hardware-wide engagement state."""
        return self._state

    def find_hw_entry_by_name(self, board_name):
        """Return the first hw map entry whose board_name matches, or None."""
        for entry in self.hw_map:
            if entry.get("board_name") == board_name:
                return entry
        return None

    def disconnect_peripherals(self):
        """Close all registered serial devices."""
        # Ensure radar monitoring is stopped before closing serial ports
        self.stop_monitoring_radar()

        for name, ser in list(self.led_serials.items()):
            try:
                if ser.is_open:
                    ser.close()
                info(f"Closed LED serial '{name}'")
            except Exception as e:
                error(f"Error closing LED serial '{name}': {e}")

        for name, ser in list(self.motor_serials.items()):
            try:
                if ser.is_open:
                    ser.close()
                info(f"Closed motor serial '{name}'")
            except Exception as e:
                error(f"Error closing motor serial '{name}': {e}")

        if self.radar_serial is not None:
            try:
                if self.radar_serial.is_open:
                    self.radar_serial.close()
                info("Closed radar serial")
            except Exception as e:
                error(f"Error closing radar serial: {e}")
