'use strict';

const fs = require('fs');
const { BUTTON_EVENT_PATH } = require('./config');

const EVENT_SIZE = 24;
const EV_KEY     = 1;

function watchButton({ onPickUp, onHangUp }) {
  let buf     = Buffer.alloc(0);
  let pressed = false;

  const stream = fs.createReadStream(BUTTON_EVENT_PATH);

  stream.on('error', (err) => {
    console.error(`[button] cannot open ${BUTTON_EVENT_PATH}: ${err.message}`);
    console.error('[button] try: sudo node src/index.js  or  sudo usermod -aG input $USER');
    process.exit(1);
  });

  stream.on('data', (chunk) => {
    buf = Buffer.concat([buf, chunk]);
    while (buf.length >= EVENT_SIZE) {
      const type  = buf.readUInt16LE(16);
      const value = buf.readInt32LE(20);
      buf = buf.subarray(EVENT_SIZE);

      if (type !== EV_KEY) continue;

      // value 1 = press, value 0 = release, value 2 = repeat (ignore)
      // Phone button: unpressed = pick-up (circuit closes), pressed = hang-up
      if (value === 0 && !pressed) { pressed = true;  console.log('[button] ↑ pick-up');  onPickUp();  }
      if (value === 1 && pressed)  { pressed = false; console.log('[button] ↓ hang-up');  onHangUp();  }
    }
  });

  console.log(`[button] watching ${BUTTON_EVENT_PATH}`);
}

module.exports = { watchButton };
