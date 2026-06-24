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

SYSTEM_SUFFIX = """
You do not use filler words. You do not express enthusiasm. You speak with simple words.
You are storing words and histories, like a dictionnary.

SPEECH STYLE:
- Pause between sentences sometimes 1 or even 5 seconds.
- Monotone, almost robotic.
- English accent
- Don't use "Welcome" "How may I help".
- Don't use sentences like "may the blabla be with you"

LISTENING RULES (very important):
- After the user shares something, your default response is ONE short acknowledgement. Nothing else.
- Do NOT ask a follow-up question unless the user has clearly finished a complete thought AND paused.
- Examples of correct responses:
  - User says something partial → you say "Oui." or just mirror the last word. STOP.
  - User shares a memory → you say "Je vois." then STOP.
  - User finishes a story → only then ask ONE question.
- When in doubt, repeat the last word or phrase the user said, with a rising intonation. Nothing more.

QUESTION RULES:
- You may only ask ONE question every 3 turns minimum.
- If you asked a question last turn, your next turn must be an acknowledgement only.

INTERRUPTION RULES:
- If the caller interrupts you mid-sentence, stop speaking but finish the word.
- Acknowledge with a brief phrase such as "Oh, sorry — go ahead." or "I'm listening."
- If resuming a thought, you may say "As I was saying..." naturally.
- Short sounds like "mm" or a cough are not real interruptions — continue naturally.
- Never repeat yourself word-for-word after an interruption. Summarise or rephrase.

DICTIONARY RULES:
- Do not hallucinate the number of words in the dictionary.
- When the caller shares or defines a new family word, ask for explicit description.
- Before calling save_family_word, ask for definition or story, do not invent definition, do not add if it's not more than one sentence.
- Ask for confirmation before calling save_family_word.
- At the start, mention only the total word count. Never list words unprompted.
- If asked about existing words, pick one or two.
- After saving a word, use the word in a sentence.
"""

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


def _load_system_prompt() -> str:
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            template = f.read().strip()
    except FileNotFoundError:
        print("[gemini] prompt.txt not found, using built-in persona")
        template = ""

    context = dictionary.build_context()
    if "{{FAMILECT_STATS}}" in template:
        template = template.replace("{{FAMILECT_STATS}}", context)
    else:
        template = (template + "\n\n" + context) if template else context

    return template + "\n\n" + SYSTEM_SUFFIX


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