#!/usr/bin/env python3

from serial_util import serial_util_list_devices, serial_util_send_command, SERIAL_BAUD_RATE

"""
nano_every_serial.py
List all /dev/tty.usb* devices, probe each with PING/NAME commands, and print a table.
Non-responders are shown as *UNKNOWN*.

Usage examples:
  python3 nano_every_serial.py                # list devices with default baud and timeout
  python3 nano_every_serial.py --baud 9600    # specify baud rate
  python3 nano_every_serial.py --timeout 0.5 # specify timeout seconds

The Arduino sketch should answer:
  PING -> PONG
  NAME -> <device name>
"""

import argparse
import sys

try:
    import serial  # pyserial
except ImportError:
    print("pyserial not installed. Install with: python3 -m pip install pyserial", file=sys.stderr)
    sys.exit(2)

def probe_name(port: str, baud: int, timeout: float) -> str:
    """Send PING; if reply is PONG, send NAME and return it or *UNKNOWN* if empty.
    On failure, return *UNKNOWN* or *ERROR* with exception class name."""
    try:
        reply = serial_util_send_command(port, baud, timeout, "PING")
        if reply.strip().upper() == "PONG":
            name = serial_util_send_command(port, baud, timeout, "NAME").strip()
            return name if name else "*UNKNOWN*"
        else:
            return "*UNKNOWN*"
    except Exception as e:
        return f"*ERROR* {e.__class__.__name__}"

def print_table(rows: list[list[str]]) -> None:
    """Print a table with headers DEVICE and NAME."""
    device_col = "DEVICE"
    name_col = "NAME"
    all_rows = [[device_col, name_col]] + rows
    # Compute max widths per column
    widths = [max(len(row[i]) for row in all_rows) for i in range(2)]
    # Print header
    print(f"{device_col:<{widths[0]}}  {name_col:<{widths[1]}}")
    print(f"{'-'*widths[0]}  {'-'*widths[1]}")
    # Print rows
    for device, name in rows:
        print(f"{device:<{widths[0]}}  {name:<{widths[1]}}")

def main() -> int:
    ap = argparse.ArgumentParser(description="List and probe serial devices with PING/NAME commands.")
    ap.add_argument("--baud", "-b", type=int, default=SERIAL_BAUD_RATE, help="Baud rate (default 115200)")
    ap.add_argument("--timeout", "-t", type=float, default=1.0, help="Serial read timeout seconds")
    args = ap.parse_args()

    rows = []
    for port in serial_util_list_devices():
        name = probe_name(port, args.baud, args.timeout)
        rows.append([port, name])

    print_table(rows)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())