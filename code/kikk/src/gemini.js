'use strict';

const fs = require('fs').promises;
const path = require('path');
const { GoogleGenAI, Modality } = require('@google/genai');
const { GEMINI_API_KEY, GEMINI_MODEL, GEMINI_VOICE } = require('./config');
const dictionary = require('./dictionary');

// ── Prompt ────────────────────────────────────────────────────────────────────

const PROMPT_FILE = path.join(__dirname, '..', 'prompt.txt');

const SYSTEM_SUFFIX = `
You are a warm, unhurried telephone operator from the 1950s helping a family preserve their private language in a dictionary called Familect.
Your voice is gentle, unhurried, and slightly formal — like someone who has handled a thousand calls and genuinely enjoys every one.

INTERRUPTION RULES (very important):
- If the caller interrupts you mid-sentence, stop speaking immediately. Do not finish your sentence.
- Acknowledge the interruption with a brief operator phrase such as "Oh, pardon me — go right ahead." or "Of course, I'm listening."
- If you were mid-thought and it makes sense to return to it, you may say "As I was saying..." before continuing.
- Short sounds like "mm", "uh-huh", or a brief cough are probably not real interruptions. Use your judgment — if no clear word was spoken, you may simply continue naturally without acknowledgement.
- Never repeat yourself word-for-word after an interruption. Summarise or rephrase.

DICTIONARY RULES:
- When the caller shares or defines a new family word, call save_family_word immediately — do not describe what you are doing, just call it.
- At the start, mention only the total word count. Never list words unprompted.
- If asked about existing words, describe them fully and warmly.
- After saving a word ask: "Shall we add another word, or have we said our goodbyes for today?"
- When the conversation is finished and you have said a warm goodbye, call end_conversation.`;

// ── Tools ─────────────────────────────────────────────────────────────────────

const SAVE_WORD_TOOL = {
  name: 'save_family_word',
  description: "Call this when you detect a word or phrase that belongs to this family's private language.",
  parameters: {
    type: 'object',
    properties: {
      term:       { type: 'string', description: 'The word or phrase as the family uses it' },
      definition: { type: 'string', description: "What it means in this family's context" },
      example:    { type: 'string', description: 'A short example sentence' },
    },
    required: ['term', 'definition'],
  },
};

const END_CONVERSATION_TOOL = {
  name: 'end_conversation',
  description: 'Call this after you have said a warm goodbye to end the session.',
  parameters: { type: 'object', properties: {} },
};

// ── System prompt builder ─────────────────────────────────────────────────────

async function buildDictionaryContext() {
  const entries = await dictionary.load();
  if (!entries.length) return 'The Familect dictionary is currently empty.';
  const lines = [`The Familect dictionary holds ${entries.length} word(s):`];
  for (const e of entries) {
    let line = `- ${e.term} (added by ${e.addedBy || 'unknown'}): ${e.definition || ''}`;
    if (e.example) line += ` — "${e.example}"`;
    lines.push(line);
  }
  return lines.join('\n');
}

async function loadSystemPrompt() {
  let template = '';
  try {
    template = await fs.readFile(PROMPT_FILE, 'utf8');
  } catch {
    console.warn('[gemini] prompt.txt not found, using built-in persona');
    template = '';
  }

  const context = await buildDictionaryContext();
  if (template.includes('{{FAMILECT_STATS}}')) {
    template = template.replace('{{FAMILECT_STATS}}', context);
  } else {
    template = template ? template + '\n\n' + context : context;
  }

  return template + '\n\n' + SYSTEM_SUFFIX;
}

// ── Interruption gate ─────────────────────────────────────────────────────────
//
// The problem: Gemini fires `interrupted` the moment VAD detects sound —
// before transcription has arrived. So checking word count at interruption
// time always returns 0 and the gate never triggers.
//
// The fix: when `interrupted` fires, we start a short timer (INTERRUPT_WAIT_MS).
// During that window, if a transcript arrives with enough real words, we
// immediately confirm it as a real interruption and kill the speaker.
// If the timer expires with no words, we discard it as noise and do nothing.
//
// This maps naturally to the telephone operator character: rather than cutting
// out the moment they hear a sound, they pause for a beat to confirm someone
// is actually speaking before gracefully stopping.

const INTERRUPT_WAIT_MS    = 400; // how long to wait for transcript after interrupted signal
const MIN_WORDS_TO_CONFIRM = 2;   // minimum words to treat as a real interruption

function createInterruptGate(onConfirmed) {
  let waitTimer    = null; // pending interruption timer
  let wordsSeen    = 0;    // words accumulated since interrupted signal
  let waitingForConfirm = false;

  // Called when Gemini fires content.interrupted
  function arm() {
    if (waitingForConfirm) return; // already armed, ignore duplicate signals
    waitingForConfirm = true;
    wordsSeen = 0;
    console.log('[gate] armed — waiting for transcript');

    waitTimer = setTimeout(() => {
      // Timer expired with no words → noise, discard
      console.log('[gate] expired — no words, treating as noise');
      disarm();
    }, INTERRUPT_WAIT_MS);
  }

  // Called when inputTranscription arrives
  function onTranscript(text) {
    if (!waitingForConfirm) return;

    const count = text.trim().split(/\s+/).filter(Boolean).length;
    wordsSeen += count;
    console.log(`[gate] transcript received — words so far: ${wordsSeen}`);

    if (wordsSeen >= MIN_WORDS_TO_CONFIRM) {
      clearTimeout(waitTimer);
      console.log('[gate] confirmed real interruption');
      disarm();
      onConfirmed();
    }
  }

  // Reset everything — called on disarm and on new model turn
  function disarm() {
    clearTimeout(waitTimer);
    waitTimer = null;
    waitingForConfirm = false;
    wordsSeen = 0;
  }

  return { arm, onTranscript, disarm };
}

