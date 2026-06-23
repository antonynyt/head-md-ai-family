'use strict';

const { createServer }        = require('./server');
const { createBroadcaster }   = require('./broadcaster');
const { watchButton }         = require('./button');
const { createGeminiSession } = require('./gemini');
const { createAudio }         = require('./audio');
const dictionary              = require('./dictionary');
const { PORT }                = require('./config');

async function main() {
  const server    = createServer();
  const broadcast = createBroadcaster(server);
  const audio     = createAudio();

  let session = null;

  // ── Session lifecycle ─────────────────────────────────────────────────────

  async function startSession() {
    if (session) return;
    console.log('[index] pick-up → starting session');
    broadcast({ type: 'session:start' });

    try {
      session = await createGeminiSession({
        onAudioChunk: (pcm) => audio.play(pcm),

        onTranscript: (msg) => broadcast({ type: 'transcript', ...msg }),

        onWord: async (word) => {
          await dictionary.save(word);
          broadcast({ type: 'word:saved', word });
        },

        // Called only when the speech gate decides it's a real interruption.
        // Kills the speaker immediately, clearing the ALSA buffer so the
        // operator's voice stops at once rather than draining buffered audio.
        onInterrupt: () => {
          console.log('[index] real interruption — stopping speaker');
          audio.interruptPlayback();
          broadcast({ type: 'interrupted' });
        },

        // Called when Gemini starts its next model turn.
        // The speaker restarts automatically on the first new audio chunk.
        onResume: () => {
          console.log('[index] new turn — speaker will restart on first audio chunk');
          broadcast({ type: 'resumed' });
        },

        onClose: () => {
          audio.stopCapture();
          audio.stopPlayback();
          session = null;
          broadcast({ type: 'session:end' });
        },
      });

      if (!session) return;
      audio.startCapture((pcm) => session?.sendAudio(pcm));

    } catch (err) {
      console.error('[index] failed to start session:', err.message);
      broadcast({ type: 'session:error', message: err.message });
      session = null;
    }
  }

  async function endSession() {
    if (!session) return;
    console.log('[index] hang-up → ending session');
    session.endAudio();
    audio.stopCapture();
    audio.stopPlayback();
    await session.close().catch(() => {});
    session = null;
    broadcast({ type: 'session:end' });
  }

  // ── Hardware button ───────────────────────────────────────────────────────

  watchButton({ onPickUp: startSession, onHangUp: endSession });

  server.listen(PORT, () => {
    console.log(`[server] http://0.0.0.0:${PORT}  ws://0.0.0.0:${PORT}`);
  });
}

main().catch((err) => {
  console.error('[fatal]', err);
  process.exit(1);
});
