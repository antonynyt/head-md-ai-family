"""Gemini Live API session manager.

Uses the official google-genai Python SDK.
Receive loop follows the official per-turn pattern:
    while True:
        async for response in session.receive():
            ...
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Callable

try:
    from google import genai
    from google.genai import types
except ImportError as e:
    raise ImportError("pip install google-genai") from e

import numpy as np

import src.dictionary as dictionary
from src.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_VOICE, PROMPT_FILE

# Seconds of caller silence after pick-up before the operator greets first.
# The greeting is generated right at session open and held back until then — if the caller
# says "allo" in the meantime, the held greeting is thrown away and only the reply to them plays.
GREETING_DELAY_SEC = 2.0
# Local speech detection on the mic, so the held greeting isn't released while the caller is
# mid-"allo" and Gemini hasn't transcribed it yet. Adaptive: the room's noise floor is tracked and a chunk
# counts as speech only when it is clearly louder than it (mouth is right on the handset).
SPEECH_NOISE_RATIO = 3.0     # speech RMS must be this many times the noise floor (~10 dB)
SPEECH_RMS_MIN     = 300     # absolute floor (int16 RMS) so a silent room doesn't trigger on a breath
NOISE_FLOOR_ALPHA  = 0.2     # how fast the noise floor follows ambient level changes
# Once the caller spoke, how long to wait for Gemini to react before greeting anyway
# (covers false triggers like a handset knock)
CALLER_REPLY_GRACE_SEC = 1.0

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


_WORD_PROPERTIES = {
    "term":           types.Schema(type=types.Type.STRING, description="The word or phrase as the family uses it"),
    "definition":     types.Schema(type=types.Type.STRING, description="What it means in this family's context"),
    "pronunciation":  types.Schema(type=types.Type.STRING, description="How to say it, spelled phonetically (e.g. 'fuh-NEH-tik')"),
    "example":        types.Schema(type=types.Type.STRING, description="A short example sentence"),
    "part_of_speech": types.Schema(type=types.Type.STRING, description="Part of speech: n. v. adj. adv. expr. etc."),
    "caller_name":    types.Schema(type=types.Type.STRING, description="The name of the person who shared this word"),
}

TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="propose_family_word",
        description=(
            "Call this once, right before asking the caller to confirm a word out loud. "
            "Shows the word on their screen. Does not save it yet."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties=_WORD_PROPERTIES,
            required=["term", "definition"],
        ),
    ),
    types.FunctionDeclaration(
        name="save_family_word",
        description="Call this only after the caller has confirmed the word out loud.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties=_WORD_PROPERTIES,
            required=["term", "definition"],
        ),
    ),
    types.FunctionDeclaration(
        name="discard_family_word",
        description=(
            "Call this when the caller says they do not want the proposed word added. "
            "Removes it from their screen. Does not save anything."
        ),
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="highlight_family_word",
        description=(
            "Call this when you start talking about one or more existing dictionary "
            "entries by name — it lights them up on the caller's screen. Does not "
            "save or change anything."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "terms": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="The exact word(s) or phrase(s) being talked about, as stored in the dictionary",
                ),
            },
            required=["terms"],
        ),
    ),
])


# ── Session ───────────────────────────────────────────────────────────────────

class GeminiSession:
    """
    Manages one Live API session.

    Callbacks (all plain sync functions):
        on_audio(pcm: bytes)          — 24kHz mono int16 to play
        on_transcript(text, turn)     — "user" or "model"
        on_word_pending(args: dict)   — word proposed, awaiting voice confirmation
        on_word_discarded()           — proposed word declined by the caller
        on_word_mentioned(terms)      — existing word(s) being talked about
        on_word(entry: dict)          — word saved to dictionary
        on_interrupted()              — caller barged in over the model's speech
    """

    def __init__(
        self,
        added_by: str,
        on_audio:          Callable[[bytes], None],
        on_transcript:     Callable[[str, str], None],
        on_word_pending:   Callable[[dict], None],
        on_word_discarded: Callable[[], None],
        on_word_mentioned: Callable[[list[str]], None],
        on_word:           Callable[[dict], None],
        on_interrupted:    Callable[[], None],
    ):
        self._added_by          = added_by
        self._on_audio          = on_audio
        self._on_transcript     = on_transcript
        self._on_word_pending   = on_word_pending
        self._on_word_discarded = on_word_discarded
        self._on_word_mentioned = on_word_mentioned
        self._on_word           = on_word
        self._on_interrupted    = on_interrupted

        self._session  = None
        self._running  = False
        # Session object is created at pick-up — the greeting delay counts from here
        self._picked_up_at = time.monotonic()
        # Set once Gemini has heard the caller or answered them
        self._conversation_started = asyncio.Event()
        # Greeting gate: "holding" (greeting audio buffered, not played yet), "dropped"
        # (caller spoke first — discard the rest of the greeting turn), "done" (normal flow)
        self._greeting = "done"
        self._greeting_turn_open = False      # the greeting turn is still streaming in
        self._greeting_held: list[tuple[str, object]] = []
        self._greeting_settled = asyncio.Event()
        # Set as soon as the mic picks up speech locally — ahead of any server round-trip
        self._caller_spoke = asyncio.Event()
        self._noise_floor: float | None = None
        self._mic_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=5)
        # Mic audio captured while the Gemini connection is still opening (~3s of 300ms chunks)
        # — sent once it's open, so an early "allo" is heard instead of dropped
        self._preconnect_mic: deque[bytes] = deque(maxlen=10)

    def send_mic(self, pcm: bytes) -> None:
        """Enqueue mic chunk. Drops if queue is full to avoid latency buildup."""
        if not self._caller_spoke.is_set():
            self._detect_speech(pcm)
        if not self._running:
            self._preconnect_mic.append(pcm)
        else:
            try:
                self._mic_queue.put_nowait(pcm)
            except asyncio.QueueFull:
                pass

    def _detect_speech(self, pcm: bytes) -> None:
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        if not samples.size:
            return
        rms = float(np.sqrt(np.mean(samples ** 2)))
        if self._noise_floor is None:
            # First chunk calibrates the room — never counted as speech
            self._noise_floor = rms
            return
        if rms > max(self._noise_floor * SPEECH_NOISE_RATIO, SPEECH_RMS_MIN):
            print(f"[gemini] caller speech detected (rms {rms:.0f}, floor {self._noise_floor:.0f})")
            self._caller_spoke.set()
        else:
            self._noise_floor += NOISE_FLOOR_ALPHA * (rms - self._noise_floor)

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
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                    prefix_padding_ms=200,
                    silence_duration_ms=800,
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            tools=[TOOLS],
        )

        async with client.aio.live.connect(model=GEMINI_MODEL, config=config) as session:
            self._session = session
            self._running = True
            print(f"[gemini] session open ({time.monotonic() - self._picked_up_at:.1f}s after pick-up)")
            # Mic audio from before the connection opened, in order, ahead of live chunks
            for pcm in self._preconnect_mic:
                await session.send_realtime_input(
                    audio={"data": pcm, "mime_type": "audio/pcm;rate=16000"}
                )
            self._preconnect_mic.clear()

            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._send_loop())
                tg.create_task(self._recv_loop())
                tg.create_task(self._greeting_gate())

        self._running = False
        print("[gemini] session closed")

    # ── internal loops ────────────────────────────────────────────────────────

    async def _send_greeting_cue(self) -> None:
        await self._session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[types.Part(text="(The person has just picked up the phone. Say your first sentence.)")],
            ),
            turn_complete=True,
        )

    async def _greeting_gate(self) -> None:
        """Make sure the caller hears exactly one greeting.

        Silent caller → the pre-generated greeting plays GREETING_DELAY_SEC after pick-up.
        Caller says "allo" first → the held greeting is dropped and only Gemini's reply plays.
        """
        if self._caller_spoke.is_set():
            # "allo" already said while connecting — Gemini answers the buffered audio itself
            print("[gemini] caller spoke while connecting — no greeting cue")
            try:
                await asyncio.wait_for(self._conversation_started.wait(), timeout=CALLER_REPLY_GRACE_SEC)
            except asyncio.TimeoutError:
                print("[gemini] no reply to caller noise — greeting now")
                await self._send_greeting_cue()
            return

        # Generate the greeting now, play it later (or never)
        self._greeting = "holding"
        self._greeting_turn_open = True
        try:
            await self._send_greeting_cue()
        except Exception as e:
            print(f"[gemini] greet error: {e}")
            self._greeting = "done"
            return

        await asyncio.sleep(max(0.0, GREETING_DELAY_SEC - (time.monotonic() - self._picked_up_at)))
        if self._greeting == "holding" and self._caller_spoke.is_set():
            # Caller is mid-sentence — wait for Gemini to confirm before playing anything
            try:
                await asyncio.wait_for(self._greeting_settled.wait(), timeout=CALLER_REPLY_GRACE_SEC)
            except asyncio.TimeoutError:
                print("[gemini] caller noise but no reply — playing greeting")
        if self._greeting == "holding":
            self._release_greeting()

    def _release_greeting(self) -> None:
        print(f"[gemini] playing greeting ({time.monotonic() - self._picked_up_at:.1f}s after pick-up)")
        self._greeting = "done"
        self._greeting_settled.set()
        held, self._greeting_held = self._greeting_held, []
        for kind, value in held:
            if kind == "audio":
                self._on_audio(value)
            else:
                self._on_transcript(value, "model")

    def _drop_greeting(self) -> None:
        print("[gemini] caller spoke first — dropping held greeting")
        self._greeting_held.clear()
        self._greeting = "dropped" if self._greeting_turn_open else "done"
        self._greeting_settled.set()

    def _emit_model(self, kind: str, value) -> None:
        """Route model audio/transcript through the greeting gate."""
        if self._greeting_turn_open and self._greeting == "holding":
            self._greeting_held.append((kind, value))
        elif self._greeting_turn_open and self._greeting == "dropped":
            pass
        elif kind == "audio":
            self._on_audio(value)
        else:
            self._on_transcript(value, "model")

    async def _send_loop(self) -> None:
        while self._running:
            try:
                pcm = await asyncio.wait_for(self._mic_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if self._session and self._running:
                try:
                    await self._session.send_realtime_input(
                        audio={"data": pcm, "mime_type": "audio/pcm;rate=16000"}
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

                caller_text = content.input_transcription.text if content.input_transcription else None
                if content.model_turn or caller_text:
                    self._conversation_started.set()

                # Gemini heard the caller (or is answering them) before the greeting played
                if self._greeting == "holding" and (
                    caller_text or content.interrupted
                    or (content.model_turn and not self._greeting_turn_open)
                ):
                    self._drop_greeting()

                if content.model_turn:
                    for part in content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            self._emit_model("audio", part.inline_data.data)

                if content.output_transcription and content.output_transcription.text:
                    self._emit_model("transcript", content.output_transcription.text)

                if caller_text:
                    self._on_transcript(caller_text, "user")

                if content.interrupted:
                    self._on_interrupted()

                if content.turn_complete or content.interrupted:
                    if self._greeting_turn_open:
                        self._greeting_turn_open = False
                        if self._greeting == "dropped":
                            self._greeting = "done"

    async def _handle_tool_call(self, fn) -> None:
        name    = fn.name
        args    = dict(fn.args) if fn.args else {}
        call_id = fn.id

        if name == "propose_family_word":
            caller = args.get("caller_name") or self._added_by
            self._added_by = caller  # remember for later calls that omit it
            self._on_word_pending({**args, "caller_name": caller})
            await self._session.send_tool_response(
                function_responses=[types.FunctionResponse(
                    id=call_id, name=name,
                    response={"output": "Shown to caller, awaiting confirmation."},
                )]
            )

        elif name == "save_family_word":
            caller = args.get("caller_name") or self._added_by
            self._added_by = caller  # remember for later calls that omit it
            entry = await dictionary.save(args, caller)
            if entry:
                self._on_word(entry)
            await self._session.send_tool_response(
                function_responses=[types.FunctionResponse(
                    id=call_id, name=name,
                    response={"output": "Word saved." if entry else "Word already exists."},
                )]
            )

        elif name == "discard_family_word":
            self._on_word_discarded()
            await self._session.send_tool_response(
                function_responses=[types.FunctionResponse(
                    id=call_id, name=name,
                    response={"output": "Word discarded."},
                )]
            )

        elif name == "highlight_family_word":
            terms = [t.strip() for t in (args.get("terms") or []) if isinstance(t, str) and t.strip()]
            if terms:
                self._on_word_mentioned(terms)
            await self._session.send_tool_response(
                function_responses=[types.FunctionResponse(
                    id=call_id, name=name,
                    response={"output": "Highlighted." if terms else "No terms given."},
                )]
            )