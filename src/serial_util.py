import glob
import time

try:
    import serial  # pyserial
except ImportError:
    print("pyserial not installed. Install with: python3 -m pip install pyserial", file=sys.stderr)
    sys.exit(2)

SERIAL_BAUD_RATE = 115200

def serial_util_list_devices() -> list[str]:
    pats = [
        "/dev/tty.usb*",
    ]
    ports = []
    for p in pats:
        ports.extend(glob.glob(p))
    return sorted(set(ports))


def serial_util_send_command(port: str, baud: int, timeout: float, command: str) -> str:
    """Send a single-line command and return one reply line (stripped)."""
    with serial.Serial(port, baudrate=baud, timeout=timeout) as ser:
        time.sleep(0.1)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        ser.write((command.strip() + "\n").encode())
        ser.flush()

        # Read one reply line
        line = ser.readline().decode(errors="ignore").strip()
        return line
