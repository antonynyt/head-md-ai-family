"""Audio I/O via PyAudio.

Mic:     16 kHz mono int16  →  Gemini (CHUNK_SIZE samples at a time)
Speaker: Gemini  →  24 kHz mono int16

Based on the official Gemini Live API example pattern.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Callable

try:
    import pyaudio
except ImportError as e:
    raise ImportError("pip install pyaudio  (also: sudo apt install portaudio19-dev)") from e

from src.config import MIC_DEVICE, SPK_DEVICE, GEMINI_IN_RATE, GEMINI_OUT_RATE

FORMAT     = pyaudio.paInt16
CHUNK_SIZE = 1024   # ~64ms at 16kHz — matches official example


class AudioIO:
    """
    Manages mic capture and speaker playback for one session.

        audio = AudioIO(loop, on_mic_chunk)
        audio.start()
        audio.enqueue(pcm_bytes)  # feed 24kHz mono int16 from Gemini
        audio.interrupt()         # clear speaker queue on interruption
        audio.stop()
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, on_mic_chunk: Callable[[bytes], None]):
        self._loop         = loop
        self._on_mic_chunk = on_mic_chunk

        self._pya         = pyaudio.PyAudio()
        self._mic_stream  = None
        self._spk_stream  = None

        self._out_queue   = asyncio.Queue()
        self._running     = False
        self._play_task   = None

    # ── public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True

        # Find device indices
        mic_index = self._find_device(MIC_DEVICE, input=True)
        spk_index = self._find_device(SPK_DEVICE, input=False)

        # Mic — blocking reads in a background thread
        self._mic_stream = self._pya.open(
            format=FORMAT,
            channels=1,
            rate=GEMINI_IN_RATE,
            input=True,
            input_device_index=mic_index,
            frames_per_buffer=CHUNK_SIZE,
        )
        self._mic_thread = threading.Thread(target=self._mic_reader, daemon=True)
        self._mic_thread.start()

        # Speaker — blocking writes in a background thread
        self._spk_stream = self._pya.open(
            format=FORMAT,
            channels=1,
            rate=GEMINI_OUT_RATE,
            output=True,
            output_device_index=spk_index,
        )
        self._play_task = asyncio.ensure_future(self._speaker_writer())

        print(f"[audio] started — mic={MIC_DEVICE} spk={SPK_DEVICE}")

    def stop(self) -> None:
        self._running = False

        if self._play_task:
            self._play_task.cancel()
            self._play_task = None

        for stream in (self._mic_stream, self._spk_stream):
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass

        self._mic_stream = None
        self._spk_stream = None
        self._pya.terminate()
        print("[audio] stopped")

    def enqueue(self, pcm: bytes) -> None:
        """Enqueue 24kHz mono int16 PCM for playback."""
        self._out_queue.put_nowait(pcm)

    def interrupt(self) -> None:
        """Clear the speaker queue immediately."""
        while not self._out_queue.empty():
            try:
                self._out_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        print("[audio] playback interrupted")

    # ── internal ──────────────────────────────────────────────────────────────

    def _find_device(self, device, input: bool) -> int | None:
        """Resolve device name/index to a PyAudio device index, or None for default."""
        if device is None:
            return None
        if isinstance(device, int):
            return device
        # Search by name substring
        for i in range(self._pya.get_device_count()):
            info = self._pya.get_device_info_by_index(i)
            if device.lower() in info["name"].lower():
                if input and info["maxInputChannels"] > 0:
                    return i
                if not input and info["maxOutputChannels"] > 0:
                    return i
        print(f"[audio] device {device!r} not found, using default")
        return None

    def _mic_reader(self) -> None:
        """Blocking mic read loop — runs in a background thread."""
        while self._running:
            try:
                data = self._mic_stream.read(CHUNK_SIZE, exception_on_overflow=False)
                if self._loop and not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(self._on_mic_chunk, data)
            except Exception as e:
                if self._running:
                    print(f"[audio] mic read error: {e}")
                break

    async def _speaker_writer(self) -> None:
        """Async loop that writes PCM chunks to the speaker stream."""
        while self._running:
            try:
                pcm = await asyncio.wait_for(self._out_queue.get(), timeout=0.5)
                if self._spk_stream:
                    await asyncio.to_thread(self._spk_stream.write, pcm)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    print(f"[audio] speaker write error: {e}")
