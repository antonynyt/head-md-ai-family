# Raspberry Pi 5 audio setup

## SPH0645 microphone + I2S DAC speaker

## Hardware

| Component | Role |
| --- | --- |
| Raspberry Pi 5 | Main board |
| SPH0645 | I2S MEMS microphone |
| Pimoroni Audio Amp SHIM | Speaker amp |
| Visaton K50 (8 ohm) | Speaker output |

## GPIO wiring

### SPH0645 microphone

| SPH0645 pin | Pi 5 physical pin | GPIO |
| --- | --- | --- |
| 3V | Pin 1 | 3.3V |
| GND | Pin 6 | GND |
| BCLK | Pin 12 | GPIO 18 |
| DOUT | Pin 38 | GPIO 20 |
| LRCLK | Pin 35 | GPIO 19 |
| SEL | GND | Left channel |

Speaker: connect speaker +/- to the Audio Amp SHIM speaker output.

## /boot/firmware/config.txt

```ini
dtparam=i2s=on
dtoverlay=hifiberry-dac
dtoverlay=googlevoicehat-soundcard
dtparam=audio=on
dtoverlay=vc4-kms-v3d,noaudio
dtoverlay=dwc2,dr_mode=host
```

## /etc/asound.conf

```ini
pcm.spk_hw {
    type hw
    card 0
    device 0
}

pcm.spk_sv {
    type softvol
    slave.pcm "spk_hw"
    control {
        name "Speaker Volume"
        card 0
    }
    min_dB -40.0
    max_dB 0.0
    resolution 256
}

pcm.mic_hw {
    type hw
    card 0
    device 0
    channels 2
    format S32_LE
    rate 48000
}

pcm.mic_sv {
    type softvol
    slave.pcm "mic_hw"
    control {
        name "Mic Capture Volume"
        card 0
    }
    min_dB -3.0
    max_dB 20.0
    resolution 256
}

pcm.!default {
    type asym
    playback.pcm "spk_sv"
    capture.pcm "mic_sv"
}
```

## Hardware format

| Device | Format | Rate | Channels |
| --- | --- | --- | --- |
| Speaker (card 0) | S32_LE | 48000 Hz | 2 |
| Mic (card 0) | S32_LE | 48000 Hz | 2 |

## Python device names

```python
MIC_DEVICE  = "mic_sv"
SPK_DEVICE  = "spk_sv"
SAMPLE_RATE = 48000
HW_CHANNELS = 2
HW_DTYPE    = "int32"
```

## Diagnostic commands

```bash
aplay -l
arecord -l
aplay -D hw:0,0 --dump-hw-params /dev/zero 2>&1 | grep FORMAT
pinctrl get 18 19 20 21
speaker-test -D hw:0,0 -t sine -f 1000 -c 2
speaker-test -D spk_hw -t sine -f 1000 -c 2
speaker-test -D spk_sv -t sine -f 1000 -c 2
arecord -D mic_sv -r 48000 -f S32_LE -c 2 -d 5 test.wav
aplay test.wav
python3 -c "import sounddevice as sd; print(sd.query_devices())"
amixer -D hw:0 sset 'Mic' 10dB
```

## Known issues and notes

### Card number instability

Card numbers can swap after reboot. Verify with `aplay -l` and `arecord -l`.

To make card ordering deterministic, create `/etc/modprobe.d/alsa.conf`:

```conf
options snd_rpi_googlevoicehat_soundcard index=0
```

### PortAudio / sounddevice initialization error

If you see `PortAudioError: Error initializing PortAudio`, check for stale card references in `/etc/asound.conf`:

```bash
sudo mv /etc/asound.conf /etc/asound.conf.bak
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```
