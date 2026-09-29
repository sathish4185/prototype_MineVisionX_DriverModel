# Mine Vision-X | In-Cabin Vehicle ADAS & Edge Telematics Node

The **Vehicle Edge Node** runs directly on the on-board edge computer inside Heavy Earth Moving Machinery (HEMM) (e.g. Raspberry Pi 4B or NVIDIA Jetson Orin Nano).

---

## 📌 Features

1. **Optical CSI / FPV Camera Pipeline & Tactical Night Vision**:
   - Captures high-definition frames (OV5647 CSI sensor / Picamera2 pipeline @ 640x480, ~28 FPS).
   - **Tactical Night Vision & 3W 850nm IR Illuminator ISP**:
     - Real-time ambient lux and scene darkness detection ($0\text{--}100\%$).
     - Automatic low-light trigger with seamless daylight fallback.
     - Multi-palette rendering: **PVS-14 Green Phosphor**, **High-Contrast IR Monochrome**, and **FLIR Thermal Ironbow False-Color Heatmap**.
     - Dynamic Digital Exposure Gain ($1.0\times\text{--}3.0\times$), contrast equalization, and tactical HUD rangefinder reticle overlay.
     - Live MJPEG video stream served at `/video_feed` with `/api/camera/night_vision` REST API.
2. **Sub-Meter Proximity Detection (GrovePi Port D2)**:
   - High-speed ultrasonic distance reading smoothed via Exponential Moving Average ($\alpha = 0.35$).
   - Dynamic 3-tier safety alert thresholds: Clear ($>45\text{ cm}$), Caution ($18\text{--}45\text{ cm}$), and Obstacle Imminent ($<18\text{ cm}$).
3. **3D Attitude & Rollover Protection (MMA7660FC I2C @ 0x4c)**:
   - Reads 3-axis accelerometer registers via I2C bus arbiter.
   - Dual-stage digital filtering: Trimmed Median Filter + Exponential Moving Average ($\alpha = 0.18$).
   - Renders interactive Three.js 3D Haul Truck model on the driver's display.
4. **u-blox NEO-M9N High-Precision GNSS (I2C-1 @ 0x42)**:
   - Concurrent multi-constellation satellite positioning (GPS, GLONASS, Galileo, BeiDou).
   - Real-time NMEA sentence parsing (`$GNGGA`, `$GNRMC`, `$GNGSA`) with HDOP satellite dilution calculation.
5. **Powertrain & Optical Wheel Encoder (Arduino UNO @ /dev/ttyUSB0)**:
   - Serial communication at 9600 baud.
   - Decodes wheel RPM, calculates true linear velocity ($km/h$), and executes failsafe directional drive commands (`F`, `B`, `L`, `R`, `S`).
6. **Telemetry Transmutation to Central Control Room**:
   - `vehicle_transmuter_client.py`: Continuously packages vehicle sensor streams and transmits them over LoRa Mesh (868/915 MHz) or 4G APN to the Central Office Security Surveillance Room.

---

## 🚀 How to Run

### Windows / Local Simulation
Double-click `launch_vehicle_hud.bat` or run:
```bash
python app.py
```
Open your browser to: **http://127.0.0.1:5000**

### Raspberry Pi 4 / Linux On-Board Deployment
1. Enable I2C and Camera in `raspi-config`:
   ```bash
   sudo raspi-config
   ```
2. Run manually:
   ```bash
   python3 app.py
   ```
3. Auto-start as a systemd service:
   ```bash
   sudo cp grovepi-telemetry.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable grovepi-telemetry.service
   sudo systemctl start grovepi-telemetry.service
   ```

### Transmuting Telemetry to Central Control Room
To transmute vehicle data to the central office:
```bash
python vehicle_transmuter_client.py --id HEMM-101 --local http://127.0.0.1:5000/api/telemetry --central http://<central_ip>:8080/api/telemetry/ingest
```
