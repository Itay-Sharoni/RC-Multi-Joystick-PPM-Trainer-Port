#!/usr/bin/env python3
"""
joystick_inspector.py
---------------------
A utility that monitors all joystick events (axes, buttons, hats) and prints the event
details to the command line. Use this tool to learn the indices and values for your
joystick controls for mapping.

Press Ctrl+C to exit.

Author: Itay Sharoni
License: GPL-3.0
"""

import sys
import pygame
import time

def init_joysticks():
    """Initialize pygame and all connected joysticks."""
    pygame.init()
    pygame.joystick.init()
    joysticks = {}
    count = pygame.joystick.get_count()
    if count < 1:
        print("No joysticks found!")
        sys.exit(1)
    for i in range(count):
        js = pygame.joystick.Joystick(i)
        js.init()
        key = f"joy{i}"
        joysticks[key] = js
        print(f"Initialized {key}: {js.get_name()}")
    return joysticks

def main():
    joysticks = init_joysticks()
    print("\nMonitoring joystick events. Move an axis or press a button to see details.\n")
    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.JOYAXISMOTION:
                    js = joysticks[f"joy{event.joy}"]
                    print(f"[{js.get_name()}] Axis {event.axis} moved: {event.value:.3f}")
                elif event.type == pygame.JOYBUTTONDOWN:
                    js = joysticks[f"joy{event.joy}"]
                    print(f"[{js.get_name()}] Button {event.button} pressed")
                elif event.type == pygame.JOYBUTTONUP:
                    js = joysticks[f"joy{event.joy}"]
                    print(f"[{js.get_name()}] Button {event.button} released")
                elif event.type == pygame.JOYHATMOTION:
                    js = joysticks[f"joy{event.joy}"]
                    print(f"[{js.get_name()}] Hat {event.hat} moved: {event.value}")
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nExiting inspector...")
    finally:
        pygame.quit()

if __name__ == "__main__":
    main()
