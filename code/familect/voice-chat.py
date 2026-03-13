#!/usr/bin/env python3
"""Real-time Gemini voice — Raspberry Pi edition.

Uses ALSA devices 'mic_sv' (input) and 'spk_sv' (output).
Hardware: 48 kHz stereo int32. Gemini: 16 kHz mono int16 in, 24 kHz mono int16 out.

Usage:
  export GEMINI_API_KEY="your_key"
  python3 voice-chat.py --prompt-file prompts/french.txt --person "Baptiste"
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from datetime import datetime, timezone
import json
import os
import signal
import sys
import threading
import time

try:
    import numpy as np
    import sounddevice as sd
    import websockets
except ImportError as exc:
    print(f"Missing: {exc}\nInstall: pip install websockets sounddevice numpy", file=sys.stderr)
    raise SystemExit(1)

try:
    import serial as _serial
except ImportError:
    _serial = None

try:
    import ctypes, ctypes.util

    _speex_lib_path = ctypes.util.find_library("speexdsp") or "libspeexdsp.so.1"
    _lib = ctypes.CDLL(_speex_lib_path)

    _lib.speex_echo_state_init.restype  = ctypes.c_void_p
    _lib.speex_echo_state_init.argtypes = [ctypes.c_int, ctypes.c_int]
    _lib.speex_echo_cancellation.restype  = None
    _lib.speex_echo_cancellation.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int16),
        ctypes.POINTER(ctypes.c_int16),
        ctypes.POINTER(ctypes.c_int16),
    ]
    _lib.speex_echo_state_destroy.restype  = None
    _lib.speex_echo_state_destroy.argtypes = [ctypes.c_void_p]

    class _EchoCanceller:
        def __init__(self, frame_size: int, filter_length: int, _rate: int) -> None:
            self._frame_size = frame_size
            self._st = _lib.speex_echo_state_init(frame_size, filter_length)
            if not self._st:
                raise RuntimeError("speex_echo_state_init returned NULL")

        def process(self, mic: bytes, ref: bytes) -> bytes:
            n = self._frame_size
            Int16Arr = ctypes.c_int16 * n
            mic_arr = Int16Arr.from_buffer_copy(mic)
            ref_arr = Int16Arr.from_buffer_copy(ref)
            out_arr = Int16Arr()
            _lib.speex_echo_cancellation(self._st, mic_arr, ref_arr, out_arr)
            return bytes(out_arr)

        def __del__(self):
            if self._st:
                _lib.speex_echo_state_destroy(self._st)

    print("[aec] Using libspeexdsp via ctypes")

except Exception as _aec_err:
    _EchoCanceller = None
    print(f"[aec] Not available: {_aec_err}")

MODEL  = "models/gemini-2.5-flash-native-audio-preview-12-2025"
WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)

# ── Pi hardware ───────────────────────────────────────────────────────────────
HW_RATE     = 48_000
HW_CHANNELS = 2
HW_DTYPE    = "int32"
MIC_DEVICE  = "mic_sv"
SPK_DEVICE  = "spk_sv"
SPK_UP      = 2           # nearest-neighbour ×2 upsample 24 kHz → 48 kHz
INT32_MAX   = 2_147_483_647.0

# Energy threshold — only used to track last speech time for silence monitor.
MIC_THRESHOLD = 0.1

# ── Acoustic echo cancellation ────────────────────────────────────────────────
AEC_FRAME  = 160   # 10 ms at 16 kHz
AEC_FILTER = 2048  # echo tail length in samples (~128 ms)
AEC_DELAY  = 320   # acoustic path delay compensation in samples (~20 ms) — tune this

# ── Paths ─────────────────────────────────────────────────────────────────────
HERE          = os.path.dirname(os.path.abspath(__file__))
FAMILECT_PATH = os.path.join(HERE, "familect.json")
DEFAULT_PROMPT = os.path.join(HERE, "prompt.txt")

# ── Thermal printer (GPIO 14/15, /dev/serial0) ───────────────────────────────
PRINTER_PORT  = "/dev/serial0"
PRINTER_BAUD  = 19200
PRINT_WIDTH   = 32

_ESC = b"\x1b"
_GS  = b"\x1d"


def _to_cp437(text: str) -> bytes:
    """Encode text to CP437 bytes, mapping common French accented characters."""
    CP437 = {
        'é': 0x82, 'â': 0x83, 'ä': 0x84, 'à': 0x85, 'ç': 0x87,
        'ê': 0x88, 'ë': 0x89, 'è': 0x8A, 'ï': 0x8B, 'î': 0x8C,
        'ô': 0x93, 'ö': 0x94, 'û': 0x96, 'ù': 0x97, 'ü': 0x81,
        'É': 0x90, 'Ä': 0x8E, 'Ö': 0x99, 'Ü': 0x9A,
        '\u2019': 0x27,  # right single quote → apostrophe
    }
    out = bytearray()
    for ch in text:
        if ch in CP437:
            out.append(CP437[ch])
        elif ord(ch) < 128:
            out.append(ord(ch))
        else:
            out.append(ord('?'))
    return bytes(out)


def print_word(entry: dict) -> None:
    """Print a Familect entry on the thermal printer."""
    if _serial is None:
        print("[printer] pyserial not installed — skipping (pip install pyserial)")
        return
    try:
        import textwrap
        p = _serial.Serial(PRINTER_PORT, PRINTER_BAUD, timeout=2)
        time.sleep(0.1)

        def w(data: bytes) -> None:
            p.write(data); p.flush()

        def line(text: str = "", bold: bool = False) -> None:
            if bold: w(_ESC + b"E\x01")
            for chunk in textwrap.wrap(text, PRINT_WIDTH) or [""]:
                w(_to_cp437(chunk) + b"\n")
            if bold: w(_ESC + b"E\x00")

        def divider() -> None:
            w(b"-" * PRINT_WIDTH + b"\n")

        w(_ESC + b"@")                    # init
        w(_ESC + b"a\x00")               # left align
        divider()
        line(entry.get("word", "").upper(), bold=True)
        line(entry.get("definition", ""))
        if story := entry.get("story", "").strip():
            w(b"\n")
            line(f'"{story}"')
        divider()
        added_by = entry.get("added_by", "?")
        date_str = entry.get("created_at", "")[:10]
        line(f"{added_by} - {date_str}" if date_str else added_by)
        w(_ESC + b"d\x04")               # feed 4 lines
        w(_GS  + b"V\x41\x10")           # partial cut
        p.close()
        print(f"[printer] Printed: {entry.get('word')!r}")
    except Exception as e:
        print(f"[printer] Error: {e}")
_TOOLS = {
    "function_declarations": [
        {
            "name": "save_word",
            "description": "Save a new family word or expression to the Familect dictionary.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "word":       {"type": "STRING", "description": "The word or expression."},
                    "definition": {"type": "STRING", "description": "What it means."},
                    "story":      {"type": "STRING", "description": "Optional origin story or anecdote."},
                },
                "required": ["word", "definition"],
            },
        },
        {
            "name": "end_conversation",
            "description": "Call this after you have said a warm goodbye to end the session.",
            "parameters": {"type": "OBJECT", "properties": {}},
        },
    ]
}

_SYSTEM_SUFFIX = (
    "\n\nYou manage a family dictionary called Familect. "
    "When the user shares or defines a new family word, call save_word immediately — do not describe it, just call it. "
    "At the start only mention the total word count, never list words unprompted. "
    "If asked about existing words, describe them fully. "
    "After saving a word ask: 'Would you like to add another word, or are we done?' "
    "When the conversation is finished and you have said a warm goodbye, call end_conversation."
)


class FarewellComplete(Exception):
    """Session ended cleanly."""


# ── Familect helpers ──────────────────────────────────────────────────────────

def load_entries() -> list[dict]:
    try:
        with open(FAMILECT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def init_familect_file() -> None:
    if not os.path.exists(FAMILECT_PATH):
        with open(FAMILECT_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2, ensure_ascii=False)
        print(f"[familect] Created {FAMILECT_PATH}")


def save_entry(args: dict, added_by: str) -> None:
    word = args.get("word", "").strip()
    if not word:
        return
    entries = load_entries()
    entry: dict = {
        "word":       word,
        "definition": args.get("definition", ""),
        "added_by":   added_by,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if story := args.get("story", "").strip():
        entry["story"] = story
    entries.append(entry)
    with open(FAMILECT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    print(f"[familect] Saved: {entry}")
    print_word(entry)


def build_dictionary_context() -> str:
    entries = load_entries()
    if not entries:
        return "The dictionary is currently empty."
    lines = [f"The dictionary holds {len(entries)} word(s):"]
    for e in entries:
        line = f"- {e['word']} (added by {e.get('added_by', '?')}): {e.get('definition', '')}"
        if e.get("story"):
            line += f" — {e['story']}"
        lines.append(line)
    return "\n".join(lines)


def load_prompt(prompt_file: str) -> str:
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            template = f.read().strip()
    except FileNotFoundError:
        template = ""
    context = build_dictionary_context()
    if "{{FAMILECT_STATS}}" in template:
        return template.replace("{{FAMILECT_STATS}}", context)
    return template.rstrip() + "\n\n" + context


# ── VoiceClient ───────────────────────────────────────────────────────────────

class VoiceClient:
    def __init__(self, api_key: str, system_prompt: str, added_by: str) -> None:
        self.api_key       = api_key
        self.system_prompt = system_prompt
        self.added_by      = added_by
        self._loop         = None
        self._ws           = None
        self._setup_done   = asyncio.Event()
        self._running      = False
        self._mic_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._play_buf     = bytearray()
        self._play_lock    = threading.Lock()
        self._last_mic_input     = None
        self._ai_speaking        = False
        self._ai_speaking_since  = 0.0
        self._farewell_requested = asyncio.Event()
        self._aec          = _EchoCanceller(AEC_FRAME, AEC_FILTER, 16000) if _EchoCanceller else None
        self._aec_ref      = bytearray(AEC_DELAY * 2)  # pre-filled silence creates the delay offset
        self._aec_ref_lock = threading.Lock()
        self._aec_mic_acc  = bytearray()

    # ── audio callbacks ───────────────────────────────────────────────────────

    def _mic_cb(self, indata, frames, _time, _status):
        """48 kHz stereo int32 → 16 kHz mono int16, with AEC."""
        mono_48k = (indata.astype(np.float32) / INT32_MAX).mean(axis=1)
        n = len(mono_48k)
        if n < 3:
            return
        mono_16k = mono_48k[: (n // 3) * 3].reshape(-1, 3).mean(axis=1)
        if np.abs(mono_16k).mean() > MIC_THRESHOLD and not self._ai_speaking:
            self._last_mic_input = time.time()
        pcm = (np.clip(mono_16k, -1.0, 1.0) * 32767).astype(np.int16).tobytes()

        if self._aec:
            self._aec_mic_acc.extend(pcm)
            frame_bytes = AEC_FRAME * 2
            out_chunks = []
            while len(self._aec_mic_acc) >= frame_bytes:
                mic_frame = bytes(self._aec_mic_acc[:frame_bytes])
                del self._aec_mic_acc[:frame_bytes]
                with self._aec_ref_lock:
                    if len(self._aec_ref) >= frame_bytes:
                        ref_frame = bytes(self._aec_ref[:frame_bytes])
                        del self._aec_ref[:frame_bytes]
                    else:
                        ref_frame = b"\x00" * frame_bytes
                out_chunks.append(self._aec.process(mic_frame, ref_frame))
            if not out_chunks:
                return
            pcm = b"".join(out_chunks)

        if self._loop and self._running:
            self._loop.call_soon_threadsafe(self._mic_queue.put_nowait, pcm)

    def _speaker_cb(self, outdata, frames, _time, _status):
        """24 kHz mono int16 → 48 kHz stereo int32."""
        needed_bytes = (frames // SPK_UP) * 2
        with self._play_lock:
            take     = min(needed_bytes, len(self._play_buf))
            in_bytes = bytes(self._play_buf[:take])
            del self._play_buf[:take]
        if take < needed_bytes:
            in_bytes += b"\x00" * (needed_bytes - take)
        mono_24k = np.frombuffer(in_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        if self._aec:
            n24 = len(mono_24k)
            n16 = n24 * 2 // 3
            if n16 > 0:
                ref_16k = np.interp(
                    np.linspace(0, n24 - 1, n16), np.arange(n24), mono_24k
                )
                ref_bytes = (np.clip(ref_16k, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                with self._aec_ref_lock:
                    self._aec_ref.extend(ref_bytes)
                    if len(self._aec_ref) > 32000:   # cap at ~1 s
                        del self._aec_ref[:-32000]

        mono_48k = np.repeat(mono_24k, SPK_UP)[:frames]
        outdata[:] = (np.clip(np.stack([mono_48k, mono_48k], axis=1), -1.0, 1.0) * INT32_MAX).astype(np.int32)

    # ── async loops ───────────────────────────────────────────────────────────

    async def _send_loop(self):
        await self._setup_done.wait()
        # Brief pause so the AI's opening words don't bleed back before
        # _ai_speaking is set — prevents self-interruption at startup.
        await asyncio.sleep(1.5)
        while self._running:
            pcm = await self._mic_queue.get()
            # Suppress mic for the first 5 s of AI speech to block speaker bleed.
            # After 5 s, allow audio through so the user can barge in.
            if self._ai_speaking and (time.time() - self._ai_speaking_since) < 3.0:
                continue
            await self._ws.send(json.dumps({
                "realtime_input": {
                    "media_chunks": [{"mime_type": "audio/pcm", "data": base64.b64encode(pcm).decode()}]
                }
            }))

    async def _recv_loop(self):
        async for raw in self._ws:
            msg = json.loads(raw)

            if "setupComplete" in msg:
                self._setup_done.set()
                print("[connected] speak now")
                await self._ws.send(json.dumps({
                    "clientContent": {
                        "turns": [{"role": "user", "parts": [{"text": "[activated, start conversation]"}]}],
                        "turnComplete": True,
                    }
                }))
                continue

            # ── tool calls ────────────────────────────────────────────────────
            for call in msg.get("toolCall", {}).get("functionCalls", []):
                call_id = call.get("id", "")
                name    = call.get("name", "")

                if name == "save_word":
                    save_entry(call.get("args", {}), self.added_by)
                    await self._ws.send(json.dumps({
                        "toolResponse": {"functionResponses": [{
                            "id": call_id, "name": name, "response": {"output": "Word saved."},
                        }]}
                    }))

                elif name == "end_conversation":
                    await self._ws.send(json.dumps({
                        "toolResponse": {"functionResponses": [{
                            "id": call_id, "name": name, "response": {"output": "Goodbye."},
                        }]}
                    }))
                    await asyncio.sleep(1.5)  # let final audio drain
                    raise FarewellComplete()

            sc = msg.get("serverContent")
            if not sc:
                continue

            for part in sc.get("modelTurn", {}).get("parts", []):
                if (text := part.get("text")) and not part.get("thought"):
                    print(f"ai> {text.strip()}")
                if b64 := part.get("inlineData", {}).get("data"):
                    if not self._ai_speaking:
                        self._ai_speaking_since = time.time()
                    self._ai_speaking = True
                    with self._play_lock:
                        self._play_buf.extend(base64.b64decode(b64))

            if sc.get("turnComplete"):
                self._ai_speaking = False

            if sc.get("interrupted"):
                self._ai_speaking = False
                with self._play_lock:
                    self._play_buf.clear()
                if self._aec:
                    with self._aec_ref_lock:
                        self._aec_ref.clear()
                        self._aec_ref.extend(b"\x00" * (AEC_DELAY * 2))
                print("[interrupted]")

    async def _farewell_monitor(self):
        """On SIGUSR1 (NFC removed): ask AI to say goodbye then exit."""
        await self._setup_done.wait()
        await self._farewell_requested.wait()
        print("[farewell] NFC removed — asking AI to say goodbye …")
        self._running = False
        await self._ws.send(json.dumps({
            "clientContent": {
                "turns": [{"role": "user", "parts": [{"text": "[the user removed their card — say a warm goodbye and call end_conversation]"}]}],
                "turnComplete": True,
            }
        }))
        # Fallback: if end_conversation is never called, exit after 15 s
        deadline = self._loop.time() + 15
        while self._loop.time() < deadline:
            await asyncio.sleep(0.2)
        raise FarewellComplete()

    async def _silence_monitor(self):
        """Nudge AI after 45 seconds of user silence."""
        await self._setup_done.wait()
        self._last_mic_input = time.time()
        while self._running:
            await asyncio.sleep(1)
            if self._ai_speaking:
                self._last_mic_input = time.time()
                continue
            if self._last_mic_input and time.time() - self._last_mic_input > 45:
                await self._ws.send(json.dumps({
                    "clientContent": {
                        "turns": [{"role": "user", "parts": [{"text": "[long silence — gently check if the user is still there]"}]}],
                        "turnComplete": True,
                    }
                }))
                self._last_mic_input = time.time()

    # ── entry point ───────────────────────────────────────────────────────────

    async def run(self):
        self._loop    = asyncio.get_running_loop()
        self._running = True
        self._loop.add_signal_handler(signal.SIGUSR1, self._farewell_requested.set)

        in_s  = sd.InputStream( device=MIC_DEVICE, samplerate=HW_RATE, channels=HW_CHANNELS, dtype=HW_DTYPE, blocksize=0, callback=self._mic_cb)
        out_s = sd.OutputStream(device=SPK_DEVICE, samplerate=HW_RATE, channels=HW_CHANNELS, dtype=HW_DTYPE, blocksize=0, callback=self._speaker_cb)
        in_s.start()
        out_s.start()

        try:
            async with websockets.connect(f"{WS_URL}?key={self.api_key}", max_size=8 << 20) as ws:
                self._ws = ws
                await ws.send(json.dumps({
                    "setup": {
                        "model": MODEL,
                        "generationConfig": {
                            "responseModalities": ["AUDIO"],
                            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Pulcherrima"}}},
                        },
                        "systemInstruction": {"parts": [{"text": self.system_prompt + _SYSTEM_SUFFIX}]},
                        "tools": [_TOOLS],
                    }
                }))
                tasks = [
                    asyncio.create_task(self._recv_loop()),
                    asyncio.create_task(self._send_loop()),
                    asyncio.create_task(self._silence_monitor()),
                    asyncio.create_task(self._farewell_monitor()),
                ]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for t in done:
                    if t.cancelled():
                        continue
                    exc = t.exception()
                    if exc and not isinstance(exc, (FarewellComplete, websockets.exceptions.ConnectionClosedOK)):
                        raise exc
        finally:
            self._running = False
            in_s.stop();  in_s.close()
            out_s.stop(); out_s.close()
            print("[closed]")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", default=DEFAULT_PROMPT)
    parser.add_argument("--person", default="Unknown")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY not set", file=sys.stderr)
        return 1

    init_familect_file()
    prompt = load_prompt(args.prompt_file)

    retry_delay = 2
    while True:
        try:
            asyncio.run(VoiceClient(api_key, prompt, args.person).run())
            return 0
        except KeyboardInterrupt:
            print("\n[stopped]")
            return 0
        except FarewellComplete:
            return 0
        except Exception as exc:
            print(f"[error] {exc} — retrying in {retry_delay}s …", file=sys.stderr)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 30)


if __name__ == "__main__":
    raise SystemExit(main())