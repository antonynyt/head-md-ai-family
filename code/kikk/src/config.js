'use strict';

module.exports = {
  PORT: 3000,

  // Gemini — get your key at https://aistudio.google.com/apikey
  GEMINI_API_KEY: process.env.GEMINI_API_KEY || '',
  GEMINI_MODEL:   'gemini-3.1-flash-live-preview',
  GEMINI_VOICE:   'Aoede', // Puck | Charon | Kore | Fenrir | Aoede

  // Button — find your device with: sudo evtest
  BUTTON_EVENT_PATH: '/dev/input/event5',

  // Audio devices — find yours with: arecord -l (mic) and aplay -l (speaker)
  MIC_DEVICE: 'hw:3,0',
  SPK_DEVICE: 'hw:3,0',

  // Where to write familect.json
  DICT_PATH: './familect.json',
};
