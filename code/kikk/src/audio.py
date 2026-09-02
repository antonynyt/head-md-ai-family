"""Audio I/O via PyAudio.

Mic:     16 kHz mono int16  →  Gemini (CHUNK_SIZE samples at a time)
Speaker: Gemini  →  24 kHz mono int16  →  telephone filter  →  speaker

Based on the official Gemini Live API example pattern.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Callable

import numpy as np
from scipy import signal

try:
    import pyaudio
except ImportError as e:
    raise ImportError("pip install pyaudio  (also: sudo apt install portaudio19-dev)") from e

from src.config import MIC_DEVICE, SPK_DEVICE, MIC_IN_RATE, SPK_OUT_RATE, GEMINI_IN_RATE, GEMINI_OUT_RATE

FORMAT     = pyaudio.paInt16
CHUNK_SIZE = 4800   # 300ms at 16kHz — ~3 requests/sec, avoids 409 rate limit errors

# ── Telephone filter ──────────────────────────────────────────────────────────
# Classic POTS bandwidth: 300Hz–3400Hz bandpass.
# Built once at module load — scipy filter design is expensive.
_TEL_SOS = signal.butter(
    4, [300, 3400], btype='bandpass', fs=GEMINI_OUT_RATE, output='sos'
)

# ── Presence sound constants ──────────────────────────────────────────────────
# Pink noise level — warmer than white noise, biased toward low-mids.
# 0.003 = subtle tape hiss presence
PINK_LEVEL = 0.003

def _resample_pcm(pcm: bytes, in_rate: int, out_rate: int) -> bytes:
    """Resample int16 PCM from one rate to another."""
    if not pcm or in_rate == out_rate:
        return pcm
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return pcm
    resampled = signal.resample_poly(samples, out_rate, in_rate)
    resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
    return resampled.tobytes()


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
        self._voice_buf   = bytearray()
        self._voice_lock  = threading.Lock()
        self._audio_samples_queued = 0
        self._audio_samples_played = 0
        # Filter state carried between chunks to avoid boundary clicks
        self._filter_zi   = signal.sosfilt_zi(_TEL_SOS)

    # ── public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True

        mic_index = self._find_device(MIC_DEVICE, input=True)
        spk_index = self._find_device(SPK_DEVICE, input=False)

        self._mic_stream = self._pya.open(
            format=FORMAT,
            channels=1,
            rate=MIC_IN_RATE,
            input=True,
            input_device_index=mic_index,
            frames_per_buffer=CHUNK_SIZE,
        )
        self._mic_thread = threading.Thread(target=self._mic_reader, daemon=True)
        self._mic_thread.start()

        self._spk_stream = self._pya.open(
            format=FORMAT,
            channels=1,
            rate=SPK_OUT_RATE,
            output=True,
            output_device_index=spk_index,
        )
        self._play_task = asyncio.create_task(self._speaker_writer())
        self._noise_t   = threading.Thread(target=self._noise_thread, daemon=True)
        self._noise_t.start()

        print(f"[audio] started — mic={MIC_DEVICE} spk={SPK_DEVICE}")

    def stop(self) -> None:
        # 1. Signal all threads/tasks to stop — they check _running each loop
        self._running = False

        if self._play_task:
            self._play_task.cancel()
            self._play_task = None

        # 2. Wait for mic reader and noise thread to exit their loops
        #    before touching the streams they're using
        time.sleep(0.3)

        # 3. Null out stream references so any late callbacks bail early
        mic = self._mic_stream
        spk = self._spk_stream
        self._mic_stream = None
        self._spk_stream = None

        # 4. Abort streams (not stop — abort drops pending buffers immediately)
        #    wrapped individually so one failure doesn't block the other
        for stream in (mic, spk):
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass

        # 5. Terminate PyAudio — do this last and in a separate process
        #    if needed to avoid the ALSA mmap segfault
        time.sleep(0.2)
        try:
            self._pya.terminate()
        except Exception:
            pass

        print("[audio] stopped")

    def enqueue(self, pcm: bytes) -> None:
        """Filter and enqueue 24kHz mono int16 PCM for playback."""
        if not pcm:
            return
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        filtered, self._filter_zi = signal.sosfilt(_TEL_SOS, samples, zi=self._filter_zi)
        pcm_out = np.clip(filtered, -32768, 32767).astype(np.int16)
        pcm_out = _resample_pcm(pcm_out.tobytes(), GEMINI_OUT_RATE, SPK_OUT_RATE)
        with self._voice_lock:
            self._audio_samples_queued += len(pcm_out) // 2
        self._out_queue.put_nowait(pcm_out)

    def playback_delay_ms(self) -> int:
        """Return ms until currently queued audio will have finished playing.

        A transcript chunk arrives from Gemini around the same time as the audio
        it describes is enqueued here — but the speaker plays that queue back in
        real time, so the chunk's audio won't actually be *heard* until this much
        later. The caller uses this to hold the on-screen transcript back so it
        appears in step with the sound instead of the moment the text streams in.
        """
        hw_latency_sec = 0.0
        if self._spk_stream:
            try:
                hw_latency_sec = self._spk_stream.get_output_latency()
            except Exception:
                hw_latency_sec = 0.025  # fallback: 25ms

        with self._voice_lock:
            queued = self._audio_samples_queued

        delay_ms = queued * 1000 / SPK_OUT_RATE + hw_latency_sec * 1000
        return max(0, round(delay_ms))

    def interrupt(self) -> None:
        """Clear the speaker queue, voice buffer and reset filter state."""
        while not self._out_queue.empty():
            try:
                self._out_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        with self._voice_lock:
            self._voice_buf.clear()
            self._audio_samples_queued = 0
            self._audio_samples_played = 0
        self._filter_zi = signal.sosfilt_zi(_TEL_SOS)
        print("[audio] playback interrupted")

    # ── internal ──────────────────────────────────────────────────────────────

    def _find_device(self, device, input: bool) -> int | None:
        if device is None:
            return None
        if isinstance(device, int):
            return device
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
        while self._running:
            try:
                data = self._mic_stream.read(CHUNK_SIZE, exception_on_overflow=False)
                data = _resample_pcm(data, MIC_IN_RATE, GEMINI_IN_RATE)
                if self._loop and not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(self._on_mic_chunk, data)
            except Exception as e:
                if self._running:
                    print(f"[audio] mic read error: {e}")
                break

    async def _speaker_writer(self) -> None:
        """Dequeue voice chunks and put them in the voice buffer for the noise thread."""
        while self._running:
            try:
                pcm = await asyncio.wait_for(self._out_queue.get(), timeout=0.5)
                with self._voice_lock:
                    self._voice_buf.extend(pcm)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    print(f"[audio] speaker write error: {e}")

    def _noise_thread(self) -> None:
        """Writes continuous pink noise + voice at a fixed hardware rate."""
        frame      = int(SPK_OUT_RATE * 0.01)  # 10ms frames
        pink_state = np.zeros(8)

        # Precompute masks — frame size never changes
        indices = np.arange(frame)
        masks   = [indices % (2**i) == 0 for i in range(8)]

        while self._running:
            with self._voice_lock:
                needed      = frame * 2
                take        = min(needed, len(self._voice_buf))
                voice_bytes = bytes(self._voice_buf[:take])
                del self._voice_buf[:take]
                self._audio_samples_queued -= take // 2
                self._audio_samples_played += take // 2
                if take < needed:
                    voice_bytes += b"\x00" * (needed - take)

            voice = np.frombuffer(voice_bytes, dtype=np.int16).astype(np.float32)

            # Pink noise via Voss-McCartney (8-stage 1/f approximation)
            white = np.random.normal(0, 1, (frame, 8))
            for i in range(8):
                if masks[i].any():
                    pink_state[i] = white[masks[i], i][-1]
            pink = np.sum([
                np.where(masks[i], white[:, i], pink_state[i])
                for i in range(8)
            ], axis=0) / 8.0 * (PINK_LEVEL * 32767)

            output = np.clip(voice + pink, -32768, 32767).astype(np.int16)

            if self._spk_stream:
                try:
                    self._spk_stream.write(output.tobytes())
                except Exception:
                    break