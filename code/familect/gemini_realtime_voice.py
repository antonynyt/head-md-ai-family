#!/usr/bin/env python3
"""Real-time Gemini voice prototype.

Setup:
  python3 -m pip install websockets sounddevice numpy
  export GEMINI_API_KEY="your_key"
  python3 gemini_realtime_voice.py

Press Ctrl+C to stop.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import threading

try:
    import numpy as np
    import sounddevice as sd
    import websockets
except ImportError as exc:
    print(f"Missing: {exc}\nInstall: python3 -m pip install websockets sounddevice numpy", file=sys.stderr)
    raise SystemExit(1)

MODEL   = "models/gemini-2.5-flash-native-audio-preview-12-2025"
WS_URL  = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)
IN_RATE  = 16000
OUT_RATE = 24000
# Energy threshold (0.0–1.0) above which mic input counts as "someone speaking".
# Headphones: ~0.01 works well. Speakers: raise to ~0.05+ to ignore AI audio bleed.
MIC_THRESHOLD = 0.05


class VoiceClient:
    def __init__(self, api_key: str, system_prompt: str) -> None:
        self.api_key       = api_key
        self.system_prompt = system_prompt
        self._loop         = None
        self._ws           = None
        self._setup_done   = asyncio.Event()
        self._running      = False
        self._mic_queue: asyncio.Queue[bytes] = asyncio.Queue()
        # Flat byte buffer — avoids losing bytes when chunks are larger than one callback frame
        self._play_buf   = bytearray()
        self._play_lock  = threading.Lock()
        self._last_mic_input = None
        self._ai_speaking    = False  # True while AI turn is in progress

    # ── mic ──────────────────────────────────────────────────────────────────
    def _mic_cb(self, indata, frames, _time, _status):
        import time
        pcm = (np.clip(indata[:, 0], -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        # Only reset the silence timer when the user is actually speaking (energy above noise floor)
        if np.abs(indata[:, 0]).mean() > MIC_THRESHOLD:
            self._last_mic_input = time.time()
        if self._loop and self._running:
            self._loop.call_soon_threadsafe(self._mic_queue.put_nowait, pcm)

    # ── speaker ──────────────────────────────────────────────────────────────
    def _speaker_cb(self, outdata, frames, _time, _status):
        needed = frames * 2  # int16 mono → 2 bytes per sample
        with self._play_lock:
            take      = min(needed, len(self._play_buf))
            out_bytes = bytes(self._play_buf[:take])
            del self._play_buf[:take]           # consume only what we used
        # zero-pad when the buffer is running dry (keeps stream alive without glitches)
        if take < needed:
            out_bytes += b"\x00" * (needed - take)
        outdata[:, 0] = np.frombuffer(out_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    # ── send mic to Gemini ────────────────────────────────────────────────────
    async def _send_loop(self):
        await self._setup_done.wait()
        while self._running:
            pcm = await self._mic_queue.get()
            # While AI is speaking, only forward audio if the user is actually talking
            # (above threshold) — prevents noise/bleed self-interruption but allows real interrupts
            if self._ai_speaking:
                energy = np.abs(np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0).mean()
                if energy < MIC_THRESHOLD:
                    continue
            await self._ws.send(json.dumps({
                "realtime_input": {
                    "media_chunks": [{"mime_type": "audio/pcm", "data": base64.b64encode(pcm).decode()}]
                }
            }))

    # ── receive from Gemini ───────────────────────────────────────────────────
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

            sc = msg.get("serverContent")
            if not sc:
                continue

            for part in sc.get("modelTurn", {}).get("parts", []):
                if text := part.get("text"):
                    print(f"ai> {text}")
                if b64 := part.get("inlineData", {}).get("data"):
                    self._ai_speaking = True  # AI has started/is speaking
                    with self._play_lock:
                        self._play_buf.extend(base64.b64decode(b64))

            if sc.get("turnComplete"):
                self._ai_speaking = False  # AI finished its turn

            if sc.get("interrupted"):
                self._ai_speaking = False
                with self._play_lock:
                    self._play_buf.clear()
                print("[interrupted]")

    # ── silence monitor ───────────────────────────────────────────────────────
    async def _silence_monitor(self):
        """Monitor for 10 seconds of silence and prompt the AI."""
        import time
        await self._setup_done.wait()
        self._last_mic_input = time.time()  # Initialize

        while self._running:
            await asyncio.sleep(1)  # Check every second
            # Skip if AI is currently speaking
            if self._ai_speaking:
                continue
            if self._last_mic_input and time.time() - self._last_mic_input > 15:
                # 15 seconds of silence detected — ask the AI to check in
                await self._ws.send(json.dumps({
                    "clientContent": {
                        "turns": [{"role": "user", "parts": [{"text": "[10 seconds of silence — please ask the user if they are still there]"}]}],
                        "turnComplete": True,
                    }
                }))
                self._last_mic_input = time.time()  # Reset timer

    # ── entry point ───────────────────────────────────────────────────────────
    async def run(self):
        self._loop    = asyncio.get_running_loop()
        self._running = True

        in_s  = sd.InputStream( samplerate=IN_RATE,  channels=1, dtype="float32", blocksize=0, callback=self._mic_cb)
        out_s = sd.OutputStream(samplerate=OUT_RATE, channels=1, dtype="float32", blocksize=0, callback=self._speaker_cb)
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
                        "systemInstruction": {"parts": [{"text": self.system_prompt}]},
                    }
                }))
                recv_t = asyncio.create_task(self._recv_loop())
                send_t = asyncio.create_task(self._send_loop())
                monitor_t = asyncio.create_task(self._silence_monitor())  # Add this
                done, pending = await asyncio.wait([recv_t, send_t, monitor_t], return_when=asyncio.FIRST_EXCEPTION)
                for t in pending:
                    t.cancel()
                for t in done:
                    if t.exception():
                        raise t.exception()
        finally:
            self._running = False
            in_s.stop();  in_s.close()
            out_s.stop(); out_s.close()
            print("[closed]")


def main() -> int:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY not set", file=sys.stderr)
        return 1
    try:
        #import prompt from txt file
        with open("prompt.txt", "r") as f:
            prompt = f.read().strip()
        asyncio.run(VoiceClient(api_key, prompt or "You are a family dictionary.").run())
    except KeyboardInterrupt:
        print("\n[stopped]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
