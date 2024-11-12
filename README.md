# ESP32 Smart Locker

ESP32 Smart Locker is a project designed to manage and control RFID-based access for lockers. 
It uses an [OLIMEX ESP32 PoE microcontroller](https://www.olimex.com/Products/IoT/ESP32/ESP32-POE/) 
to read RFID tags, authenticate users, and control access through a web interface. 

## Project Overview

This project enables RFID tags to be used for access control to lockers or similar facilities (via a relay). 
An ESP32 serves as the central controller and web server, allowing you to:
- Unlocking of a an electronically powered lock via standard RFID tags
- Manage authorized RFID tags via a web interface (password protected access via Basic Authentication)

## Requirements

- **Hardware**
  - [OLIMEX ESP32 PoE microcontroller board](https://www.olimex.com/Products/IoT/ESP32/ESP32-POE/) 
  - RFID Reader (e.g. [RFID-RC522](https://www.amazon.de/dp/B07JLBGYQ6))
  - Relay module for control (e.g. [SRD-5VDC-SL-C](https://www.amazon.de/dp/B07XY2C5M5))
  - Power suppply

- **Software**
  - [MicroPython](https://micropython.org/download/esp32/) for [ESP32 OLIMEX](https://micropython.org/download/OLIMEX_ESP32_POE/) (I used version 1.24)
  - [`microdot`](https://microdot.readthedocs.io/en/latest/) as web framewor
  - `utemplate` for HTML templating (code includeded in microdot)
  - [`MicroPython_MFRC522`](https://github.com/vtt-info/MicroPython_MFRC522) for accessing the RFID reader
  
## Installation

1. **Flash ESP32**

Install [esptool](https://github.com/espressif/esptool) and flash MicroPython to the OLIMEX ESP32 POE board:
```bash
esptool.py --port /dev/ttyUSB0 erase_flash
esptool.py --chip esp32 --port /dev/ttyUSB0 --baud 460800 write_flash -z 0x1000 ~/Downloads/OLIMEX_ESP32_POE-20241025-v1.24.0.bin
```

2. **Upload Project Files**

Upload the Python scripts and the `templates` directory along with the necessary libs to the ESP32, e.g. via `rshell`:
```bash
rshell -p /dev/ttyUSB0 cp -r src/* /pyboard/
rshell -p /dev/ttyUSB0 cp -r libs/microdot/src/microdot /pyboard/
rshell -p /dev/ttyUSB0 cp -r libs/microdot/libs/common/utemplate /pyboard/
rshell -p /dev/ttyUSB0 cp libs/MicroPython_MFRC522/micropython_mfrc522/mfrc522.py /pyboard/
```

3. **Connect RFID and Relay**

Connect the RFID reader and relay module to the ESP32 board according to the pin configuration **TODO**.

4. **Set Username and Password**

Create a `credentials.txt` file on the ESP32 with the login credentials:
```plaintext
admin
my_secure_password
```

## Usage

- **Accessing the Web Interface**
  - Connect to the ESP32’s IP address in a browser to open the management interface.
  - Log in with your credentials to add or remove RFID tags.

- **Tag Management**
  - Register new tags and link them with user information
  - Delete tags as needed

## Code Overview

- **boot.py**: Starts the web server, provides RESTful HTTP methods and starts the RFID reader.
- **tools.py**: Provides helper functions for loading, adding, and removing authorized UIDs.
- **templates/**: Contains the HTML templates for the user interface.

## Security Considerations

- **Basic Authentication**: Access to the web interface is protected by simple Basic Auth, however access is done via HTTP only.
- **Keep Credentials Secure**: The `credentials.txt` file should not be used on publicly accessible systems without additional protections.
- Unly the **UID of RFID tags** is used, this might not be super secure.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Author
**Alexander Kläser**
