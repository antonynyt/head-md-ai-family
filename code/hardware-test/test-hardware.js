'use strict';

require('dotenv').config();

const { execSync, spawn } = require('child_process');
const HID = require('node-hid');

function log(tag, msg) { console.log(`[${tag}] ${msg}`); }
function section(title) { console.log(`\n── ${title} ────────────────────────────────────`); }
// ── 1. List audio devices ─────────────────────────────────────────────────────

section('Audio devices');
try {
  console.log(execSync('arecord -l 2>&1').toString().trim());
} catch {
  log('audio', 'arecord not found — run: sudo apt install alsa-utils sox');
}

// ── 2. List HID devices ───────────────────────────────────────────────────────

section('HID devices');
for (const d of HID.devices()) {
  console.log(
    `  ${(d.product || '(unnamed)').padEnd(30)}` +
    `  vendor=0x${d.vendorId.toString(16).padStart(4,'0')}` +
    `  product=0x${d.productId.toString(16).padStart(4,'0')}`
  );
}

// ── 3. Mic: record 3s then play back ─────────────────────────────────────────

section('Mic test — recording 3s');
const MIC = process.env.MIC_DEVICE || 'default';
const SPK = process.env.SPK_DEVICE || 'default';

const rec = spawn('sox', [
  '-t', 'alsa', MIC,
  '-t', 'raw', '-r', '16000', '-e', 'signed-integer', '-b', '16', '-c', '1', '-L', '-',
]);

const chunks = [];
rec.stdout.on('data', (d) => chunks.push(d));
rec.stderr.on('data', (d) => process.stdout.write('[sox] ' + d));

setTimeout(() => {
  rec.kill();
  const pcm = Buffer.concat(chunks);
  log('mic', `captured ${pcm.length} bytes — playing back …`);

  const play = spawn('sox', [
    '-t', 'raw', '-r', '16000', '-e', 'signed-integer', '-b', '16', '-c', '1', '-L', '-',
    '-t', 'alsa', SPK,
  ]);
  play.stderr.on('data', (d) => process.stdout.write('[sox] ' + d));
  play.stdin.write(pcm);
  play.stdin.end();
  play.on('close', () => {
    log('mic', 'playback done');
    testButton();
  });
}, 3000);

// ── 4. Button: watch until first press + release, then exit ───────────────────

function testButton() {
  section('Button test — press and release the button');

  const vendorId  = process.env.BUTTON_VENDOR_ID  ? parseInt(process.env.BUTTON_VENDOR_ID,  16) : null;
  const productId = process.env.BUTTON_PRODUCT_ID ? parseInt(process.env.BUTTON_PRODUCT_ID, 16) : null;

  let device;
  try {
    if (vendorId && productId) {
      device = new HID.HID(vendorId, productId);
      log('button', `opened 0x${vendorId.toString(16)}:0x${productId.toString(16)}`);
    } else {
      const candidate = HID.devices().find(
        (d) => d.usagePage !== 0x01 || (d.usage !== 0x02 && d.usage !== 0x06)
      );
      if (!candidate) { log('button', 'no suitable HID device found'); process.exit(1); }
      device = new HID.HID(candidate.vendorId, candidate.productId);
      log('button', `auto-detected "${candidate.product || 'unnamed'}"`);
    }
  } catch (err) {
    log('button', `failed to open: ${err.message}`);
    process.exit(1);
  }

  const PRESS_BYTE  = parseInt(process.env.BUTTON_PRESS_BYTE  ?? '0', 10);
  const PRESS_VALUE = parseInt(process.env.BUTTON_PRESS_VALUE ?? '1', 10);
  let pressed = false;

  device.on('data', (data) => {
    process.stdout.write(`  raw: [${Array.from(data).join(', ')}]\r`);

    const isPressed = data[PRESS_BYTE] === PRESS_VALUE;
    if (isPressed && !pressed) {
      pressed = true;
      console.log('\n  ↑ pick-up  (pressed)');
    }
    if (!isPressed && pressed) {
      console.log('  ↓ hang-up  (released)');
      log('button', 'all tests passed ✓');
      device.close();
      process.exit(0);
    }
  });

  device.on('error', (err) => { log('button', `error: ${err.message}`); process.exit(1); });
}