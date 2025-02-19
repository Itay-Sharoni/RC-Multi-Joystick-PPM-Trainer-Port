#!/usr/bin/env python3
"""
joystick_ppm_multi.py
---------------------
Reads inputs from multiple USB joysticks (via pygame) and outputs either:
  - An N-channel PPM signal on a dedicated GPIO (for RC trainer ports), or
  - A 16-channel SBUS signal on the same GPIO.
  
Features include per-channel trim, expo, and channel inversion (using a '!' prefix in the mapping).
Status LEDs:
  - RED LED (GPIO 22): Solid ON once the system is initialized.
  - GREEN LED (GPIO 23): Blinks continuously while the main loop runs.
  
A periodic table is printed (when VERBOSE is True) showing the computed pulse widths for each channel.
*Note:* This project is based on [jsa/flystick](https://github.com/jsa/flystick) – credit to the original author.

Dependencies:
  - pigpio (ensure pigpiod is running)
  - pygame (v2.0+ for hot-plug events)
  
License: GPL-3.0
"""

import sys
import time
import os
import pygame
import pigpio
import threading
import struct

# -----------------------------
# USER CONFIGURATION SECTION
# -----------------------------

VERBOSE = False  # If True, print a live table of computed channel outputs periodically

# Set output mode: "PPM" or "SBUS"
OUTPUT_MODE = "SBUS"  # Change to "PPM" for PPM output, or "SBUS" for SBUS output

# 1) COMMON PARAMETERS
PPM_GPIO_PIN    = 18            # GPIO pin for output
FRAME_LENGTH_MS = 20.0          # Total PPM frame length in milliseconds (only used in PPM mode)
MIN_PULSE_US    = 988           # Minimum pulse width (µs)
MID_PULSE_US    = 1500          # Mid (neutral) pulse width (µs)
MAX_PULSE_US    = 2012          # Maximum pulse width (µs)

# 2) CHANNEL MAPPINGS
# Define channels with keys starting at 1.
# Mapping syntax: "[!]joyX:<control>:<index>"
# A leading "!" inverts the final value.
CHANNEL_MAP = {
    1: "joy0:axis:0",
    2: "!joy0:axis:1",
    3: "joy0:axis:2",
    4: "joy0:axis:4",
    5: "none",
    6: "none",
    7: "none",
    8: "none"
    # In SBUS mode, you can add channels 9..16 as needed.
}

# 3) TRIM and EXPO SETTINGS (lists indexed starting at 0, where index 0 corresponds to channel 1)
TRIM = [0, 0, 0, 0, 0, 0, 0, 0]
EXPO = [0, 0, 0, 0, 0, 0, 0, 0]

# 4) LED GPIO PINS
RED_LED_GPIO   = 22   # RED LED: solid ON when system is initialized
GREEN_LED_GPIO = 23   # GREEN LED: blinks while main loop is active

# -----------------------------
# END USER CONFIGURATION
# -----------------------------

pi = None
running = True
joysticks = {}
last_table_print = 0.0

# Determine number of defined channels from CHANNEL_MAP.
if CHANNEL_MAP:
    num_defined_channels = max(CHANNEL_MAP.keys())
else:
    num_defined_channels = 0

# For SBUS mode, use 16 channels; for PPM mode, use num_defined_channels.
if OUTPUT_MODE == "SBUS":
    num_channels = 16
else:
    num_channels = num_defined_channels

def init_gpio():
    """Initialize pigpio and configure LED pins."""
    global pi
    pi = pigpio.pi()
    if not pi.connected:
        print("Error: pigpiod is not running!")
        sys.exit(1)
    pi.set_mode(RED_LED_GPIO, pigpio.OUTPUT)
    pi.set_mode(GREEN_LED_GPIO, pigpio.OUTPUT)
    pi.write(RED_LED_GPIO, 0)
    pi.write(GREEN_LED_GPIO, 0)

def init_joysticks():
    """Initialize pygame and all connected joysticks."""
    pygame.joystick.init()
    count = pygame.joystick.get_count()
    if count > 0:
        for i in range(count):
            js = pygame.joystick.Joystick(i)
            js.init()
            key = f"joy{i}"
            joysticks[key] = js
            print(f"Initialized {key}: {js.get_name()}")

