# RC Multi Joystick PPM Trainer Port

## Description
A multi-joystick PPM generator for RC trainer ports, featuring hotplug support, trim, expo, inversion, and an inspector utility.

If you’ve ever wanted to fly your RC craft with real plane-style controllers or even an Xbox controller connected via USB

Now the sky is not the limit!

## Features

- **8-Channel PPM Generation**  
  Generate a PPM signal on GPIO 18 using the [pigpio](http://abyz.me.uk/rpi/pigpio/) library.

- **Multi-Joystick & Hotplug Support**  
  Dynamically detects multiple joysticks. If no joystick is present, no PPM signal is generated, so the RC transmitter reverts to its own controls.

- **Per-Channel Customization**  
  Configure channel mapping, trim, expo, and inversion (using a `!` prefix).

- **Status LEDs**  
  - **RED LED (GPIO 22):** Solid ON once the system is initialized.  
  - **GREEN LED (GPIO 23):** Blinks continuously while the main loop is running.

- **Inspector Utility**  
  A separate script (`joystick_inspector.py`) monitors all joystick events (axes, buttons, hats) and prints a live table of computed PPM pulse widths.

## Hardware Requirements

- **Raspberry Pi** (tested on Pi Zero 2)
- **RC Transmitter** with a trainer port that accepts a PPM signal
- **USB Joystick(s)**
- **LEDs (Optional)**  
  - RED LED (with resistor) on GPIO 22  
  - GREEN LED (with resistor) on GPIO 23
- **Wiring**  
  - **GPIO 18** → Transmitter trainer port signal  
  - **GND** → Transmitter ground

## Software Requirements

- **Raspberry Pi OS** (or similar Linux distro)
- **Python 3**
- [**pigpio**](http://abyz.me.uk/rpi/pigpio/) library & daemon (`pigpiod`)
- [**pygame**](https://www.pygame.org/)

## Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/yourusername/RC-Multi-Joystick-PPM-Trainer-Port.git
   cd RC-Multi-Joystick-PPM-Trainer-Port
   ```

2. **Install Dependencies**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install pigpio pygame
   ```

3. **Enable and Start pigpio Daemon**

   ```bash
   sudo systemctl enable pigpiod --now
   ```

   **If step 3 failed, please install using apt-get and try again**

   ```bash
   sudo apt-get install python3-pigpi
   sudo systemctl enable pigpiod --now
   ```

## Wiring Diagram

   ```markdown
## Wiring Diagram

- **PPM Output**  
  - **GPIO 18** → Transmitter trainer port signal
  - **GND** → Transmitter ground

- **Status LEDs (Optional)**  
  - **RED LED** → GPIO 22 (with resistor)
  - **GREEN LED** → GPIO 23 (with resistor)
   ```

```sql
    Raspberry Pi              3‑Pole (TRS) Connector (Headphones Cable)
  ------------------          -------------------------
  |                |          |         |           |
  |   GPIO 18      | -------->|   TIP   |  (PPM signal)
  |   (PPM out)    |          |         |           
  |                |          |         |           
  |   GND ---------| -------->| SLEEVE  |  (Ground)
  |                |          |         |
  ------------------          |  RING   |  (Not used)
                             -------------------------
```

## Configuration

Open `joystick_ppm_multi.py` and edit the top section:

- **CHANNEL_MAP**  
  Maps each channel (0–7) to a joystick control.  
  Example:
  ```python
  CHANNEL_MAP = {
      0: "joy0:axis:0",   # normal axis
      1: "!joy0:axis:1",  # inverted axis
      2: "joy0:axis:2",
      3: "joy1:axis:0",
      4: "none",
      5: "none",
      6: "none",
      7: "none",
  }
  ```

  A leading ! inverts the final value.
  If `VERBOSE = True`, a live table of channel pulse widths will be displayed.

- **TRIM & EXPO**
  Set per-channel trim (µs offset) and expo (0 = linear, 1 = full expo) in:
  ```python
  TRIM = [0, 0, 0, 0, 0, 0, 0, 0]
  EXPO = [0, 0, 0, 0, 0, 0, 0, 0]
  ```

- **PPM Parameters**
  Adjust `MIN_PULSE_US`, `MID_PULSE_US`, `MAX_PULSE_US`, and `FRAME_LENGTH_MS` as needed.


## Running the Scripts

### PPM Generator

```bash
python3 joystick_ppm_multi.py
```


### Joystick Inspector

```bash
python3 joystick_inspector.py
```
This script prints all joystick events and a table of computed channel outputs, useful for verifying your mapping before flight.


## Running as a Systemd Service

To have the PPM generator start automatically at boot:

1. **Create the Service File**  
   For example, `/etc/systemd/system/joystick_ppm.service`:
   ```ini
   [Unit]
   Description=Multi-Joystick PPM Generator Service
   After=pigpiod.service
   Requires=pigpiod.service

   [Service]
   Environment="TERM=linux" "XDG_RUNTIME_DIR=/run/user/1000"
   ExecStart=/home/pi/ppm/venv/bin/python3 /home/pi/ppm/joystick_ppm_multi.py
   WorkingDirectory=/home/pi/ppm/
   StandardOutput=journal
   StandardError=journal
   Restart=always
   KillSignal=SIGKILL
   SendSIGKILL=yes
   TimeoutStopSec=5
   User=pi
   Group=pi

   [Install]
   WantedBy=multi-user.target
   ```

2. **Create the Service File**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable joystick_ppm.service
   sudo systemctl start joystick_ppm.service
   ```

## Calibrating Your Joystick
### OS-Level Calibration:
```bash
sudo apt-get install joystick
jscal -c /dev/input/js0
```
Follow the prompts to calibrate the axes so that the center position is zero and the extremes are properly mapped.


## Author & Acknowledgements

- **Author:** Itay Sharoni 
- **Contact:** [[GitHub](https://github.com/Itay-Sharon)]

**Acknowledgements**  
- [pigpio](http://abyz.me.uk/rpi/pigpio/) library & daemon  
- [pygame](https://www.pygame.org/) library  
- [jsa/flystick](https://github.com/jsa/flystick) for the original concept & inspiration.


## License

This project is licensed under the [GPL-3.0 License](LICENSE).



