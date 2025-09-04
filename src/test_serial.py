#!/usr/bin/env python3

from serial_util import serial_util_list_devices, serial_util_send_command, SERIAL_BAUD_RATE

"""
test_serial.py
List all /dev/tty.usb* devices, probe each with NAME commands, and print a table.
Non-responders are shown as *UNKNOWN*.

Usage examples:
  python3 test_serial.py

The Arduino sketch should answer:
  NAME -> <device name>
"""

def probe_name(port: str) -> str:
    """send NAME and return it or *UNKNOWN* if empty.
    On failure, return *UNKNOWN* or *ERROR* with exception class name."""
    try:
        name = serial_util_send_command(port, SERIAL_BAUD_RATE, 1.0, "NAME").strip()
        return name if name else "*UNKNOWN*"
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
    rows = []
    for port in serial_util_list_devices():
        name = probe_name(port)
        rows.append([port, name])

    print_table(rows)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())