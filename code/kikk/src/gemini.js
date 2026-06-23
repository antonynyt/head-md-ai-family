'use strict';

const { GoogleGenAI, Modality } = require('@google/genai');
const { GEMINI_API_KEY, GEMINI_MODEL, GEMINI_VOICE } = require('./config');

const SYSTEM_PROMPT = `You are a warm, curious conversationalist helping families rediscover
private words and phrases unique to their household — their familect.
Listen attentively. Ask gentle questions. When you detect a family word or phrase
(something invented, mispronounced, or with a meaning only this family would know),
call the save_family_word tool.`;

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

async function createGeminiSession({ onAudioChunk, onTranscript, onWord, onInterrupt, onClose }) {
  if (!GEMINI_API_KEY) throw new Error('GEMINI_API_KEY is not set in src/config.js');

  const ai = new GoogleGenAI({ apiKey: GEMINI_API_KEY });

  const session = await ai.live.connect({
    model: GEMINI_MODEL,
    config: {
      responseModalities: [Modality.AUDIO],
      systemInstruction: { parts: [{ text: SYSTEM_PROMPT }] },
      speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: GEMINI_VOICE } } },
      inputAudioTranscription:  {},
      outputAudioTranscription: {},
      tools: [{ functionDeclarations: [SAVE_WORD_TOOL] }],
    },
    callbacks: {
      onopen:  () => console.log('[gemini] session open'),
      onclose: (e) => {
        console.log('[gemini] session closed', e?.code ?? '');
        if (onClose) onClose();
      },
      onerror: (e) => console.error('[gemini] error:', e.message ?? e),
      onmessage: (msg) => {
        const content = msg?.serverContent;
        if (!content) return;

        // Audio output — process ALL parts
        if (content.modelTurn?.parts) {
          for (const part of content.modelTurn.parts) {
            if (part.inlineData?.mimeType?.startsWith('audio/'))
              onAudioChunk(Buffer.from(part.inlineData.data, 'base64'));
          }
        }

        // Transcripts (native audio model uses these, not modelTurn text)
        if (content.inputTranscription?.text)
          onTranscript({ text: content.inputTranscription.text, turn: 'user', final: true });

        if (content.outputTranscription?.text)
          onTranscript({ text: content.outputTranscription.text, turn: 'model', final: false });

        // Interruption — user spoke over the model
        if (content.interrupted) {
          console.log('[gemini] interrupted');
          if (onInterrupt) onInterrupt();
        }

        // Function call
        if (content.modelTurn?.parts) {
          for (const part of content.modelTurn.parts) {
            if (part.functionCall?.name === 'save_family_word')
              onWord({ ...part.functionCall.args, savedAt: new Date().toISOString() });
          }
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
    endAudio() {
      // Flush any cached audio on the server when mic stops
      try {
        session.sendRealtimeInput({ audioStreamEnd: true });
      } catch (_) {}
    },
    async close() {
      await session.close().catch(() => {});
    },
  };
}

module.exports = { createGeminiSession };
