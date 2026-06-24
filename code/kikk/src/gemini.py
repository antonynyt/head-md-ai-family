"""Gemini Live API session manager.

Uses the official google-genai Python SDK.
Receive loop follows the official per-turn pattern:
    while True:
        async for response in session.receive():
            ...
"""
from __future__ import annotations

import asyncio
from typing import Callable

try:
    from google import genai
    from google.genai import types
except ImportError as e:
    raise ImportError("pip install google-genai") from e

import src.dictionary as dictionary
from src.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_VOICE, PROMPT_FILE

# ── System prompt ─────────────────────────────────────────────────────────────

def _load_system_prompt() -> str:
    """Load prompt.txt — contains the full system prompt with {{FAMILECT_STATS}} placeholder."""
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            template = f.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError(f"prompt.txt not found at {PROMPT_FILE} — this file is required.")

    context = dictionary.build_context()
    return template.replace("{{FAMILECT_STATS}}", context)


TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="save_family_word",
        description="Call this when the user has confirmed a word and its definition.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "term":       types.Schema(type=types.Type.STRING, description="The word or phrase as the family uses it"),
                "definition": types.Schema(type=types.Type.STRING, description="What it means in this family's context"),
                "example":    types.Schema(type=types.Type.STRING, description="A short example sentence"),
            },
            required=["term", "definition"],
        ),
    ),
])





# ── Session ───────────────────────────────────────────────────────────────────

class GeminiSession:
    """
    Manages one Live API session.

    Callbacks (all plain sync functions):
        on_audio(pcm: bytes)           — 24kHz mono int16 to play
        on_transcript(text, turn)      — "user" or "model"
        on_word(entry: dict)           — word saved to dictionary
        on_interrupt()                 — interruption, clear audio buffer
        on_ai_speaking(speaking: bool) — AI turn started/ended
    """

    def __init__(
        self,
        added_by: str,
        on_audio:        Callable[[bytes], None],
        on_transcript:   Callable[[str, str], None],
        on_word:         Callable[[dict], None],
        on_interrupt:    Callable[[], None],
        on_ai_speaking:  Callable[[bool], None],
    ):
        self._added_by       = added_by
        self._on_audio       = on_audio
        self._on_transcript  = on_transcript
        self._on_word        = on_word
        self._on_interrupt   = on_interrupt
        self._on_ai_speaking = on_ai_speaking

        self._session  = None
        self._running  = False
        self._mic_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=5)

    def send_mic(self, pcm: bytes) -> None:
        """Enqueue mic chunk. Drops if queue is full to avoid latency buildup."""
        if self._running:
            try:
                self._mic_queue.put_nowait(pcm)
            except asyncio.QueueFull:
                pass

    async def run(self) -> None:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set")

        system_prompt = _load_system_prompt()
        client = genai.Client(api_key=GEMINI_API_KEY)

        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=types.Content(parts=[types.Part(text=system_prompt)]),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=GEMINI_VOICE)
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            tools=[TOOLS],
        )

        async with client.aio.live.connect(model=GEMINI_MODEL, config=config) as session:
            self._session = session
            self._running = True
            print("[gemini] session open")

            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._send_loop())
                tg.create_task(self._recv_loop())

        self._running = False
        print("[gemini] session closed")

    # ── internal loops ────────────────────────────────────────────────────────

    async def _send_loop(self) -> None:
        while self._running:
            try:
                pcm = await asyncio.wait_for(self._mic_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if self._session and self._running:
                try:
                    await self._session.send_realtime_input(
                        audio={"data": pcm, "mime_type": "audio/pcm"}
                    )
                except Exception as e:
                    print(f"[gemini] send error: {e}")

    async def _recv_loop(self) -> None:
        while self._running:
            turn = self._session.receive()
            async for response in turn:

                if response.tool_call:
                    for fn in response.tool_call.function_calls:
                        await self._handle_tool_call(fn)

                content = response.server_content
                if not content:
                    continue

                if content.model_turn:
                    for part in content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            self._on_ai_speaking(True)
                            self._on_audio(part.inline_data.data)

                if content.output_transcription and content.output_transcription.text:
                    self._on_transcript(content.output_transcription.text, "model")

                if content.input_transcription and content.input_transcription.text:
                    self._on_transcript(content.input_transcription.text, "user")

                if content.turn_complete:
                    self._on_ai_speaking(False)

                if content.interrupted:
                    print("[gemini] interrupted")
                    self._on_ai_speaking(False)
                    self._on_interrupt()

    async def _handle_tool_call(self, fn) -> None:
        name    = fn.name
        args    = dict(fn.args) if fn.args else {}
        call_id = fn.id

        if name == "save_family_word":
            entry = await dictionary.save(args, self._added_by)
            if entry:
                self._on_word(entry)
            await self._session.send_tool_response(
                function_responses=[types.FunctionResponse(
                    id=call_id, name=name,
                    response={"output": "Word saved." if entry else "Word already exists."},
                )]
            )