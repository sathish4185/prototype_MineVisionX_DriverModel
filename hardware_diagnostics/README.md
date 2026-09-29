# Mine Vision-X | Hardware Diagnostics & Sensor Calibration Suite

A standalone testing and validation toolkit for all sensor hardware, I2C buses, serial controllers, and motor drivers in the Mine Vision-X vehicle perception stack.

---

## 🛠️ Diagnostic Scripts

| Script | Subsystem | Purpose & Usage |
| :--- | :--- | :--- |
| **`probe_sensors.py`** | I2C Arbiter | Scans the I2C bus (`/dev/i2c-1`), tests register handshakes with **u-blox NEO-M9N GNSS (0x42)** and **MMA7660 IMU (0x4c)**, and dumps sample register data. |
| **`read_gps.py`** | GNSS Satellite Receiver | Reads raw NMEA data streams (`$GNGGA`, `$GNRMC`, `$GNGSA`) over I2C register `0xFF` from the NEO-M9N receiver and displays latitude, longitude, and fix status. |
| **`test_imu_stability.py`** | 3-Axis IMU (MMA7660) | Samples 3-axis accelerometer readings at 20 Hz, applies Trimmed Median Filtering and Exponential Moving Average ($\alpha = 0.18$), and calculates signal-to-noise ratio. |
| **`probe_ultrasonic.py`** | Ultrasonic Ranging | Probes GrovePi digital ports (D2 through D8) with test pulses to automatically locate and calibrate connected ultrasonic distance sensors. |
| **`check_arduino.py`** | Powertrain Microcontroller | Establishes serial connection with Arduino UNO (`/dev/ttyUSB0` @ 9600 baud), verifies optical wheel encoder pulses, and prints live RPM. |
| **`monitor_arduino.py`** | Serial Telemetry Stream | Continuous real-time monitor displaying wheel encoder RPM and calculated linear velocity ($km/h$). |
| **`send_motor_cmd.py`** | Directional Motor Drive | Sends individual directional motor commands (`F` = Forward, `B` = Backward, `L` = Left, `R` = Right, `S` = Stop) directly to the Arduino motor shield. |
| **`test_commands.py`** | Motor Stress & Failsafe | Automated drive cycle testing execution: iterates through forward, reverse, steering pivots, and emergency braking stops to verify mechanical response. |

---

## 🚀 How to Run

Run any diagnostic script using Python:
```bash
# Probe I2C Sensors (NEO-M9N & MMA7660)
python hardware_diagnostics/probe_sensors.py

# Read GPS NMEA Stream
python hardware_diagnostics/read_gps.py

# Test IMU Filtering & Stability
python hardware_diagnostics/test_imu_stability.py

# Probe GrovePi Digital Ports for Ultrasonic Sensor
python hardware_diagnostics/probe_ultrasonic.py

# Verify Arduino Serial Connection
python hardware_diagnostics/check_arduino.py

# Test Motor Drive Commands
python hardware_diagnostics/send_motor_cmd.py
```
