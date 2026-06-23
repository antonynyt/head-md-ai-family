'use strict';

const { spawn } = require('child_process');
const { MIC_DEVICE, SPK_DEVICE } = require('./config');

const MIC_CHUNK_BYTES = 640; // ~20ms at 16kHz 16-bit mono

function createAudio() {
  let micProcess = null;
  let spkProcess = null;
  let micBuffer  = Buffer.alloc(0);

  function startCapture(onChunk) {
    if (micProcess) return;

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

  function play(pcm) {
    if (!spkProcess) {
      spkProcess = spawn('sox', [
        '-t', 'raw', '-r', '24000', '-e', 'signed-integer', '-b', '16', '-c', '1', '-L', '-',
        '-t', 'alsa', SPK_DEVICE,
      ]);
      spkProcess.stderr.on('data', (d) => process.stdout.write('[sox/spk] ' + d));
      spkProcess.on('close', () => { spkProcess = null; });
      console.log(`[audio] speaker ready (${SPK_DEVICE})`);
    }
    spkProcess.stdin.write(pcm);
  }

  function stopPlayback() {
    if (!spkProcess) return;
    spkProcess.kill('SIGTERM');
    spkProcess = null;
    console.log('[audio] playback stopped (interrupted)');
  }

  return { startCapture, stopCapture, play, stopPlayback };
}

module.exports = { createAudio };
