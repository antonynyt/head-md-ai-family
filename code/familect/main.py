#!/usr/bin/env python3
"""Main entry point for Familect.

Waits for:
  1. The button on GPIO 17 to be released.
  2. A known NFC tag to be present at the reader.

When both conditions are met, voice-chat.py is launched.
The session stops when the button is pressed or the NFC tag is removed.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time

try:
    import board
    import busio
    from adafruit_pn532.adafruit_pn532 import MIFARE_CMD_AUTH_B
    from adafruit_pn532.i2c import PN532_I2C
    from gpiozero import Button
except ImportError as exc:
    print(f"Missing dependency: {exc}\nInstall: pip install gpiozero adafruit-circuitpython-pn532", file=sys.stderr)
    raise SystemExit(1)

# ── Configuration ─────────────────────────────────────────────────────────────
HERE            = os.path.dirname(os.path.abspath(__file__))
BUTTON_GPIO_PIN = 17
NFC_TIMEOUT     = 0.5   # seconds per NFC poll
NFC_MISS_LIMIT  = 20    # consecutive misses before tag is considered removed (20 × 0.5 s = 10 s)

VOICE_CHAT_SCRIPT = os.path.join(HERE, "voice-chat.py")
PROMPTS_DIR       = os.path.join(HERE, "prompts")
DEFAULT_PROMPT    = os.path.join(HERE, "prompt.txt")
MIFARE_DEFAULT_KEY = b"\xff\xff\xff\xff\xff\xff"

# Map NFC tag UID → (person name, prompt file).
# Add one entry per family member tag.
TAG_PROFILES: dict[tuple[int, ...], tuple[str, str]] = {
    (0x4, 0x3E, 0x84, 0xA2, 0x1F, 0x1D, 0x91): ("Baptiste", DEFAULT_PROMPT),
    # (0x4, 0xAB, 0xCD, ...): ("Marie", os.path.join(PROMPTS_DIR, "marie.txt")),
}


# ── NFC helpers ───────────────────────────────────────────────────────────────

def init_nfc() -> PN532_I2C:
    for attempt in range(1, 6):
        try:
            i2c   = busio.I2C(board.SCL, board.SDA)
            pn532 = PN532_I2C(i2c, debug=False)
            _, ver, rev, _ = pn532.firmware_version
            print(f"[NFC] PN532 firmware {ver}.{rev} ready")
            pn532.SAM_configuration()
            return pn532
        except (RuntimeError, ValueError) as e:
            print(f"[NFC] Init attempt {attempt}/5 failed: {e} — retrying in 2 s …")
            time.sleep(2)
    raise RuntimeError("[NFC] Could not initialise PN532 after 5 attempts")


def read_uid(pn532: PN532_I2C) -> tuple[int, ...] | None:
    uid = pn532.read_passive_target(timeout=NFC_TIMEOUT)
    return tuple(uid) if uid is not None else None


def _decode_text_payload(raw: bytes) -> str | None:
    text = raw.split(b"\x00", 1)[0].split(b"\xfe", 1)[0].decode("utf-8", errors="ignore").strip()
    return text or None


def _parse_ndef_text(payload: bytes) -> str | None:
    if not payload:
        return None
    i = 0
    while i < len(payload):
        tlv_type = payload[i]; i += 1
        if tlv_type == 0x00:
            continue
        if tlv_type == 0xFE:
            break
        if i >= len(payload):
            break
        length = payload[i]; i += 1
        if length == 0xFF:
            if i + 1 >= len(payload):
                break
            length = (payload[i] << 8) | payload[i + 1]; i += 2
        value = payload[i : i + length]; i += length
        if tlv_type != 0x03 or len(value) < 4:
            continue
        header       = value[0]
        short_record = bool(header & 0x10)
        il_flag      = bool(header & 0x08)
        type_length  = value[1]
        pos = 2
        if short_record:
            if pos >= len(value): return None
            payload_length = value[pos]; pos += 1
        else:
            if pos + 3 >= len(value): return None
            payload_length = int.from_bytes(value[pos : pos + 4], "big"); pos += 4
        id_length = 0
        if il_flag:
            if pos >= len(value): return None
            id_length = value[pos]; pos += 1
        record_type    = value[pos : pos + type_length]; pos += type_length + id_length
        record_payload = value[pos : pos + payload_length]
        if record_type != b"T" or len(record_payload) < 1:
            continue
        lang_len = record_payload[0] & 0x3F
        text = record_payload[1 + lang_len :].decode("utf-8", errors="ignore").strip()
        return text or None
    return None


def _read_slug_from_ntag(pn532: PN532_I2C) -> str | None:
    raw = bytearray()
    for page in range(4, 40):
        data = pn532.ntag2xx_read_block(page)
        if data is None:
            break
        raw.extend(data)
    return _parse_ndef_text(bytes(raw)) or _decode_text_payload(bytes(raw))


def _read_slug_from_mifare(pn532: PN532_I2C, uid: tuple[int, ...]) -> str | None:
    if len(uid) != 4:
        return None
    if not pn532.mifare_classic_authenticate_block(uid, 4, MIFARE_CMD_AUTH_B, MIFARE_DEFAULT_KEY):
        return None
    raw = bytearray()
    for block in (4, 5, 6):
        data = pn532.mifare_classic_read_block(block)
        if data is None:
            return None
        raw.extend(data)
    return _parse_ndef_text(bytes(raw)) or _decode_text_payload(bytes(raw))


def read_tag_slug(pn532: PN532_I2C, uid: tuple[int, ...]) -> str | None:
    slug = _read_slug_from_ntag(pn532) or _read_slug_from_mifare(pn532, uid)
    return slug.strip() if slug else None


def resolve_profile(pn532: PN532_I2C, uid: tuple[int, ...]) -> tuple[str, str] | None:
    """Return (person, prompt_file) for a tag, or None if unrecognised."""
    # Try reading a 'model:value' slug from the tag first
    slug = read_tag_slug(pn532, uid)
    if slug:
        lowered = slug.lower()
        if lowered.startswith("model:"):
            profile = re.sub(r"[^a-z0-9_-]", "", lowered[6:].strip())
            if profile:
                prompt_file = os.path.join(PROMPTS_DIR, f"{profile}.txt")
                # Look up person by UID, fall back to "Unknown"
                person = TAG_PROFILES.get(uid, ("Unknown", ""))[0]
                print(f"[main] Tag slug: {slug!r} → {prompt_file}")
                return person, prompt_file
        print(f"[main] Ignoring unsupported tag slug: {slug!r}")

    # Fall back to UID lookup
    return TAG_PROFILES.get(uid)


# ── Session management ────────────────────────────────────────────────────────

def monitor_and_stop(proc: subprocess.Popen, button: Button, pn532: PN532_I2C, active_uid: tuple[int, ...]) -> str:
    """Poll button and NFC while voice-chat is running. Returns reason for stopping."""
    consecutive_misses = 0
    while proc.poll() is None:
        if button.is_pressed:
            print("[main] Button pressed — stopping …")
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            return "button"

        uid = read_uid(pn532)
        if uid != active_uid:
            consecutive_misses += 1
            if consecutive_misses >= NFC_MISS_LIMIT:
                print("[main] NFC tag removed — sending farewell signal …")
                os.kill(proc.pid, signal.SIGUSR1)
                try:
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

    print("[main] Waiting for button release + known NFC tag …")

    while True:
        if button.is_pressed:
            time.sleep(0.05)
            continue

        uid = read_uid(pn532)
        if uid is None:
            continue

        profile = resolve_profile(pn532, uid)
        if not profile:
            print(f"[main] Unknown tag: {[hex(b) for b in uid]} — ignoring")
            continue

        person, prompt_file = profile

        if not os.path.exists(prompt_file):
            print(f"[main] Prompt file missing: {prompt_file}")
            continue

        print(f"[main] Tag: {[hex(b) for b in uid]} → {person} / {prompt_file}")
        print("[main] Launching voice-chat.py …")

        proc = subprocess.Popen([
            sys.executable, VOICE_CHAT_SCRIPT,
            "--prompt-file", prompt_file,
            "--person", person,
        ])
        reason = monitor_and_stop(proc, button, pn532, uid)
        print(f"[main] Session ended ({reason}) — waiting for next activation …")

        if reason == "button":
            while button.is_pressed:
                time.sleep(0.05)


if __name__ == "__main__":
    raise SystemExit(main())