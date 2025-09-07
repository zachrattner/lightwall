#!/usr/bin/env python3

from serial_util import serial_util_list_devices, SerialSession, SERIAL_BAUD_RATE
import logger
import sys

"""
test_serial.py
List all /dev/tty.usb* devices, probe each with NAME commands, and print a table.
Non-responders are shown as *UNKNOWN*.

Usage examples:
  python3 test_serial.py

The client now uses SerialSession and waits for READY before sending commands.

The Arduino sketch should answer:
  NAME -> <device name>
"""

VERBOSE = False

def probe_name(port: str) -> str:
    """Open a SerialSession, wait for READY, send NAME, and return the reply.
    Returns *UNKNOWN* if no reply. On failure, returns *ERROR* <ExcName>.
    """
    try:
        if VERBOSE: logger.info(f"Probing {port}")
        sess = SerialSession.connect(
            port,
            baud=SERIAL_BAUD_RATE,
            timeout=1.0,
            ready_token="READY",
            ready_timeout=5.0,
        )
        if VERBOSE: logger.info(f"Connected to {port}")
        name = sess.send_command("NAME", read_reply=True).strip()
        if VERBOSE: logger.info(f"Got NAME reply='{name}'")
        return name if name else "*UNKNOWN*"
    except Exception as e:
        logger.error(f"Probe failed for {port}: {e}")
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
    global VERBOSE
    VERBOSE = "--verbose" in sys.argv
    if VERBOSE:
        sys.argv.remove("--verbose")
    if VERBOSE: logger.info("Starting serial probe")
    rows = []
    for port in serial_util_list_devices():
        name = probe_name(port)
        if VERBOSE: logger.info(f"Port {port} identified as {name}")
        rows.append([port, name])

    print_table(rows)
    if VERBOSE: logger.info("Disconnecting all sessions")
    SerialSession.disconnect_all()
    if VERBOSE: logger.info("Probe complete")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())