// ── Session factory ───────────────────────────────────────────────────────────

async function createGeminiSession({
  onAudioChunk,
  onTranscript,
  onWord,
  onInterrupt,
  onResume,
  onClose,
  initialPrompt,
}) {
  if (!GEMINI_API_KEY) throw new Error('GEMINI_API_KEY is not set in src/config.js');

  const systemPrompt = await loadSystemPrompt();
  const ai           = new GoogleGenAI({ apiKey: GEMINI_API_KEY });

  // Whether we confirmed a real interruption and are waiting for the next turn.
  let interrupted = false;

  const gate = createInterruptGate(() => {
    // Runs when the gate confirms a real interruption
    interrupted = true;
    console.log('[gemini] real interruption confirmed — killing speaker');
    if (onInterrupt) onInterrupt();
  });

  const session = await ai.live.connect({
    model: GEMINI_MODEL,
    config: {
      responseModalities: [Modality.AUDIO],
      systemInstruction: { parts: [{ text: systemPrompt }] },
      speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: GEMINI_VOICE } } },
      inputAudioTranscription:  {},
      outputAudioTranscription: {},
      tools: [{ functionDeclarations: [SAVE_WORD_TOOL, END_CONVERSATION_TOOL] }],
    },
    callbacks: {
      onopen:  () => console.log('[gemini] session open'),
      onclose: (e) => {
        console.log('[gemini] session closed', e?.code ?? '');
        gate.disarm();
        if (onClose) onClose();
      },
      onerror: (e) => console.error('[gemini] error:', e.message ?? e),

      onmessage: (msg) => {

        // ── Setup complete → send initial prompt ───────────────────────────
        if (msg.setupComplete) {
          console.log('[gemini] setup complete');
          const prompt = initialPrompt || '[The telephone has been picked up. Begin the conversation.]';
          try {
            session.sendRealtimeInput({ text: prompt });
            console.log('[gemini] initial prompt sent');
          } catch (err) {
            console.warn('[gemini] failed to send initial prompt:', err.message);
          }
        }

        const content = msg?.serverContent;
        if (!content) return;

        // ── Interruption signal ────────────────────────────────────────────
        // Arm the gate. It will wait up to INTERRUPT_WAIT_MS for a transcript
        // before deciding whether this is real speech or noise.
        if (content.interrupted) {
          console.log('[gemini] interrupted signal received');
          gate.arm();
        }

        // ── Model turn ────────────────────────────────────────────────────
        if (content.modelTurn?.parts) {
          // A new model turn means Gemini has started responding.
          // Disarm any pending gate — we no longer need to act on the
          // interruption signal since Gemini has already moved on.
          gate.disarm();

          if (interrupted) {
            interrupted = false;
            console.log('[gemini] new turn after interruption — resuming');
            if (onResume) onResume();
          }

          for (const part of content.modelTurn.parts) {
            if (part.inlineData?.mimeType?.startsWith('audio/')) {
              onAudioChunk(Buffer.from(part.inlineData.data, 'base64'));
            }

            if (part.functionCall?.name === 'save_family_word') {
              onWord({ ...part.functionCall.args, savedAt: new Date().toISOString() });
            }

            if (part.functionCall?.name === 'end_conversation') {
              console.log('[gemini] end_conversation called — closing session');
              session.close().catch(() => {});
            }
          }
        }

        // ── Transcripts ───────────────────────────────────────────────────
        if (content.inputTranscription?.text) {
          // Feed into gate first — it may confirm the interruption immediately
          gate.onTranscript(content.inputTranscription.text);
          onTranscript({ text: content.inputTranscription.text, turn: 'user', final: true });
        }
        if (content.outputTranscription?.text) {
          onTranscript({ text: content.outputTranscription.text, turn: 'model', final: false });
        }
      },
    },
  });

  return {
    sendAudio(pcm) {
      try {
        session.sendRealtimeInput({
          audio: { data: pcm.toString('base64'), mimeType: 'audio/pcm;rate=16000' },
        });
      } catch (err) {
        console.warn('[gemini] sendAudio error:', err.message);
      }
    },
    sendText(text) {
      try {
        session.sendRealtimeInput({ text });
      } catch (err) {
        console.warn('[gemini] sendText error:', err.message);
      }
    },
    endAudio() {
      try {
        session.sendRealtimeInput({ audioStreamEnd: true });
      } catch (_) {}
    },
    async close() {
      gate.disarm();
      await session.close().catch(() => {});
    },
  };
}

module.exports = { createGeminiSession };