# Thermal printer setup

## Hardware

- Interface: Raspberry Pi UART (`/dev/serial0`)
- Baud rate used by this project: `19200`
- Typical printer type: ESC/POS thermal printer

## Wiring

Use Raspberry Pi UART pins:

- GPIO14 TX (physical pin 8)
- GPIO15 RX (physical pin 10)

Typical wiring:
- Pi TX -> printer RX
- Pi RX -> printer TX (if needed by your printer)
- Connect power and ground according to your printer model

## Raspberry Pi UART config

Enable UART:

```bash
sudo raspi-config
```

Then open:
- Interface Options
- Serial Port
- Login shell over serial: No
- Serial port hardware enabled: Yes

## Python dependency

```bash
pip install pyserial
```

## Project config

`printer.py` and `voice-chat.py` use:

- Port: `/dev/serial0`
- Baud: `19200`

If needed, adjust these constants in the code:

- `PRINTER_PORT`
- `PRINTER_BAUD`

## Quick checks

Check the serial device exists:

```bash
ls -l /dev/serial0
```

Check user permissions for serial access:

```bash
groups
```

If required, add your user to `dialout` and reconnect your session:

```bash
sudo usermod -aG dialout $USER
```

## Troubleshooting

If printing does not work, verify:
- UART is enabled in `raspi-config`
- Printer is wired to the correct UART pins
- Device path is correct (`/dev/serial0`)
- `pyserial` is installed in the active environment
- Baud rate matches your printer (default here is `19200`)