def clear_joysticks():
    """Clear the joystick dictionary."""
    global joysticks
    joysticks.clear()

def apply_expo(value, expo_factor):
    """Apply exponential (expo) curve to a normalized value [-1, 1]."""
    if expo_factor <= 0:
        return value
    return (1 - expo_factor) * value + expo_factor * (value ** 3)

def axis_to_us(axis_value, ch_index):
    """
    Convert an axis value [-1, 1] to a pulse width in microseconds,
    applying expo and trim for channel (ch_index is 1-indexed).
    """
    adjusted = apply_expo(axis_value, EXPO[ch_index-1])
    pulse = (adjusted + 1) * 0.5 * (MAX_PULSE_US - MIN_PULSE_US) + MIN_PULSE_US
    pulse += TRIM[ch_index-1]
    return int(max(MIN_PULSE_US, min(MAX_PULSE_US, pulse)))

def read_channel(ch_key):
    """
    Read the control value for a channel given its key (as defined in CHANNEL_MAP, 1-indexed).
    Returns the pulse width in µs.
    If the mapping starts with '!', invert the final normalized value.
    For keys not defined, return MID_PULSE_US.
    """
    mapping = CHANNEL_MAP.get(ch_key, "none")
    if mapping == "none":
        return MID_PULSE_US
    invert = False
    if mapping.startswith("!"):
        invert = True
        mapping = mapping[1:]
    parts = mapping.split(":")
    if len(parts) < 2:
        return MID_PULSE_US
    joy_key = parts[0]
    if joy_key not in joysticks:
        return MID_PULSE_US
    js = joysticks[joy_key]
    control_type = parts[1]
    if control_type == "axis":
        axis_idx = int(parts[2])
        val = js.get_axis(axis_idx)
    elif control_type == "button":
        btn_idx = int(parts[2])
        val = js.get_button(btn_idx)
        val = (val * 2) - 1
    elif control_type == "hat":
        hat_idx = int(parts[2])
        subaxis = int(parts[3])
        hx, hy = js.get_hat(hat_idx)
        val = hx if subaxis == 0 else hy
    else:
        val = 0
    if invert:
        val = -val
    return axis_to_us(val, ch_key)

def build_ppm_frame(channels_us):
    """
    Build a pigpio waveform for a single PPM frame from the provided channel pulse widths.
    Only used in PPM mode.
    """
    gap_us = 300  # Fixed gap between channels
    total_time = sum(channels_us) + gap_us * len(channels_us)
    sync_time_us = int(FRAME_LENGTH_MS * 1000 - total_time)
    pulses = []
    for ch in channels_us:
        high_time = max(ch - gap_us, 100)
        pulses.append(pigpio.pulse(1 << PPM_GPIO_PIN, 0, high_time))
        pulses.append(pigpio.pulse(0, 1 << PPM_GPIO_PIN, gap_us))
    pulses.append(pigpio.pulse(0, 1 << PPM_GPIO_PIN, max(sync_time_us, 8000)))
    pi.wave_clear()
    pi.wave_add_generic(pulses)
    return pi.wave_create()

def map_to_sbus(pulse):
    """Map a pulse width (µs) to an SBUS value in the range 172 to 1811."""
    sbus_min = 172
    sbus_max = 1811
    sbus_val = sbus_min + (pulse - MIN_PULSE_US) * (sbus_max - sbus_min) / (MAX_PULSE_US - MIN_PULSE_US)
    return int(round(max(sbus_min, min(sbus_max, sbus_val))))

