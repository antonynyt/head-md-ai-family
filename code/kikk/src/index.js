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

  watchButton({
    onPickUp: async () => {
      if (session) return;
      console.log('[button] pick-up → starting session');
      broadcast({ type: 'session:start' });

      try {
        session = await createGeminiSession({
          onAudioChunk: (pcm) => audio.play(pcm),
          onTranscript: (msg) => broadcast({ type: 'transcript', ...msg }),
          onWord: async (word) => {
            await dictionary.save(word);
            broadcast({ type: 'word:saved', word });
          },
          onInterrupt: () => {
            audio.stopPlayback();
            broadcast({ type: 'interrupted' });
          },
          onClose: () => {
            audio.stopCapture();
            session = null;
            broadcast({ type: 'session:end' });
          },
        });

        if (!session) return;
        audio.startCapture((pcm) => session?.sendAudio(pcm));

      } catch (err) {
        console.error('[session] failed to start:', err.message);
        broadcast({ type: 'session:error', message: err.message });
        session = null;
      }
    },

    onHangUp: async () => {
      if (!session) return;
      console.log('[button] hang-up → ending session');
      session.endAudio();
      audio.stopCapture();
      await session.close().catch(() => {});
      session = null;
      broadcast({ type: 'session:end' });
    },
  });

  server.listen(PORT, () => {
    console.log(`[server] http://0.0.0.0:${PORT}  ws://0.0.0.0:${PORT}`);
  });
}

main().catch((err) => {
  console.error('[fatal]', err);
  process.exit(1);
});
