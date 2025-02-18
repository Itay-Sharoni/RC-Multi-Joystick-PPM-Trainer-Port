#!/usr/bin/env python3
"""
joystick_ppm_multi.py
---------------------
Reads inputs from multiple USB joysticks (via pygame) and outputs an 8-channel PPM
signal using pigpio. Supports per‑channel trim and expo with mapping syntax that allows
you to choose which joystick control drives each channel.

Status LEDs:
  - RED LED (GPIO 22): Turns ON solid when the system is initialized.
  - GREEN LED (GPIO 23): Blinks continuously while the main loop is active.

A periodic table is printed (when VERBOSE is True) that shows the computed pulse widths
for each channel. Use this to verify your settings before connecting to your RC transmitter.

NEW CHANGES:
  1. If at least one joystick is detected, do NOT print "Waiting for joystick connection...".
  2. If all joysticks are unplugged, PPM output stops immediately, giving RC transmitter control back.
  3. If a channel mapping begins with '!', the final value is inverted (multiplied by -1).

Dependencies:
  - pigpio (ensure pigpiod is running)
  - pygame (v2.0+ for hot-plug events)

Author: Your Name
License: GPL-3.0
"""

import sys
import time
import os
import pygame
import pigpio
import threading

# -----------------------------
# USER CONFIGURATION SECTION
# -----------------------------

VERBOSE = True  # If True, print the table of computed channel outputs periodically

# 1) PPM OUTPUT CONFIGURATION
PPM_GPIO_PIN    = 18            # GPIO pin for PPM output
FRAME_LENGTH_MS = 20.0          # Total PPM frame length in milliseconds (should be ok as is)
MIN_PULSE_US    = 988          # Minimum pulse width (µs)
MID_PULSE_US    = 1500          # Mid (neutral) pulse width (µs)
MAX_PULSE_US    = 2012          # Maximum pulse width (µs)

# 2) CHANNEL MAPPINGS (8 channels)
# Mapping syntax:
#   "[!]joyX:<control>:<index>"
# The optional '!' prefix inverts (multiplies by -1) the final value.
# Valid control types: "axis", "button", or "hat"
# For hats: "joyX:hat:<hat_index>:<0=horizontal,1=vertical>"
# Use "none" if a channel is not used.
CHANNEL_MAP = {
    1: "joy0:axis:0",
    2: "joy0:axis:1",
    3: "joy0:axis:2",
    4: "joy0:axis:4",
    5: "none",
    6: "none",
    7: "none",
    8: "none"
}

# 3) TRIM and EXPO SETTINGS (one value per channel, 0-7)
TRIM = [0, 0, 0, 0, 0, 0, 0, 0]
EXPO = [0, 0, 0, 0, 0, 0, 0, 0]

# 4) LED GPIO PINS
RED_LED_GPIO   = 22   # Red LED: solid ON when system is initialized
GREEN_LED_GPIO = 23   # Green LED: blinks while main loop is active

# -----------------------------
# END USER CONFIGURATION
# -----------------------------

pi = None
running = True
joysticks = {}
last_table_print = 0.0

def init_gpio():
    """Initialize pigpio and configure LED pins."""
    global pi
    pi = pigpio.pi()
    if not pi.connected:
        print("Error: pigpio daemon not running!")
        sys.exit(1)
    pi.set_mode(RED_LED_GPIO, pigpio.OUTPUT)
    pi.set_mode(GREEN_LED_GPIO, pigpio.OUTPUT)
    pi.write(RED_LED_GPIO, 0)
    pi.write(GREEN_LED_GPIO, 0)

def init_joysticks():
    """Initialize pygame and all connected joysticks."""
    pygame.init()
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
    """Clear the joystick dictionary and stop PPM output."""
    global joysticks
    joysticks.clear()

def apply_expo(value, expo_factor):
    """Apply exponential (expo) curve to a normalized value [-1, 1]."""
    if expo_factor <= 0:
        return value
    return (1 - expo_factor) * value + expo_factor * (value ** 3)

