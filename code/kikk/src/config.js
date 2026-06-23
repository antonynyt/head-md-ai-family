'use strict';

module.exports = {
  PORT: 3000,

  // Gemini
  GEMINI_API_KEY: '',
  GEMINI_MODEL:   'gemini-3.1-flash-live-preview',
  GEMINI_VOICE:   'Aoede', // Puck | Charon | Kore | Fenrir | Aoede

  // Button — check with: sudo evtest
  BUTTON_EVENT_PATH: '/dev/input/event5',

  // Audio — check with: arecord -l
  MIC_DEVICE: 'hw:3,0',
  SPK_DEVICE: 'hw:3,0',

  // Where to write familect.json
  DICT_PATH: './familect.json',
};