def build_sbus_frame(channels_us):
    """
    Build an SBUS frame (25 bytes) from the provided channel pulse widths.
    Expects channels_us to be a list of num_channels values.
    This routine uses pigpio's wave_add_serial to generate a standard, uninverted SBUS signal.
    """
    sbus_channels = [map_to_sbus(p) for p in channels_us]
    bitstream = 0
    bits = 0
    data_bytes = []
    for ch in sbus_channels:
        bitstream |= (ch & 0x07FF) << bits
        bits += 11
        while bits >= 8:
            data_bytes.append(bitstream & 0xFF)
            bitstream >>= 8
            bits -= 8
    while len(data_bytes) < 22:
        data_bytes.append(0)
    frame = bytearray(25)
    frame[0] = 0x0F
    for i in range(22):
        frame[i+1] = data_bytes[i]
    frame[23] = 0  # Flags (set to 0)
    frame[24] = 0x00
    pi.wave_clear()
    # Generate serial waveform at 100,000 baud using pigpio.
    pi.wave_add_serial(PPM_GPIO_PIN, 100000, bytes(frame))
    wid = pi.wave_create()
    if wid < 0:
        print("Error: wave_create returned invalid wave id")
    return wid

def print_table(joystick_count, num_defined_channels):
    """
    Clear the screen and print a table showing computed channel outputs for channels
    defined in CHANNEL_MAP (keys 1..num_defined_channels).
    """
    os.system('clear')
    print("Channel Outputs (µs):")
    print("------------------------------------------")
    print(f"{'Ch':<4}{'Mapping':<25}{'Pulse (µs)':>10}")
    print("------------------------------------------")
    for ch in range(1, num_defined_channels+1):
        mapping = CHANNEL_MAP.get(ch, "none")
        pulse = read_channel(ch)
        print(f"{ch:<4}{mapping:<25}{pulse:>10}")
    print("------------------------------------------")
    if joystick_count == 0:
        print("No joystick detected, so no output is sent.\n")
    else:
        print("Joystick(s) detected. (Press Ctrl+C to exit)\n")

def green_led_blink():
    """Blink the green LED continuously while running."""
    state = 0
    while running:
        state = 1 - state
        pi.write(GREEN_LED_GPIO, state)
        time.sleep(0.5)
    pi.write(GREEN_LED_GPIO, 0)

def main():
    global running, last_table_print
    init_gpio()
    pygame.init()
    pygame.joystick.init()
    init_joysticks()
    if OUTPUT_MODE == "SBUS":
        num_out_channels = 16
    else:
        num_out_channels = num_defined_channels

    pi.write(RED_LED_GPIO, 1)
    blink_thread = threading.Thread(target=green_led_blink, daemon=True)
    blink_thread.start()
    pi.set_mode(PPM_GPIO_PIN, pigpio.OUTPUT)
    print("Output generation logic started. Press Ctrl+C to exit.")
    last_table_print = time.time()

    try:
        while True:
            pygame.event.pump()
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEADDED:
                    print("Joystick added.")
                    init_joysticks()
                elif event.type == pygame.JOYDEVICEREMOVED:
                    print("Joystick removed.")
                    pygame.joystick.quit()
                    pygame.joystick.init()
                    clear_joysticks()
                    init_joysticks()
            joystick_count = pygame.joystick.get_count()
            if joystick_count == 0:
                if VERBOSE and (time.time() - last_table_print >= 0.5):
                    last_table_print = time.time()
                    print_table(joystick_count, num_defined_channels)
                time.sleep(0.1)
                continue

            # Build output channels list: use defined channels 1..num_defined_channels.
            channels = [read_channel(ch) for ch in range(1, num_defined_channels+1)]
            # In both modes, output channels are taken directly from CHANNEL_MAP (no dummy channel).
            if OUTPUT_MODE == "SBUS":
                wid = build_sbus_frame(channels)
            else:
                wid = build_ppm_frame(channels)
            if wid < 0:
                print("Error: Invalid wave id. Skipping this cycle.")
            else:
                pi.wave_send_once(wid)
                while pi.wave_tx_busy():
                    time.sleep(0.001)
                pi.wave_delete(wid)
            if VERBOSE and (time.time() - last_table_print >= 0.5):
                last_table_print = time.time()
                print_table(joystick_count, num_defined_channels)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        running = False
        blink_thread.join()
        pi.write(RED_LED_GPIO, 0)
        pi.write(GREEN_LED_GPIO, 0)
        pi.wave_clear()
        pi.stop()
        pygame.quit()

if __name__ == "__main__":
    main()
