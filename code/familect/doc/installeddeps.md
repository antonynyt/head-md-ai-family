# Installed dependencies (Raspberry Pi)

This page lists packages to install for this project on Raspberry Pi.

## 1) APT packages

```bash
sudo apt update
sudo apt install -y \
	python3-venv \
	python3-dev \
	portaudio19-dev \
	python3-lgpio \
	i2c-tools \
	python3-gpiozero
```

Notes:
- `python3-lgpio` is recommended via `apt` on Raspberry Pi 5.
- `python3-dev` + `portaudio19-dev` are required when `sounddevice` needs local build support.
- `i2c-tools` is useful for PN532 checks (`i2cdetect -y 1`).

## 2) Python virtual environment

For Pi 5 + PN532 (`lgpio` installed from apt), create the venv with system site packages:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 3) pip packages (required)

```bash
pip install \
	numpy \
	sounddevice \
	websockets \
	gpiozero \
	adafruit-circuitpython-pn532 \
	pyserial
```

## 4) pip packages (optional)

Acoustic echo cancellation:

```bash
pip install speexdsp-ns
```

## 5) Quick verification commands

```bash
python3 -c "import sounddevice, websockets, numpy; print('audio/websocket deps ok')"
python3 -c "import gpiozero; print('gpiozero ok')"
python3 -c "import board, busio; from adafruit_pn532.i2c import PN532_I2C; print('pn532 deps ok')"
python3 -c "import serial; print('pyserial ok')"
```

## 6) Freeze installed Python deps

```bash
pip freeze > requirements.lock.txt
```