def axis_to_us(axis_value, ch_index):
    """
    Convert an axis value [-1..1] to a pulse width in microseconds,
    applying expo and trim for that channel.
    """
    adjusted = apply_expo(axis_value, EXPO[ch_index])
    pulse = (adjusted + 1) * 0.5 * (MAX_PULSE_US - MIN_PULSE_US) + MIN_PULSE_US
    pulse += TRIM[ch_index]
    return int(max(MIN_PULSE_US, min(MAX_PULSE_US, pulse)))

def read_channel(ch_index):
    """
    Read the control value for a channel based on CHANNEL_MAP.
    Returns the pulse width in µs.
    If the mapping starts with '!', invert the final normalized value.
    """
    mapping = CHANNEL_MAP.get(ch_index, "none")
    if mapping == "none":
        return MID_PULSE_US

    # Check for inversion prefix
    invert = False
    if mapping.startswith("!"):
        invert = True
        mapping = mapping[1:]  # Remove '!' prefix

    parts = mapping.split(":")
    if len(parts) < 2:
        return MID_PULSE_US  # fallback

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
        # unpressed = -1, pressed = +1
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

    return axis_to_us(val, ch_index)

def build_ppm_frame(channels_us):
    """
    Build a pigpio waveform for a single PPM frame from channel pulse widths.
    """
    total_channel_time = sum(channels_us)
    sync_time_us = int(FRAME_LENGTH_MS * 1000 - total_channel_time)
    pulses = []
    gap_us = 300  # gap between channels

    for ch_us in channels_us:
        high_time = max(ch_us - gap_us, 100)
        pulses.append(pigpio.pulse(1 << PPM_GPIO_PIN, 0, high_time))
        pulses.append(pigpio.pulse(0, 1 << PPM_GPIO_PIN, gap_us))

    leftover = sync_time_us - (len(channels_us) * gap_us)
    leftover = max(leftover, 8000)
    pulses.append(pigpio.pulse(0, 1 << PPM_GPIO_PIN, leftover))
    pi.wave_clear()
    pi.wave_add_generic(pulses)
    return pi.wave_create()

def print_table(joystick_count):
    """
    Clear the screen and print a table showing computed PPM channel outputs.
    """
    os.system('clear')
    print("PPM Channels Output (µs):")
    print("------------------------------------------")
    print(f"{'Ch':<4}{'Mapping':<25}{'Pulse (µs)':>10}")
    print("------------------------------------------")
    for ch in range(8):
        mapping = CHANNEL_MAP.get(ch, "none")
        pulse = read_channel(ch)
        print(f"{ch:<4}{mapping:<25}{pulse:>10}")
    print("------------------------------------------")
    if joystick_count == 0:
        print("No joystick detected, so no PPM output is sent.\n")
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

    # Turn RED LED on to show system is up
    pi.write(RED_LED_GPIO, 1)

    # Start blinking GREEN LED in a background thread
    blink_thread = threading.Thread(target=green_led_blink, daemon=True)
    blink_thread.start()

    # Setup PPM output pin
    pi.set_mode(PPM_GPIO_PIN, pigpio.OUTPUT)

    print("PPM generation logic started. Press Ctrl+C to exit.")
    last_table_print = time.time()

    try:
        while True:
            pygame.event.pump()

            # Handle hotplug/unplug events
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

            count = pygame.joystick.get_count()
            # If no joystick is connected, do not send PPM (transmitter regains control)
            if count == 0:
                if VERBOSE and (time.time() - last_table_print >= 0.5):
                    last_table_print = time.time()
                    print_table(count)
                time.sleep(0.1)
                continue

            channels = [read_channel(ch) for ch in range(8)]
            wid = build_ppm_frame(channels)
            pi.wave_send_once(wid)
            while pi.wave_tx_busy():
                time.sleep(0.001)
            pi.wave_delete(wid)

            if VERBOSE and (time.time() - last_table_print >= 0.5):
                last_table_print = time.time()
                print_table(count)

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
