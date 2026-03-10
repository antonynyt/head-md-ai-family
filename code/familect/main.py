#!/usr/bin/env python3
"""Main entry point for Familect.

Waits for:
  1. The button on GPIO 17 to be released.
  2. A specific NFC tag to be present at the reader.

When both conditions are met, voice-chat.py is launched as a subprocess.
The voice chat is stopped when the button is pressed or the NFC tag is removed.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import asyncio

try:
    import board
    import busio
    from adafruit_pn532.i2c import PN532_I2C
    from gpiozero import Button
except ImportError as exc:
    print(f"Missing dependency: {exc}\nInstall: pip install gpiozero adafruit-circuitpython-pn532", file=sys.stderr)
    raise SystemExit(1)

# ── Configuration ─────────────────────────────────────────────────────────────
BUTTON_GPIO_PIN = 17

# The UID of the authorised NFC tag as a tuple of ints.
# Replace with your own tag's UID (printed by nfc-test.py, e.g. [0x04, 0xab, 0x12, 0x34]).
ALLOWED_NFC_UID: tuple[int, ...] = (0x4, 0x3e, 0x84, 0xa2, 0x1f, 0x1d, 0x91)

# How long (seconds) the NFC reader polls for a tag before giving up.
NFC_TIMEOUT = 0.5

# Path to voice-chat.py (resolved relative to this file so it works from any cwd).
VOICE_CHAT_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice-chat.py")


def init_nfc() -> PN532_I2C:
    i2c = busio.I2C(board.SCL, board.SDA)
    pn532 = PN532_I2C(i2c, debug=False)
    ic, ver, rev, _ = pn532.firmware_version
    print(f"[NFC] PN532 firmware {ver}.{rev} ready")
    pn532.SAM_configuration()
    return pn532


def read_uid(pn532: PN532_I2C) -> tuple[int, ...] | None:
    uid = pn532.read_passive_target(timeout=NFC_TIMEOUT)
    if uid is None:
        return None
    return tuple(uid)


# How many consecutive NFC misses before we consider the tag removed.
# Each miss takes NFC_TIMEOUT seconds, so 2 × 0.5 s = 1 s of no tag → stop.
NFC_MISS_LIMIT = 2


def monitor_and_stop(proc: subprocess.Popen, button: "Button", pn532: PN532_I2C) -> str:
    """Poll button and NFC while voice-chat is running; terminate proc when needed.

    Returns a string describing the reason the session ended.
    """
    consecutive_misses = 0
    while proc.poll() is None:          # loop until the process exits on its own
        # ── Stop condition 1: button pressed ─────────────────────────────────
        if button.is_pressed:
            print("[main] Button pressed — stopping voice chat …")
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            return "button"

        # ── Stop condition 2: NFC tag removed ────────────────────────────────
        uid = read_uid(pn532)
        if uid != ALLOWED_NFC_UID:
            consecutive_misses += 1
            if consecutive_misses >= NFC_MISS_LIMIT:
                print("[main] NFC tag removed — sending farewell signal …")
                os.kill(proc.pid, signal.SIGUSR1)
                try:
                    # Allow up to 15 s for the AI to say goodbye and the process to exit
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    print("[main] Farewell timed out — force killing …")
                    proc.kill()
                    proc.wait()
                return "nfc"
        else:
            consecutive_misses = 0

    return "exited"


def main() -> int:
    button = Button(BUTTON_GPIO_PIN, pull_up=True)
    pn532  = init_nfc()

    print("[main] Waiting for button release + authorised NFC tag …")
    print(f"[main] Authorised UID: {[hex(b) for b in ALLOWED_NFC_UID]}")

    while True:
        # ── Condition 1: button must have been released (not currently held) ──
        if button.is_pressed:
            time.sleep(0.05)
            continue

        # ── Condition 2: correct NFC tag must be present ──────────────────────
        uid = read_uid(pn532)
        if uid is None:
            continue

        if uid != ALLOWED_NFC_UID:
            print(f"[main] Unknown tag: {[hex(b) for b in uid]} — ignoring")
            continue

        print(f"[main] Authorised tag detected: {[hex(b) for b in uid]}")

        # Both conditions met → start voice chat
        print("[main] Launching voice-chat.py …")
        proc = subprocess.Popen([sys.executable, VOICE_CHAT_SCRIPT])
        reason = monitor_and_stop(proc, button, pn532)

        print(f"[main] voice-chat ended ({reason}) — waiting for next activation …")

        # If stopped by button press, wait until released before re-arming
        if reason == "button":
            while button.is_pressed:
                time.sleep(0.05)


if __name__ == "__main__":
    raise SystemExit(main())
