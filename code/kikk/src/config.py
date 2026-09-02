"""Familect configuration — edit this file for your hardware."""
import os

# ── Server ────────────────────────────────────────────────────────────────────
PORT = 3000

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-3.1-flash-live-preview"
GEMINI_VOICE   = "Iapetus"   # Puck | Charon | Kore | Fenrir | Aoede

# ── Button ────────────────────────────────────────────────────────────────────
# Linux input event device — find yours with: sudo evtest
# BUTTON_EVENT_PATH = "/dev/input/event5"
BUTTON_EVENT_PATH = "keyboard"  # for testing without a button

# ── Audio ─────────────────────────────────────────────────────────────────────
# Find device names with: python3 -m sounddevice
# None = system default. On the Pi use e.g. "hw:3,0"
MIC_DEVICE = None
SPK_DEVICE = None

# Hardware-safe rates for the USB device
MIC_IN_RATE  = 48_000   # mic device rate
SPK_OUT_RATE = 48_000   # speaker device rate

# Gemini fixed rates — do not change
GEMINI_IN_RATE  = 16_000   # mic → Gemini payload
GEMINI_OUT_RATE = 24_000   # Gemini → speaker payload

# ── Dictionary ────────────────────────────────────────────────────────────────
HERE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DICT_PATH  = os.path.join(HERE, "familect.json")
PROMPT_FILE = os.path.join(HERE, "prompt.txt")
PUBLIC_DIR  = os.path.join(HERE, "frontend", "dist")