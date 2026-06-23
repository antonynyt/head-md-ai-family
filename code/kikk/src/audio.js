'use strict';

const { spawn } = require('child_process');
const { MIC_DEVICE, SPK_DEVICE } = require('./config');

// ~20 ms of audio at 16kHz 16-bit mono
const MIC_CHUNK_BYTES = 640;

function createAudio() {
  let micProcess = null;
  let spkProcess = null;
  let micBuffer  = Buffer.alloc(0);

  // ── Helpers ───────────────────────────────────────────────────────────────

  function killSpeaker(reason) {
    if (!spkProcess) return;
    const proc = spkProcess;
    spkProcess = null;
    try { proc.stdin.destroy(); } catch (_) {}
    proc.kill('SIGTERM');
    if (reason) console.log(`[audio] speaker killed (${reason})`);
  }

  // ── Mic capture ───────────────────────────────────────────────────────────

  function startCapture(onChunk) {
    if (micProcess) return;

    // Request 48kHz stereo from ALSA and let sox downsample to 16kHz mono
    // for Gemini (audio/pcm;rate=16000).
    micProcess = spawn('sox', [
      '-t', 'alsa', '-r', '48000', '-c', '2', MIC_DEVICE,
      '-t', 'raw', '-r', '16000', '-e', 'signed-integer', '-b', '16', '-c', '1', '-L', '-',
    ]);

    micProcess.stdout.on('data', (chunk) => {
      micBuffer = Buffer.concat([micBuffer, chunk]);
      while (micBuffer.length >= MIC_CHUNK_BYTES) {
        onChunk(micBuffer.subarray(0, MIC_CHUNK_BYTES));
        micBuffer = micBuffer.subarray(MIC_CHUNK_BYTES);
      }
    });

    micProcess.stderr.on('data', (d) => process.stdout.write('[sox/mic] ' + d));
    micProcess.on('close', () => { micProcess = null; });
    console.log(`[audio] mic started (${MIC_DEVICE})`);
  }

  function stopCapture() {
    if (!micProcess) return;
    micProcess.kill('SIGTERM');
    micProcess = null;
    micBuffer  = Buffer.alloc(0);
    console.log('[audio] mic stopped');
  }

  // ── Speaker playback ──────────────────────────────────────────────────────
  //
  // ONE long-running sox process stays alive for the whole model turn.
  // It is started on the first play() call and killed only on interrupt
  // or session end — never between chunks.
  //
  // cork()/uncork() around each write keeps the pipe in a "more data coming"
  // state so sox never sees an idle stdin and exits prematurely.

  function ensureSpeaker() {
    if (spkProcess) return;

    spkProcess = spawn('sox', [
      '-t', 'raw', '-r', '24000', '-e', 'signed-integer', '-b', '16', '-c', '1', '-L', '-',
      '-t', 'alsa', SPK_DEVICE,
    ], { stdio: ['pipe', 'pipe', 'pipe'] });

    spkProcess.stdin.cork();

    spkProcess.stderr.on('data', (d) => process.stdout.write('[sox/spk] ' + d));

    spkProcess.on('close', () => {
      spkProcess = null;
      console.log('[audio] speaker process closed');
    });

    spkProcess.stdin.on('error', (err) => {
      if (err.code !== 'EPIPE') {
        console.warn('[audio] speaker stdin error:', err.message);
      }
      spkProcess = null;
    });

    console.log(`[audio] speaker ready (${SPK_DEVICE})`);
  }

  function play(pcm) {
    ensureSpeaker();
    if (!spkProcess || !spkProcess.stdin.writable) return;

    spkProcess.stdin.uncork();
    spkProcess.stdin.write(pcm, (err) => {
      if (err && err.code !== 'EPIPE') {
        console.warn('[audio] speaker write error:', err.message);
      }
    });
    spkProcess.stdin.cork();
  }

  // ── Interrupt ─────────────────────────────────────────────────────────────
  // Kill the speaker immediately — clears the ALSA buffer so the operator's
  // voice stops at once. A new process starts on the next play() call.

  function interruptPlayback() {
    killSpeaker('interrupted by user');
  }

  // ── End of session ────────────────────────────────────────────────────────

  function stopPlayback() {
    killSpeaker('session ended');
  }

  return {
    startCapture,
    stopCapture,
    play,
    interruptPlayback,
    stopPlayback,
  };
}

module.exports = { createAudio };
