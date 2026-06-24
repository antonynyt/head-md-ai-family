"""Familect configuration — edit this file for your hardware."""
import os

# ── Server ────────────────────────────────────────────────────────────────────
PORT = 3000

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-3.1-flash-live-preview"
GEMINI_VOICE   = "Charon"   # Puck | Charon | Kore | Fenrir | Aoede

# ── Button ────────────────────────────────────────────────────────────────────
# Linux input event device — find yours with: sudo evtest
# BUTTON_EVENT_PATH = "/dev/input/event5"
BUTTON_EVENT_PATH = "keyboard"

# ── Audio ─────────────────────────────────────────────────────────────────────
# Find device names with: python3 -m sounddevice
# None = system default. On the Pi use e.g. "hw:3,0"
MIC_DEVICE = None
SPK_DEVICE = None

# Gemini fixed rates — do not change
GEMINI_IN_RATE  = 16_000   # mic → Gemini
GEMINI_OUT_RATE = 24_000   # Gemini → speaker

# Speaker bleed suppression — mute mic for this many seconds at the start of
# each AI turn, as a lightweight alternative to AEC
BLEED_SUPPRESS_SECS = 2.0

# ── Dictionary ────────────────────────────────────────────────────────────────
HERE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DICT_PATH  = os.path.join(HERE, "familect.json")
PROMPT_FILE = os.path.join(HERE, "prompt.txt")
PUBLIC_DIR  = os.path.join(HERE, "public")