import glob
import time
import sys

try:
    import serial
except ImportError:
    print("pyserial not installed. Install with: python3 -m pip install pyserial", file=sys.stderr)
    sys.exit(2)

SERIAL_BAUD_RATE = 115200

# Persistent sessions so we avoid resetting the Arduino by re-opening the port each command.
DEFAULT_STARTUP_DELAY_S = 0.25

class SerialSession:
    _pool: dict[str, "SerialSession"] = {}

    def __init__(self, port: str, baud: int = SERIAL_BAUD_RATE, timeout: float = 1.0, startup_delay: float = DEFAULT_STARTUP_DELAY_S):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.startup_delay = startup_delay
        self.ser: serial.Serial | None = None

    def open(self) -> None:
        if self.ser and self.ser.is_open:
            return
        self.ser = serial.Serial(self.port, baudrate=self.baud, timeout=self.timeout, exclusive=True)
        # Do not clear input: we want to capture early READY banners.
        # Only clear any pending host-side output.
        self.ser.reset_output_buffer()

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            try:
                self.ser.flush()
            except Exception:
                pass
            self.ser.close()

    def send_command(self, command: str, read_reply: bool = True) -> str:
        if not self.ser or not self.ser.is_open:
            self.open()
        assert self.ser is not None
        self.ser.write((command.strip() + "\n").encode())
        self.ser.flush()
        if not read_reply:
            return ""
        line = self.ser.readline().decode(errors="ignore").strip()
        return line

    def wait_for(self, token: str, max_seconds: float = 5.0) -> bool:
        if not self.ser or not self.ser.is_open:
            self.open()
        assert self.ser is not None
        deadline = time.time() + max_seconds
        # Poll quickly for the token with short sleeps to minimize latency.
        while time.time() < deadline:
            if self.ser.in_waiting:
                line = self.ser.readline().decode(errors="ignore").strip()
                if token in line:
                    return True
            else:
                # Small nap avoids busy-wait while keeping responsiveness
                time.sleep(0.01)
        return False

    @classmethod
    def connect(cls, port: str, baud: int = SERIAL_BAUD_RATE, timeout: float = 1.0, *, ready_token: str = "READY", startup_delay: float = DEFAULT_STARTUP_DELAY_S, ready_timeout: float = 5.0) -> "SerialSession":
        """Open (and cache) a persistent connection and optionally wait for a READY token.
        Returns the connected SerialSession (cached by port).
        """
        sess = cls._pool.get(port)
        if sess is None:
            sess = cls(port, baud=baud, timeout=timeout, startup_delay=startup_delay)
            sess.open()
            cls._pool[port] = sess
        if ready_token:
            sess.wait_for(ready_token, max_seconds=ready_timeout)
        return sess

    @classmethod
    def get(cls, port: str) -> "SerialSession | None":
        """Return an existing cached session for the port, if any."""
        return cls._pool.get(port)

    def disconnect(self) -> None:
        """Close this session and remove it from the cache if it is the cached instance."""
        self.close()
        # Remove from pool only if it matches the cached object
        if self.__class__._pool.get(self.port) is self:
            self.__class__._pool.pop(self.port, None)

    @classmethod
    def disconnect_all(cls) -> None:
        """Disconnect all cached sessions."""
        for p, sess in list(cls._pool.items()):
            try:
                sess.close()
            finally:
                cls._pool.pop(p, None)


def serial_util_list_devices() -> list[str]:
    pats = [
        "/dev/tty.usb*",
    ]
    ports = []
    for p in pats:
        ports.extend(glob.glob(p))
    return sorted(set(ports))
