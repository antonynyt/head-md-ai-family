#!/usr/bin/env python3
"""Thermal printer support for Familect.

Talks to an Adafruit-style thermal printer on the Pi's hardware UART
(GPIO 14 TX / GPIO 15 RX) at /dev/serial0, 19200 baud.

Install: pip install pyserial
Enable UART: sudo raspi-config → Interface Options → Serial Port
  - Login shell over serial: No
  - Serial port hardware enabled: Yes
"""
from __future__ import annotations

import textwrap
import time

try:
    import serial
except ImportError:
    serial = None  # type: ignore

# ── Printer config ────────────────────────────────────────────────────────────
PRINTER_PORT  = "/dev/serial0"
PRINTER_BAUD  = 19200
PRINT_WIDTH   = 32   # characters per line (typical for 58 mm paper)

# ESC/POS commands
ESC = b"\x1b"
GS  = b"\x1d"

CMD_INIT        = ESC + b"@"         # initialise printer
CMD_BOLD_ON     = ESC + b"E\x01"
CMD_BOLD_OFF    = ESC + b"E\x00"
CMD_ALIGN_CTR   = ESC + b"a\x01"
CMD_ALIGN_LEFT  = ESC + b"a\x00"
CMD_FEED        = ESC + b"d"         # feed N lines (append N as byte)
CMD_CUT         = GS  + b"V\x41\x10" # partial cut with feed


def _open_printer() -> "serial.Serial | None":
    if serial is None:
        print("[printer] pyserial not installed — skipping print")
        return None
    try:
        p = serial.Serial(PRINTER_PORT, PRINTER_BAUD, timeout=2)
        time.sleep(0.1)
        return p
    except Exception as e:
        print(f"[printer] Could not open {PRINTER_PORT}: {e}")
        return None


def _write(p: "serial.Serial", data: bytes) -> None:
    p.write(data)
    p.flush()


def _line(p: "serial.Serial", text: str = "", bold: bool = False) -> None:
    if bold:
        _write(p, CMD_BOLD_ON)
    for chunk in textwrap.wrap(text, PRINT_WIDTH) or [""]:
        _write(p, chunk.encode("utf-8", errors="replace") + b"\n")
    if bold:
        _write(p, CMD_BOLD_OFF)


def _divider(p: "serial.Serial") -> None:
    _write(p, (("─" * PRINT_WIDTH) + "\n").encode("utf-8", errors="replace"))


def print_word(entry: dict) -> None:
    """Print a single Familect entry. entry must have word, definition,
    added_by, created_at, and optionally story."""
    p = _open_printer()
    if p is None:
        return

    try:
        _write(p, CMD_INIT)

        # Word
        _line(p, entry.get("word", "").upper(), bold=True)

        # Definition
        _line(p, entry.get("definition", ""))

        # Story (optional)
        if story := entry.get("story", "").strip():
            _write(p, b"\n")
            _line(p, f"« {story} »")

        # Footer: when
        _divider(p)
        created_at = entry.get("created_at", "")
        if created_at:
            # Format: "2026-03-12"
            date_str = created_at[:10]
            _line(p, f"{date_str}")

        # Feed and cut
        _write(p, CMD_FEED + b"\x04")
        _write(p, CMD_CUT)

        print(f"[printer] Printed: {entry.get('word')!r}")
    except Exception as e:
        print(f"[printer] Print error: {e}")
    finally:
        p.close()