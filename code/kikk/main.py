#!/usr/bin/env python3
"""Familect — family dictionary voice assistant.

Pick up the telephone handset to start a session.
Hang up to end it.

Usage:
    GEMINI_API_KEY=your_key python3 main.py
"""
from __future__ import annotations

import asyncio
import signal
import sys

import websockets

import src.dictionary as dictionary
from src.audio      import AudioIO
from src.broadcaster import handler as ws_handler, broadcast
from src.button     import watch_button
from src.config     import PORT, GEMINI_API_KEY
from src.gemini     import GeminiSession
from src.server     import start_http_server


# ── Session state ─────────────────────────────────────────────────────────────

class SessionManager:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop    = loop
        self._session: GeminiSession | None = None
        self._audio:   AudioIO | None       = None
        self._task:    asyncio.Task | None  = None
        # Word currently shown on screen, awaiting voice confirmation. Kept so a
        # re-propose that only mentions the changed field doesn't wipe out the
        # rest of what's already displayed.
        self._pending_word: dict | None = None

    async def start(self) -> None:
        if self._session:
            print("[main] session already active")
            return

        print("[main] pick-up → starting session")
        await broadcast({"type": "session:start"})
        self._pending_word = None

        # Create audio I/O first so we can pass its methods as callbacks
        audio = AudioIO(
            loop=self._loop,
            on_mic_chunk=self._on_mic,
        )

        session = GeminiSession(
            added_by="Unknown",  # fallback if Gemini doesn't provide caller_name
            on_audio        = audio.enqueue,
            on_transcript   = self._on_transcript,
            on_word_pending = self._on_word_pending,
            on_word         = self._on_word,
        )

        audio.start()
        self._audio   = audio
        self._session = session
        self._task    = asyncio.create_task(self._run_session())

    async def end(self) -> None:
        if not self._session:
            return
        print("[main] hang-up → ending session")

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

        if self._audio:
            self._audio.stop()

        self._session = None
        self._audio   = None
        self._task    = None
        self._pending_word = None
        await broadcast({"type": "session:end"})


    async def _run_session(self) -> None:
        try:
            await self._session.run()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[main] session error: {e}")
            await broadcast({"type": "session:error", "message": str(e)})
        finally:
            if self._audio:
                self._audio.stop()
            self._session = None
            self._audio   = None
            self._task    = None
            self._pending_word = None
            await broadcast({"type": "session:end"})

    def _on_mic(self, pcm: bytes) -> None:
        if self._session:
            self._session.send_mic(pcm)

    def _on_transcript(self, text: str, turn: str) -> None:
        print(f"[{turn}] {text.strip()}")
        delay_ms = self._audio.playback_delay_ms() if self._audio else 0
        asyncio.ensure_future(broadcast({
            "type": "transcript",
            "text": text,
            "turn": turn,
            "delay_ms": delay_ms,
        }))

    def _on_word_pending(self, args: dict) -> None:
        self._pending_word = {**(self._pending_word or {}), **args}
        asyncio.ensure_future(broadcast({"type": "word:pending", "word": self._pending_word}))

    def _on_word(self, entry: dict) -> None:
        self._pending_word = None
        asyncio.ensure_future(broadcast({"type": "word:saved", "word": entry}))


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY is not set", file=sys.stderr)
        sys.exit(1)

    dictionary.ensure_file()
    loop    = asyncio.get_running_loop()
    manager = SessionManager(loop)

    # Graceful shutdown on Ctrl+C / SIGTERM
    stop_event = asyncio.Event()

    def _shutdown(sig):
        print(f"\n[main] {sig.name} received — shutting down")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig)

    # Start HTTP server (serves iPad UI)
    http_server = await start_http_server()

    # Start WebSocket server (port + 1 so HTTP and WS are separate)
    ws_port = PORT + 1
    ws_server = await websockets.serve(ws_handler, "0.0.0.0", ws_port)
    print(f"[ws]   listening on ws://0.0.0.0:{ws_port}")

    # Watch the button
    button_task = asyncio.create_task(
        watch_button(
            on_pick_up=lambda: asyncio.create_task(manager.start()),
            on_hang_up=lambda: asyncio.create_task(manager.end()),
        )
    )

    print("[main] ready — pick up the telephone to start")

    # Wait until shutdown
    await stop_event.wait()

    print("[main] shutting down …")
    button_task.cancel()
    await manager.end()
    ws_server.close()
    await ws_server.wait_closed()
    http_server.close()
    await http_server.wait_closed()
    print("[main] bye")


if __name__ == "__main__":
    asyncio.run(main())