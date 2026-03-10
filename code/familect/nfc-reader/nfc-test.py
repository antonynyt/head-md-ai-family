import board
import busio
from adafruit_pn532.i2c import PN532_I2C

# Initialize I2C and PN532
i2c = busio.I2C(board.SCL, board.SDA)
pn532 = PN532_I2C(i2c, debug=False)

# Print firmware version to confirm communication
ic, ver, rev, support = pn532.firmware_version
print(f"Found PN532 - Firmware version: {ver}.{rev}")

# Configure to read MiFare cards
pn532.SAM_configuration()

print("Waiting for NFC card/tag... (Ctrl+C to exit)")
while True:
    uid = pn532.read_passive_target(timeout=0.5)
    if uid is not None:
        print(f"Card detected! UID: {[hex(i) for i in uid]}")