from gpiozero import Button
from signal import pause

button = Button(17, pull_up=True)

button.when_pressed = lambda: print("Pressed")
button.when_released = lambda: print("Released")

pause()