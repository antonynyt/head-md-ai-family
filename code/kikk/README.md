# Requirements on the RaspberryPi

- needs web access
- same wifi as the iPad
- `alsamixer` to set the volume of the handset

# Setup (on the pi!)

```bash
make setup
make install-service
```

`make install-service` needs `/home/kiki/.config/familect.env` to exist first — create it:

```bash
sudo mkdir -p /home/kiki/.config
sudo tee /home/kiki/.config/familect.env >/dev/null <<'EOF'
GEMINI_API_KEY=YOUR_KEY_HERE
EOF
sudo chown kiki:kiki /home/kiki/.config/familect.env
sudo chmod 600 /home/kiki/.config/familect.env
```

Keep the API key in this file.

## (if previous make commands doesn't work)

```bash
# make venv
python -m venv .venv
source .venv/bin/activate

# System dependencies
sudo apt install portaudio19-dev python3-pip

# Python dependencies
pip install -r requirements.txt

# Find your audio devices
python3 -m sounddevice

# Find your button event device
sudo evtest
```

Update `src/config.py` with your:
- `MIC_DEVICE` and `SPK_DEVICE` — from `python3 -m sounddevice`
- `BUTTON_EVENT_PATH` — from `sudo evtest`

## Build front end

```bash
cd frontend

npm install

npm run build
```

## Run (for dev)

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
  audio.py        — PyAudio mic/speaker with telephone bandpass filter
  gemini.py       — Gemini Live API session
  broadcaster.py  — WebSocket broadcast to iPad
  button.py       — Linux input event device watcher
  dictionary.py   — familect.json read/write
  server.py       — static HTTP server for iPad UI
frontend/
  dist/           — built iPad UI, served by src/server.py
bin/               — setup / install / service scripts (see Makefile)
kikk.service       — systemd unit for the backend
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
{ "type": "transcript", "text": "...", "turn": "user"|"model", "delay_ms": 0 }
{ "type": "word:pending", "word": { "term", "definition", "pronunciation", "part_of_speech", "example", "caller_name" } }
{ "type": "word:saved", "word": { "term", "definition", "example", "added_by", "saved_at" } }
{ "type": "word:highlight", "terms": ["..."] }
{ "type": "interrupted" }
{ "type": "dictionary:init", "words": [...] }
```
