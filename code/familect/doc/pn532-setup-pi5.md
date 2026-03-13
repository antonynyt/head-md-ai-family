# PN532 NFC/RFID module v3 on Raspberry Pi 5

## Hardware

- Interface: I2C (DIP switches: SEL0=OFF, SEL1=ON)
- Detected at: `0x24` (`i2cdetect -y 1`)

## Wiring

| PN532 pin | Raspberry Pi 5 pin |
| --- | --- |
| VCC | 3.3V (Pin 1) |
| GND | GND (Pin 6) |
| SDA | GPIO2 / SDA (Pin 3) |
| SCL | GPIO3 / SCL (Pin 5) |

## Working installation steps

```bash
# 1. Install lgpio via apt (avoids common build issues)
sudo apt install python3-lgpio -y

# 2. Recreate venv with access to system site packages
deactivate
python3 -m venv --system-site-packages .venv
source .venv/bin/activate

# 3. Install Adafruit PN532 library
pip install adafruit-circuitpython-pn532

# 4. Run test script
python3 test-nfc.py
```

Pi 5 note: `lgpio` is more reliable via `apt` than `pip`.

## Troubleshooting

- `i2cdetect -y 1` should show `0x24`.
- Confirm SDA/SCL wiring on GPIO 2 and GPIO 3.
- Confirm power wiring (3.3V and GND).
- Confirm PN532 mode is I2C (not SPI/UART).
- Enable I2C: `sudo raspi-config` -> Interface Options -> I2C -> Enable.

## Test script (`test-nfc.py`)

```python
import board
import busio
from adafruit_pn532.i2c import PN532_I2C

i2c = busio.I2C(board.SCL, board.SDA)
pn532 = PN532_I2C(i2c, debug=False)

ic, ver, rev, support = pn532.firmware_version
print(f"Found PN532 - Firmware version: {ver}.{rev}")

pn532.SAM_configuration()

print("Waiting for NFC card/tag... (Ctrl+C to exit)")
while True:
    uid = pn532.read_passive_target(timeout=0.5)
    if uid is not None:
        print(f"Card detected! UID: {[hex(i) for i in uid]}")
```
