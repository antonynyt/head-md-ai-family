# Familect

Family dictionary voice assistant — telephone operator persona, Raspberry Pi.

## Setup

```bash
# System dependencies
sudo apt install libspeexdsp-dev python3-pip

# Python dependencies
pip install -r requirements.txt --break-system-packages

# Find your audio devices
python3 -m sounddevice

# Find your button event device
sudo evtest
```

Update `src/config.py` with your:
- `MIC_DEVICE` and `SPK_DEVICE` — from `python3 -m sounddevice`
- `BUTTON_EVENT_PATH` — from `sudo evtest`

## Run

```bash
GEMINI_API_KEY=your_key python3 main.py
# or: export GEMINI_API_KEY=your_key && python3 main.py
```

## iPad UI

Open `http://<pi-ip>:3000` on the iPad.
WebSocket events arrive on `ws://<pi-ip>:3001`.

## Project structure

```
main.py           — entry point, wires everything together
src/
  config.py       — all tunable constants
  audio.py        — sounddevice mic/speaker with AEC
  gemini.py       — Gemini Live API session
  broadcaster.py  — WebSocket broadcast to iPad
  button.py       — Linux input event device watcher
  dictionary.py   — familect.json read/write
  server.py       — static HTTP server for iPad UI
public/
  index.html      — iPad UI (you build this)
prompt.txt        — optional custom system prompt
familect.json     — auto-created on first run
```

## Ports

| Port | Protocol | Purpose              |
|------|----------|----------------------|
| 3000 | HTTP     | iPad UI static files |
| 3001 | WS       | Live event stream    |

## WebSocket events (→ iPad)

```json
{ "type": "session:start" }
{ "type": "session:end" }
{ "type": "session:error", "message": "..." }
{ "type": "transcript", "text": "...", "turn": "user"|"model" }
{ "type": "word:saved", "word": { "term", "definition", "example", "added_by", "saved_at" } }
{ "type": "interrupted" }
{ "type": "dictionary:init", "words": [...] }
```
