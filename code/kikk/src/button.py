"""Hardware button watcher via Linux input event device.

Reads raw evdev events from BUTTON_EVENT_PATH.
Calls on_pick_up() when the handset is lifted, on_hang_up() when replaced.

Phone hook switch logic (normally-open circuit):
  value 0 = key released = circuit closed  = pick-up
  value 1 = key pressed  = circuit open    = hang-up
  value 2 = auto-repeat  = ignored

Run with sufficient permissions:
  sudo python3 main.py
  or: sudo usermod -aG input $USER  (then re-login)

DEV_MODE: set BUTTON_EVENT_PATH = "keyboard" in config to use spacebar instead.
"""
from __future__ import annotations

import asyncio
import struct
import sys
from typing import Callable

from src.config import BUTTON_EVENT_PATH

# struct input_event { timeval (8+8 bytes), type (2), code (2), value (4) }
EVENT_FORMAT = "llHHi"
EVENT_SIZE   = struct.calcsize(EVENT_FORMAT)
EV_KEY       = 1


async def watch_button(
    on_pick_up: Callable[[], None],
    on_hang_up: Callable[[], None],
) -> None:
    """
    Watches the button event device (or spacebar in dev mode) forever.
    Runs until cancelled.
    """
    if BUTTON_EVENT_PATH == "keyboard":
        await _watch_spacebar(on_pick_up, on_hang_up)
    else:
        await _watch_hardware(on_pick_up, on_hang_up)


# ── Hardware button ───────────────────────────────────────────────────────────

async def _watch_hardware(
    on_pick_up: Callable[[], None],
    on_hang_up: Callable[[], None],
) -> None:
    print(f"[button] watching {BUTTON_EVENT_PATH}")
    loop    = asyncio.get_running_loop()
    pressed = False
    buf     = b""

    try:
        fd = open(BUTTON_EVENT_PATH, "rb", buffering=0)
    except OSError as e:
        print(f"[button] cannot open {BUTTON_EVENT_PATH}: {e}")
        print("[button] try: sudo python3 main.py  or  sudo usermod -aG input $USER")
        raise

    try:
        reader = asyncio.StreamReader()
        await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), fd)

        while True:
            chunk = await reader.read(EVENT_SIZE * 8)
            if not chunk:
                break
            buf += chunk
            while len(buf) >= EVENT_SIZE:
                event = buf[:EVENT_SIZE]
                buf   = buf[EVENT_SIZE:]
                _, _, ev_type, _code, value = struct.unpack(EVENT_FORMAT, event)
                if ev_type != EV_KEY:
                    continue
                if value == 0 and not pressed:
                    pressed = True
                    print("[button] ↑ pick-up")
                    on_pick_up()
                elif value == 1 and pressed:
                    pressed = False
                    print("[button] ↓ hang-up")
                    on_hang_up()
    finally:
        fd.close()


# ── Spacebar (dev mode) ───────────────────────────────────────────────────────

async def _watch_spacebar(
    on_pick_up: Callable[[], None],
    on_hang_up: Callable[[], None],
) -> None:
    """Toggle pick-up / hang-up with the spacebar. Ctrl+C to quit."""
    print("[button] DEV MODE — press SPACE to pick up / hang up, Ctrl+C to quit")

    loop    = asyncio.get_running_loop()
    active  = False
    queue: asyncio.Queue[str] = asyncio.Queue()

    def _read_stdin():
        import tty, termios
        fd   = sys.stdin.fileno()
        old  = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while True:
                ch = sys.stdin.read(1)
                loop.call_soon_threadsafe(queue.put_nowait, ch)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    import threading
    t = threading.Thread(target=_read_stdin, daemon=True)
    t.start()

    while True:
        ch = await queue.get()

        if ch == '\x03':  # Ctrl+C
            print("\n[button] Ctrl+C — exiting")
            raise KeyboardInterrupt

        if ch == ' ':
            if not active:
                active = True
                print("[button] ↑ pick-up  (press space to hang up)")
                on_pick_up()
            else:
                active = False
                print("[button] ↓ hang-up  (press space to pick up)")
                on_hang_up()