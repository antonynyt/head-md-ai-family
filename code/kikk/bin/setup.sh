#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE="${PROJECT_DIR}/src/config.py"

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "Config file not found: ${CONFIG_FILE}" >&2
  exit 1
fi

if [[ ! -x "${PROJECT_DIR}/.venv/bin/python" ]] || ! "${PROJECT_DIR}/.venv/bin/python" -m pip --version >/dev/null 2>&1; then
  echo "Virtual environment missing or broken; creating it..."
  "${PROJECT_DIR}/bin/install.sh"
else
  echo "Virtual environment found at ${PROJECT_DIR}/.venv"
fi

# Use the sounddevice index for config, not the human-readable ALSA card name.
DEVICE_NAME="Native Union POP Phone"
DEVICE_INDEX=""
CARD_INDEX=""

if [[ -x "${PROJECT_DIR}/.venv/bin/python" ]]; then
  SOUNDDEV_OUT="${PROJECT_DIR}/.venv/bin/python -m sounddevice 2>/dev/null || true"
  SOUNDDEV_RESULT="$(eval "${SOUNDDEV_OUT}" 2>/dev/null || true)"
else
  SOUNDDEV_RESULT="$(python3 -m sounddevice 2>/dev/null || true)"
fi

if [[ -n "${SOUNDDEV_RESULT}" ]]; then
  SOUNDDEV_MATCH="$(printf '%s\n' "${SOUNDDEV_RESULT}" | grep -i 'Native Union POP Phone\|Native Union\|POP Phone\|POP PHONE' | head -n1 || true)"
  if [[ -n "${SOUNDDEV_MATCH}" ]]; then
    DEVICE_INDEX="$(printf '%s\n' "${SOUNDDEV_MATCH}" | sed -E 's/.*[^0-9]([0-9]+)[[:space:]]+Native Union.*$/\1/' | head -n1)"
    DEVICE_NAME="$(printf '%s\n' "${SOUNDDEV_MATCH}" | sed -E 's/^.*[0-9][[:space:]]+(.+)$/\1/' | head -n1)"
  fi
fi

if command -v aplay >/dev/null 2>&1; then
  echo
  echo "== ALSA audio devices =="
  aplay -l 2>/dev/null || true
  ALSA_MATCH="$(aplay -l 2>/dev/null | grep -iE 'Native Union|POP Phone|POP PHONE' | head -n1 || true)"
  if [[ -n "${ALSA_MATCH}" ]]; then
    CARD_INDEX="$(printf '%s\n' "${ALSA_MATCH}" | sed -E 's/^.*carte[[:space:]]+([0-9]+).*$/\1/' | head -n1)"
    if [[ -z "${DEVICE_NAME}" ]]; then
      DEVICE_NAME="Native Union POP Phone"
    fi
  fi
fi

if [[ -z "${DEVICE_INDEX}" ]]; then
  DEVICE_INDEX="1"
fi

if [[ -z "${CARD_INDEX}" ]]; then
  CARD_INDEX="3"
fi

BUTTON_PATH=""
if command -v evtest >/dev/null 2>&1; then
  for dev in /dev/input/event*; do
    [[ -e "$dev" ]] || continue
    if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
      if sudo -n evtest "$dev" >/tmp/kikk_evtest.$$ 2>/dev/null; then
        if grep -Eqi 'GPIO|button|hid|input device|USB' /tmp/kikk_evtest.$$; then
          BUTTON_PATH="$dev"
          break
        fi
      fi
    fi
  done
fi

if [[ -z "${BUTTON_PATH}" ]]; then
  for dev in $(ls /dev/input/event* 2>/dev/null | sort); do
    [[ -n "$dev" ]] && BUTTON_PATH="$dev" && break
  done
fi

if [[ -z "${BUTTON_PATH}" ]]; then
  BUTTON_PATH="/dev/input/event4"
fi

# Validate the chosen button device by asking for an actual press.
if command -v evtest >/dev/null 2>&1; then
  echo
  echo "== Press validation =="
  echo "Press the hardware button once now. This script will wait until it sees a real event on ${BUTTON_PATH}."
  sudo -n evtest "${BUTTON_PATH}" 2>/tmp/kikk_press.$$ | head -n 30
  if grep -Eqi 'Event:|type|code|value' /tmp/kikk_press.$$; then
    echo "Button event detected on ${BUTTON_PATH}."
  else
    echo "No button event was detected; keeping the default path ${BUTTON_PATH}."
  fi
  rm -f /tmp/kikk_press.$$ 2>/dev/null || true
fi

if [[ -z "${DEVICE_NAME}" ]]; then
  DEVICE_NAME="Native Union POP Phone"
fi

printf '\n== Detected values ==\n'
printf 'BUTTON_EVENT_PATH = %s\n' "$BUTTON_PATH"
printf 'MIC_DEVICE = %s\n' "$DEVICE_INDEX"
printf 'SPK_DEVICE = %s\n' "$DEVICE_INDEX"
printf 'ALSA card for mixer = %s\n' "$CARD_INDEX"

python3 - "$CONFIG_FILE" "$BUTTON_PATH" "$DEVICE_INDEX" <<'PY'
import re
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
button_path = sys.argv[2]
device_index = sys.argv[3]
text = config_path.read_text()
repl = {
    r'BUTTON_EVENT_PATH\s*=\s*.*': f'BUTTON_EVENT_PATH = "{button_path}"',
    r'MIC_DEVICE\s*=\s*.*': f'MIC_DEVICE = {device_index}',
    r'SPK_DEVICE\s*=\s*.*': f'SPK_DEVICE = {device_index}',
}
new_text = text
for pattern, replacement in repl.items():
    new_text = re.sub(pattern, replacement, new_text, count=1, flags=re.MULTILINE)
config_path.write_text(new_text)
print(f"Updated {config_path}")
PY

# Set the speaker to 80% on the correct ALSA card, not the default one.
if command -v amixer >/dev/null 2>&1; then
  echo
  echo "== Setting speaker to 80% on ALSA card ${CARD_INDEX} =="
  amixer -c "${CARD_INDEX}" sset Speaker 80% 2>/dev/null || \
  amixer -c "${CARD_INDEX}" sset PCM 80% 2>/dev/null || \
  amixer -c "${CARD_INDEX}" sset Master 80% 2>/dev/null || \
  echo "amixer could not set the volume on card ${CARD_INDEX}; use alsamixer -c ${CARD_INDEX} and select the Native Union device manually."
elif command -v alsamixer >/dev/null 2>&1; then
  echo
  echo "== Setting speaker to 80% on ALSA card ${CARD_INDEX} =="
  alsamixer -c "${CARD_INDEX}" set Speaker 80% 2>/dev/null || \
  alsamixer -c "${CARD_INDEX}" set PCM 80% 2>/dev/null || \
  alsamixer -c "${CARD_INDEX}" set Master 80% 2>/dev/null || \
  echo "alsamixer could not set the volume on card ${CARD_INDEX}; use the GUI and select the Native Union device manually."
else
  echo
  echo "== Speaker volume =="
  echo "No amixer or alsamixer found; install ALSA utils to set Speaker to 80% on the Native Union card."
fi

rm -f /tmp/kikk_evtest.$$ 2>/dev/null || true

echo

echo "Setup complete."
