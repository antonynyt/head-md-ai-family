# Familect

Familect is a Raspberry Pi voice assistant flow using:
- a push button for activation control
- an NFC tag for profile selection
- Gemini real-time audio for conversation
- thermal printing for saved family words

## Project structure

- `main.py`: hardware entry point, waits for button + NFC tag, then starts the voice session
- `voice-chat.py`: Gemini real-time audio client, dictionary storage, printer integration
- `printer.py`: standalone thermal printer helper
- `prompt.txt`: default system prompt
- `prompts/`: per-profile prompts
- `familect.json`: generated dictionary file containing saved entries

## Component setup docs

Detailed hardware setup is split by component in [`doc/`](./doc/README.md):

- [Raspberry Pi 5 audio setup (SPH0645 + I2S amp)](./doc/audio-setup-pi5.md)
- [PN532 NFC/RFID v3 setup (I2C)](./doc/pn532-setup-pi5.md)
- [Button setup (GPIO17)](./doc/button-setup.md)
- [Thermal printer setup (UART /dev/serial0)](./doc/printer-setup.md)
- [Installed dependencies (APT + pip)](./doc/installeddeps.md)

## Requirements

- Raspberry Pi
- Python 3.10+
- Gemini API key
- PN532 NFC reader on I2C
- Push button on GPIO 17
- Audio input and output devices available as:
  - `mic_sv`
  - `spk_sv`
- Optional thermal printer on `/dev/serial0`

## Installation

1. Create a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

For Raspberry Pi 5 with PN532, if `lgpio` is installed via `apt`, use:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
```

2. Install Python dependencies.

```bash
pip install numpy sounddevice websockets gpiozero adafruit-circuitpython-pn532 pyserial
```

3. Optional: install acoustic echo cancellation support.

```bash
pip install speexdsp-ns
```

4. Export your Gemini API key.

```bash
export GEMINI_API_KEY="your_api_key"
```

5. If `sounddevice` fails to install or open devices on Raspberry Pi OS, install PortAudio system packages first.

```bash
sudo apt update
sudo apt install python3-dev portaudio19-dev
```

## Raspberry Pi base setup

Enable I2C for the PN532 reader:

```bash
sudo raspi-config
```

Then open:
- Interface Options
- I2C
- Enable

Enable UART for the thermal printer:

```bash
sudo raspi-config
```

Then open:
- Interface Options
- Serial Port
- Login shell over serial: No
- Serial port hardware enabled: Yes

## Configuration

### NFC profiles

Known NFC tags are declared in `main.py` in the `TAG_PROFILES` table.

Each tag can map to:
- a person name
- a prompt file

Tags can also contain a text payload like:
- `model:baptiste`
- `model:lea`

### Dictionary storage

Saved words are written to `familect.json`.
If the file does not exist, it is created automatically at startup.

## Steps to reproduce

### 1. Verify the button

```bash
python3 examples/button.py
```

Press and release the button.
You should see:
- Pressed
- Released

### 2. Verify the NFC reader

```bash
python3 examples/nfc-reader/nfc-test.py
```

Present a card or tag to the reader.
You should see its UID printed in the terminal.

### 3. Register a tag

Open `main.py` and add your NFC UID to `TAG_PROFILES`.

### 4. Start the full app

```bash
python3 main.py
```

### 5. Trigger a session

- make sure the button is not pressed
- present a registered NFC tag

### 6. Talk to the assistant

- the voice session starts
- if the model detects a new family word, it saves it to `familect.json`
- if a thermal printer is connected, the word is printed

### 7. Stop the session

You can stop the session in two ways:
- press the button
- remove the NFC tag

If the NFC tag is removed, the assistant attempts to say goodbye before the session exits.

## Running `voice-chat.py` directly

```bash
python3 voice-chat.py --prompt-file prompt.txt --person "Baptiste"
```

Notes:
- `GEMINI_API_KEY` must be set
- the ALSA devices `mic_sv` and `spk_sv` must exist
- this bypasses the button and NFC activation flow

## Troubleshooting

### GEMINI_API_KEY not set

Export the API key before running the app.

```bash
export GEMINI_API_KEY="your_api_key"
```

### Unknown NFC tag

Add the tag UID to `TAG_PROFILES` in `main.py`, or write a supported `model:profile` slug to the NFC tag.

### Prompt file missing

Make sure the profile points to an existing file in `prompts/` or to `prompt.txt`.

### Printer does not work

Check:
- UART is enabled
- the printer is connected to `/dev/serial0`
- `pyserial` is installed
- the printer baud rate matches 19200

### No audio

Check that the ALSA device names match:
- `mic_sv`
- `spk_sv`

For full audio diagnostics, see [audio setup doc](./doc/audio-setup-pi5.md).

## Notes

- The app currently targets a Raspberry Pi hardware setup.
- The full activation flow is controlled by `main.py`.
- The voice session logic, dictionary save flow, and printer integration are in `voice-chat.py`.
