#!/bin/bash

WAIT=7

echo "── Detecting devices ────────────────────────────────────"

# ── Audio ─────────────────────────────────────────────────────────────────────
AUDIO_CARD=$(arecord -l 2>/dev/null | grep -i "usb" | head -1)

if [ -z "$AUDIO_CARD" ]; then
  echo "[audio] no USB audio device found"
  MIC_DEVICE="default"
else
  CARD_NUM=$(echo "$AUDIO_CARD" | grep -oP 'card \K[0-9]+')
  DEV_NUM=$(echo "$AUDIO_CARD"  | grep -oP 'device \K[0-9]+')
  CARD_NAME=$(echo "$AUDIO_CARD" | grep -oP '\[.*?\]' | head -1 | tr -d '[]')
  MIC_DEVICE="hw:${CARD_NUM},${DEV_NUM}"
  echo "[audio] $CARD_NAME → $MIC_DEVICE"
fi

# ── Button ────────────────────────────────────────────────────────────────────
echo ""
echo "[button] unplug the button now — waiting ${WAIT}s..."
sleep $WAIT

BEFORE=$(ls /dev/input/event* 2>/dev/null)

echo "[button] plug the button back in — waiting ${WAIT}s..."
sleep $WAIT

AFTER=$(ls /dev/input/event* 2>/dev/null)
NEW_EVENTS=$(comm -13 <(echo "$BEFORE" | sort) <(echo "$AFTER" | sort))

if [ -z "$NEW_EVENTS" ]; then
  echo "[button] no new input device detected"
  BUTTON_EVENT="unknown"
else
  BUTTON_EVENT=$(echo "$NEW_EVENTS" | head -1)
  BUTTON_NAME=$(cat /sys/class/input/$(basename "$BUTTON_EVENT")/device/name 2>/dev/null || echo "unknown")
  echo "[button] $BUTTON_NAME → $BUTTON_EVENT"
fi

# ── Result ────────────────────────────────────────────────────────────────────
echo ""
echo "── Copy to your .env ────────────────────────────────────"
echo "MIC_DEVICE=$MIC_DEVICE"
echo "SPK_DEVICE=$MIC_DEVICE"
echo "BUTTON_EVENT_PATH=$BUTTON_EVENT"