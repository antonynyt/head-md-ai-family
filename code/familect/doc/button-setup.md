# Raspberry Pi button setup

## Wiring

Use a GPIO pin and GND, not the RUN pins.

Recommended wiring:

`GPIO17 ---- Button ---- GND`

- GPIO17: physical pin 11
- GND: physical pin 6

## Internal pull-up resistor

The code uses `pull_up=True`, so no external resistor is required for the basic setup.

## Example

Install the GPIO library if needed:

```bash
sudo apt install python3-gpiozero
```

```python
from gpiozero import Button
from signal import pause

button = Button(17, pull_up=True)

button.when_pressed = lambda: print("Pressed")
button.when_released = lambda: print("Released")

pause()
```
