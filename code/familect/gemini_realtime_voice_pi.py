#!/usr/bin/env python3
"""Real-time Gemini voice prototype — Raspberry Pi edition.

Uses ALSA devices 'mic_sv' (input) and 'pwm_sv' (output).
Hardware runs at 48 kHz stereo int32; Gemini expects 16 kHz mono int16 in
and produces 24 kHz mono int16 out — this script handles all conversion.

Setup:
  pip install websockets sounddevice numpy scipy
  export GEMINI_API_KEY="your_key"
  python3 gemini_realtime_voice_pi.py

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
    from scipy.signal import resample_poly
    import websockets
except ImportError as exc:
    print(f"Missing: {exc}\nInstall: pip install websockets sounddevice numpy scipy", file=sys.stderr)
    raise SystemExit(1)

MODEL  = "models/gemini-2.5-flash-native-audio-preview-12-2025"
WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)

# ── Gemini API rates ──────────────────────────────────────────────────────────
GEMINI_IN_RATE  = 16_000   # Gemini expects 16 kHz mono int16
GEMINI_OUT_RATE = 24_000   # Gemini outputs  24 kHz mono int16

# ── Pi hardware rates ─────────────────────────────────────────────────────────
HW_RATE     = 48_000       # S32_LE / 48 kHz
HW_CHANNELS = 2            # stereo
HW_DTYPE    = "int32"      # S32_LE

MIC_DEVICE  = "mic_sv"     # ALSA capture device
SPK_DEVICE  = "pwm_sv"     # ALSA playback device

# Integer resample ratios (used with scipy.signal.resample_poly)
#   48000 → 16000  :  up=1, down=3
#   24000 → 48000  :  up=2, down=1
MIC_UP, MIC_DOWN = 1, 3
SPK_UP, SPK_DOWN = 2, 1    # simple ×2 repeat — fast enough for voice

# Energy threshold (float32 mean abs) above which mic input counts as speech.
MIC_THRESHOLD = 0.05

INT32_MAX = 2_147_483_647.0   # 2^31 – 1


class VoiceClient:
    def __init__(self, api_key: str, system_prompt: str) -> None:
        self.api_key       = api_key
        self.system_prompt = system_prompt
        self._loop         = None
        self._ws           = None
        self._setup_done   = asyncio.Event()
        self._running      = False
        self._mic_queue: asyncio.Queue[bytes] = asyncio.Queue()
        # Flat byte buffer storing 24 kHz mono int16 bytes from Gemini
        self._play_buf  = bytearray()
        self._play_lock = threading.Lock()
        self._last_mic_input = None
        self._ai_speaking    = False

    # ── mic callback (runs in a PortAudio thread) ─────────────────────────────
    def _mic_cb(self, indata, frames, _time, _status):
        """Capture stereo int32 @ 48 kHz → resample to mono int16 @ 16 kHz."""
        import time

        # indata: shape (frames, 2), dtype int32
        float_stereo = indata.astype(np.float32) / INT32_MAX
        # Mix stereo → mono
        mono_48k = float_stereo.mean(axis=1)
        # Downsample 48 kHz → 16 kHz using polyphase filter (good anti-aliasing)
        mono_16k = resample_poly(mono_48k, MIC_UP, MIC_DOWN).astype(np.float32)

        energy = np.abs(mono_16k).mean()
        if energy > MIC_THRESHOLD:
            self._last_mic_input = time.time()

        pcm = (np.clip(mono_16k, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        if self._loop and self._running:
            self._loop.call_soon_threadsafe(self._mic_queue.put_nowait, pcm)

    # ── speaker callback (runs in a PortAudio thread) ─────────────────────────
    def _speaker_cb(self, outdata, frames, _time, _status):
        """Render stereo int32 @ 48 kHz from 24 kHz mono int16 play buffer."""
        # `frames` = output samples per channel at 48 kHz.
        # Each output sample maps to 0.5 input samples at 24 kHz → need frames//2 input samples.
        needed_in_samples = frames // SPK_UP          # samples at 24 kHz
        needed_in_bytes   = needed_in_samples * 2     # int16 → 2 bytes each

        with self._play_lock:
            take     = min(needed_in_bytes, len(self._play_buf))
            in_bytes = bytes(self._play_buf[:take])
            del self._play_buf[:take]

        # Zero-pad if the buffer runs dry (keeps stream glitch-free)
        if take < needed_in_bytes:
            in_bytes += b"\x00" * (needed_in_bytes - take)

        # Decode int16 → float32
        mono_24k = np.frombuffer(in_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        # Upsample 24 kHz → 48 kHz: nearest-neighbour ×2 (fast; transparent for voice)
        mono_48k = np.repeat(mono_24k, SPK_UP)[:frames]
        # Expand to stereo and convert to int32
        stereo = np.stack([mono_48k, mono_48k], axis=1)
        outdata[:] = (np.clip(stereo, -1.0, 1.0) * INT32_MAX).astype(np.int32)

    # ── send mic to Gemini ────────────────────────────────────────────────────
    async def _send_loop(self):
        await self._setup_done.wait()
        while self._running:
            pcm = await self._mic_queue.get()
            # While AI is speaking, gate on energy to allow real interrupts
            # but suppress ambient noise / speaker bleed
            if self._ai_speaking:
                samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
                if np.abs(samples).mean() < MIC_THRESHOLD:
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
                    self._ai_speaking = True
                    with self._play_lock:
                        self._play_buf.extend(base64.b64decode(b64))

            if sc.get("turnComplete"):
                self._ai_speaking = False

            if sc.get("interrupted"):
                self._ai_speaking = False
                with self._play_lock:
                    self._play_buf.clear()
                print("[interrupted]")

    # ── silence monitor ───────────────────────────────────────────────────────
    async def _silence_monitor(self):
        """Prompt the AI after 15 seconds of silence."""
        import time
        await self._setup_done.wait()
        self._last_mic_input = time.time()

        while self._running:
            await asyncio.sleep(1)
            if self._ai_speaking:
                continue
            if self._last_mic_input and time.time() - self._last_mic_input > 15:
                await self._ws.send(json.dumps({
                    "clientContent": {
                        "turns": [{"role": "user", "parts": [{"text": "[10 seconds of silence — please ask the user if they are still there]"}]}],
                        "turnComplete": True,
                    }
                }))
                self._last_mic_input = time.time()

    # ── entry point ───────────────────────────────────────────────────────────
    async def run(self):
        self._loop    = asyncio.get_running_loop()
        self._running = True

        in_s = sd.InputStream(
            device=MIC_DEVICE,
            samplerate=HW_RATE,
            channels=HW_CHANNELS,
            dtype=HW_DTYPE,
            blocksize=0,
            callback=self._mic_cb,
        )
        out_s = sd.OutputStream(
            device=SPK_DEVICE,
            samplerate=HW_RATE,
            channels=HW_CHANNELS,
            dtype=HW_DTYPE,
            blocksize=0,
            callback=self._speaker_cb,
        )
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
                recv_t    = asyncio.create_task(self._recv_loop())
                send_t    = asyncio.create_task(self._send_loop())
                monitor_t = asyncio.create_task(self._silence_monitor())
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
        with open("prompt.txt", "r") as f:
            prompt = f.read().strip()
        asyncio.run(VoiceClient(api_key, prompt or "You are a family dictionary.").run())
    except KeyboardInterrupt:
        print("\n[stopped]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
