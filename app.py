import time
import math
import threading
from flask import Flask, jsonify, request, render_template_string
import smbus
import serial

app = Flask(__name__)

telemetry = {
    "imu": {
        "connected": False,
        "raw_x": 0,
        "raw_y": 0,
        "raw_z": 0,
        "ax": 0.0,
        "ay": 0.0,
        "az": 0.0,
        "pitch": 0.0,
        "roll": 0.0,
        "tilt_raw": 0,
        "error": None
    },
    "gps": {
        "connected": False,
        "fix": False,
        "fix_quality": "Searching...",
        "satellites": 0,
        "latitude": None,
        "longitude": None,
        "altitude_m": None,
        "speed_kmh": 0.0,
        "utc_time": None,
        "hdop": 99.99,
        "raw_sentences": [],
        "error": None
    },
    "arduino": {
        "connected": False,
        "port": "/dev/ttyUSB0",
        "rpm": 0.0,
        "speed_kmh": 0.0,
        "last_cmd": "S",
        "last_line": "",
        "ble_device": "HC-05 (00:25:00:00:D6:05)",
        "error": None
    }
}

i2c_lock = threading.Lock()
bus = None

arduino_lock = threading.Lock()
arduino_ser = None

def init_bus():
    global bus
    try:
        bus = smbus.SMBus(1)
        return True
    except Exception as e:
        print(f"Error initializing I2C bus: {e}")
        return False

# ================= ARDUINO SERIAL & MOTOR WORKER =================
def arduino_worker():
    global arduino_ser
    port = "/dev/ttyUSB0"
    baud = 9600

    while True:
        try:
            with arduino_lock:
                if arduino_ser is None or not arduino_ser.is_open:
                    arduino_ser = serial.Serial(port, baud, timeout=0.5)
                    telemetry["arduino"]["connected"] = True
                    telemetry["arduino"]["error"] = None
            
            line = ""
            with arduino_lock:
                if arduino_ser and arduino_ser.in_waiting > 0:
                    line = arduino_ser.readline().decode('utf-8', errors='replace').strip()

            if line:
                telemetry["arduino"]["last_line"] = line
                if "RPM:" in line:
                    try:
                        val_str = line.split("RPM:")[1].strip()
                        rpm = float(val_str)
                        telemetry["arduino"]["rpm"] = rpm
                        # 65mm diameter wheel -> ~0.204m circumference
                        # speed (m/s) = rpm * 0.204 / 60 -> * 3.6 for km/h = rpm * 0.01224
                        telemetry["arduino"]["speed_kmh"] = round(rpm * 0.01224, 2)
                        telemetry["arduino"]["connected"] = True
                    except:
                        pass
            time.sleep(0.01)

        except Exception as e:
            telemetry["arduino"]["connected"] = False
            telemetry["arduino"]["error"] = str(e)
            with arduino_lock:
                if arduino_ser:
                    try:
                        arduino_ser.close()
                    except:
                        pass
                arduino_ser = None
            time.sleep(2.0)

def send_motor_command(cmd):
    global arduino_ser
    with arduino_lock:
        if arduino_ser and arduino_ser.is_open:
            try:
                arduino_ser.write(cmd.encode('utf-8'))
                telemetry["arduino"]["last_cmd"] = cmd
                return True
            except Exception as e:
                telemetry["arduino"]["error"] = str(e)
                return False
    return False

# ================= IMU WORKER (MMA7660 at 0x4c) =================
def imu_worker():
    MMA7660_ADDR = 0x4c
    with i2c_lock:
        try:
            if bus:
                # Enter standby to configure sample rate
                bus.write_byte_data(MMA7660_ADDR, 0x07, 0x00)
                # Register 0x08: (3 << 5) = 4-sample debounce filter | 0x02 = 32 samples/sec
                bus.write_byte_data(MMA7660_ADDR, 0x08, (3 << 5) | 0x02)
                # Re-enter active mode
                bus.write_byte_data(MMA7660_ADDR, 0x07, 0x01)
                telemetry["imu"]["connected"] = True
        except Exception as e:
            telemetry["imu"]["error"] = str(e)

    def parse_6bit(val):
        if val & 0x40:  # Alert bit: invalid/updating reading
            return None
        v = val & 0x3F
        if v & 0x20:
            v -= 0x40
        return v

    # Filter state
    smooth_ax = 0.0
    smooth_ay = 0.0
    smooth_az = 1.0
    smooth_pitch = 0.0
    smooth_roll = 0.0
    raw_history = []
    initialized = False

    while True:
        try:
            with i2c_lock:
                if bus:
                    rx = bus.read_byte_data(MMA7660_ADDR, 0x00)
                    ry = bus.read_byte_data(MMA7660_ADDR, 0x01)
                    rz = bus.read_byte_data(MMA7660_ADDR, 0x02)
                    tilt = bus.read_byte_data(MMA7660_ADDR, 0x03)
            
            sx = parse_6bit(rx)
            sy = parse_6bit(ry)
            sz = parse_6bit(rz)

            if sx is not None and sy is not None and sz is not None:
                # 1. Maintain sliding window of 5 samples for outlier rejection
                raw_history.append((sx, sy, sz))
                if len(raw_history) > 5:
                    raw_history.pop(0)

                # Trimmed mean: sorted medians for each axis
                xs = sorted([s[0] for s in raw_history])
                ys = sorted([s[1] for s in raw_history])
                zs = sorted([s[2] for s in raw_history])
                med_x = xs[len(xs) // 2]
                med_y = ys[len(ys) // 2]
                med_z = zs[len(zs) // 2]

                inst_ax = med_x / 21.33
                inst_ay = med_y / 21.33
                inst_az = med_z / 21.33

                # 2. Exponential Moving Average (EMA) on acceleration
                ALPHA_ACC = 0.18
                if not initialized:
                    smooth_ax = inst_ax
                    smooth_ay = inst_ay
                    smooth_az = inst_az
                    initialized = True
                else:
                    smooth_ax = ALPHA_ACC * inst_ax + (1.0 - ALPHA_ACC) * smooth_ax
                    smooth_ay = ALPHA_ACC * inst_ay + (1.0 - ALPHA_ACC) * smooth_ay
                    smooth_az = ALPHA_ACC * inst_az + (1.0 - ALPHA_ACC) * smooth_az

                # 3. Compute Euler Angles (Pitch & Roll)
                raw_pitch = math.atan2(smooth_ax, math.sqrt(smooth_ay**2 + smooth_az**2 + 1e-6)) * 180 / math.pi
                raw_roll = math.atan2(smooth_ay, math.sqrt(smooth_ax**2 + smooth_az**2 + 1e-6)) * 180 / math.pi

                # 4. Deadband + Angle smoothing (suppress micro-jitter < 0.35 degrees)
                ALPHA_ANG = 0.20
                if abs(raw_pitch - smooth_pitch) > 0.35:
                    smooth_pitch = ALPHA_ANG * raw_pitch + (1.0 - ALPHA_ANG) * smooth_pitch
                if abs(raw_roll - smooth_roll) > 0.35:
                    smooth_roll = ALPHA_ANG * raw_roll + (1.0 - ALPHA_ANG) * smooth_roll

                telemetry["imu"].update({
                    "connected": True,
                    "raw_x": sx,
                    "raw_y": sy,
                    "raw_z": sz,
                    "ax": round(smooth_ax, 2),
                    "ay": round(smooth_ay, 2),
                    "az": round(smooth_az, 2),
                    "pitch": round(smooth_pitch, 1),
                    "roll": round(smooth_roll, 1),
                    "tilt_raw": tilt,
                    "error": None
                })
        except Exception as e:
            telemetry["imu"]["connected"] = False
            telemetry["imu"]["error"] = str(e)
            with i2c_lock:
                try:
                    if bus:
                        bus.write_byte_data(MMA7660_ADDR, 0x07, 0x01)
                except:
                    pass
        time.sleep(0.04)  # 25 Hz sampling rate

# ================= GPS WORKER (Ublox NEO-M9N at 0x42) =================
def parse_nmea_coords(raw_coord, direction):
    if not raw_coord or not direction:
        return None
    try:
        dot_idx = raw_coord.find('.')
        if dot_idx == -1:
            return None
        deg_digits = dot_idx - 2
        deg = float(raw_coord[:deg_digits])
        minutes = float(raw_coord[deg_digits:])
        decimal = deg + (minutes / 60.0)
        if direction in ['S', 'W']:
            decimal = -decimal
        return round(decimal, 6)
    except:
        return None

def gps_worker():
    UBLOX_ADDR = 0x42
    raw_buffer = ""

    while True:
        try:
            with i2c_lock:
                if bus:
                    msb = bus.read_byte_data(UBLOX_ADDR, 0xFD)
                    lsb = bus.read_byte_data(UBLOX_ADDR, 0xFE)
                    avail = (msb << 8) | lsb
                    if avail > 0:
                        chunk = bus.read_i2c_block_data(UBLOX_ADDR, 0xFF, min(avail, 32))
                        for b in chunk:
                            if b != 0xFF:
                                raw_buffer += chr(b)
                        telemetry["gps"]["connected"] = True
            
            while "\r\n" in raw_buffer:
                line, raw_buffer = raw_buffer.split("\r\n", 1)
                line = line.strip()
                if not line.startswith("$"):
                    continue

                sentences = telemetry["gps"]["raw_sentences"]
                sentences.append(line)
                if len(sentences) > 8:
                    sentences.pop(0)

                parts = line.split("*")[0].split(",")
                tag = parts[0]

                if tag.endswith("GGA") and len(parts) >= 10:
                    utc = parts[1]
                    lat = parse_nmea_coords(parts[2], parts[3])
                    lon = parse_nmea_coords(parts[4], parts[5])
                    quality = parts[6]
                    sats = int(parts[7]) if parts[7].isdigit() else 0
                    hdop = float(parts[8]) if parts[8] else 99.99
                    alt = float(parts[9]) if parts[9] else None

                    qual_map = {
                        "0": "Searching...", "1": "GPS 2D/3D Fix", "2": "DGPS Fix",
                        "4": "RTK Fixed", "5": "RTK Float"
                    }
                    has_fix = quality not in ["0", ""]

                    telemetry["gps"].update({
                        "fix": has_fix,
                        "fix_quality": qual_map.get(quality, "Fix"),
                        "satellites": sats,
                        "latitude": lat,
                        "longitude": lon,
                        "altitude_m": alt,
                        "hdop": hdop,
                        "utc_time": utc[:2] + ":" + utc[2:4] + ":" + utc[4:6] if len(utc) >= 6 else utc
                    })

                elif tag.endswith("RMC") and len(parts) >= 9:
                    status = parts[2]
                    has_fix = (status == "A")
                    if has_fix:
                        lat = parse_nmea_coords(parts[3], parts[4])
                        lon = parse_nmea_coords(parts[5], parts[6])
                        speed_knots = float(parts[7]) if parts[7] else 0.0
                        telemetry["gps"]["speed_kmh"] = round(speed_knots * 1.852, 1)
                        if lat and lon:
                            telemetry["gps"]["latitude"] = lat
                            telemetry["gps"]["longitude"] = lon
                        telemetry["gps"]["fix"] = True
                        telemetry["gps"]["fix_quality"] = "GNSS Fix (Active)"
                    else:
                        telemetry["gps"]["fix"] = False
                        if telemetry["gps"]["fix_quality"] == "No Fix":
                            telemetry["gps"]["fix_quality"] = "Searching..."

        except Exception as e:
            telemetry["gps"]["error"] = str(e)
            telemetry["gps"]["connected"] = False

        time.sleep(0.05)

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GrovePi+ & Arduino Robot Telemetry</title>
  <style>
    :root {
      --bg-dark: #090d16;
      --card-bg: rgba(18, 25, 41, 0.88);
      --card-border: rgba(255, 255, 255, 0.08);
      --blue: #38bdf8;
      --purple: #818cf8;
      --green: #22c55e;
      --yellow: #f59e0b;
      --red: #ef4444;
      --text: #f8fafc;
      --muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    body {
      background: radial-gradient(circle at 50% 0%, #152238 0%, #06080e 100%);
      color: var(--text);
      min-height: 100vh;
      padding: 20px 24px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      max-width: 1350px;
      margin: 0 auto 16px auto;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--card-border);
    }
    .title h1 {
      font-size: 22px;
      font-weight: 700;
      background: linear-gradient(135deg, #ffffff 0%, #94a3b8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .badges { display: flex; gap: 8px; flex-wrap: wrap; }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 5px 12px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--card-border);
    }
    .dot { width: 8px; height: 8px; border-radius: 50%; }
    .dot.green { background: var(--green); box-shadow: 0 0 8px var(--green); }
    .dot.yellow { background: var(--yellow); box-shadow: 0 0 8px var(--yellow); }
    .dot.red { background: var(--red); box-shadow: 0 0 8px var(--red); }

    .container {
      max-width: 1350px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 18px 20px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.35);
    }
    .card-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
    }
    .card-head h2 { font-size: 17px; font-weight: 600; }
    .tag {
      font-size: 11px;
      font-weight: 600;
      color: var(--blue);
      background: rgba(56, 189, 248, 0.12);
      padding: 3px 8px;
      border-radius: 6px;
    }

    /* SECTION 1: ARDUINO MOTOR & ENCODER */
    .robot-grid {
      display: grid;
      grid-template-columns: 300px 1fr 340px;
      gap: 20px;
      align-items: center;
    }
    @media (max-width: 1050px) {
      .robot-grid { grid-template-columns: 1fr; }
    }

    .rpm-display {
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px;
      text-align: center;
    }
    .rpm-display .rpm-num {
      font-size: 44px;
      font-weight: 800;
      font-family: monospace;
      color: var(--blue);
      text-shadow: 0 0 20px rgba(56, 189, 248, 0.35);
      line-height: 1;
      margin: 8px 0;
    }
    .rpm-display .sub { font-size: 12px; color: var(--muted); }

    /* D-PAD CONTROLLER */
    .dpad-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
    }
    .dpad-row { display: flex; gap: 8px; }
    .btn-ctrl {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid var(--card-border);
      color: #fff;
      font-size: 15px;
      font-weight: 700;
      padding: 14px 22px;
      border-radius: 10px;
      cursor: pointer;
      user-select: none;
      transition: all 0.1s;
      min-width: 68px;
      text-align: center;
    }
    .btn-ctrl:hover { background: rgba(56, 189, 248, 0.25); border-color: var(--blue); }
    .btn-ctrl:active, .btn-ctrl.active {
      background: var(--blue);
      color: #000;
      transform: scale(0.95);
      box-shadow: 0 0 15px var(--blue);
    }
    .btn-stop {
      background: rgba(239, 68, 68, 0.2);
      border-color: rgba(239, 68, 68, 0.4);
      color: var(--red);
    }
    .btn-stop:hover { background: rgba(239, 68, 68, 0.4); }
    .btn-stop:active, .btn-stop.active { background: var(--red); color: #fff; }

    .robot-info {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .info-row {
      background: rgba(0,0,0,0.25);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 10px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 13px;
    }
    .info-row span.val { font-family: monospace; font-weight: 700; color: #fff; }

    /* SECTION 2: IMU */
    .imu-grid {
      display: grid;
      grid-template-columns: 240px 1fr 1fr;
      gap: 20px;
      align-items: center;
    }
    @media (max-width: 950px) {
      .imu-grid { grid-template-columns: 1fr; }
    }
    .viewport-3d {
      width: 100%;
      height: 160px;
      perspective: 700px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: rgba(0,0,0,0.3);
      border-radius: 12px;
      border: 1px dashed rgba(255,255,255,0.1);
    }
    .cube {
      width: 75px;
      height: 75px;
      position: relative;
      transform-style: preserve-3d;
      transition: transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);
      will-change: transform;
    }
    .face {
      position: absolute;
      width: 75px;
      height: 75px;
      border: 2px solid rgba(56, 189, 248, 0.8);
      background: rgba(56, 189, 248, 0.2);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 11px;
      color: #fff;
      border-radius: 6px;
    }
    .face.front  { transform: rotateY(0deg) translateZ(37.5px); background: rgba(56, 189, 248, 0.4); }
    .face.back   { transform: rotateY(180deg) translateZ(37.5px); }
    .face.right  { transform: rotateY(90deg) translateZ(37.5px); }
    .face.left   { transform: rotateY(-90deg) translateZ(37.5px); }
    .face.top    { transform: rotateX(90deg) translateZ(37.5px); background: rgba(34, 197, 94, 0.4); }
    .face.bottom { transform: rotateX(-90deg) translateZ(37.5px); }

    .angle-boxes {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .angle-box {
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 12px;
      text-align: center;
    }
    .angle-box .lbl { font-size: 11px; color: var(--muted); text-transform: uppercase; margin-bottom: 2px; }
    .angle-box .deg { font-size: 24px; font-weight: 700; font-family: monospace; color: var(--blue); }

    .gauges { display: flex; flex-direction: column; gap: 8px; }
    .gauge { display: flex; flex-direction: column; gap: 4px; }
    .gauge-top { display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); }
    .gauge-top .val { font-family: monospace; font-weight: 700; color: #fff; }
    .gauge-bar-bg { height: 7px; background: rgba(255,255,255,0.08); border-radius: 4px; overflow: hidden; }
    .gauge-bar { height: 100%; background: linear-gradient(90deg, var(--blue), var(--purple)); border-radius: 4px; transition: width 0.25s cubic-bezier(0.2, 0.8, 0.2, 1); }

    /* SECTION 3: GPS */
    .gps-grid {
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 16px;
    }
    @media (max-width: 950px) {
      .gps-grid { grid-template-columns: 1fr; }
    }
    .gps-stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
    }
    @media (max-width: 650px) {
      .gps-stats { grid-template-columns: repeat(2, 1fr); }
    }
    .stat-card {
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 8px 12px;
    }
    .stat-card .lbl { font-size: 10px; color: var(--muted); text-transform: uppercase; margin-bottom: 2px; }
    .stat-card .val { font-size: 15px; font-weight: 700; font-family: monospace; color: #fff; }

    .radar-container {
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      height: 140px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      position: relative;
    }
    .radar-svg { width: 100px; height: 100px; }

    .nmea-feed {
      margin-top: 10px;
      background: rgba(0,0,0,0.45);
      border-radius: 6px;
      padding: 8px 12px;
      font-family: monospace;
      font-size: 11px;
      color: var(--blue);
      max-height: 48px;
      overflow: hidden;
      white-space: nowrap;
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="title">
      <h1>GrovePi+ & Arduino Robot Vehicle Telemetry</h1>
      <span style="font-size: 12px; color: var(--muted);">Raspberry Pi 4 &bull; Arduino Uno &bull; Grove Sensors</span>
    </div>
    <div class="badges">
      <div id="badge-arduino" class="badge"><div class="dot yellow"></div> Arduino: Connecting...</div>
      <div id="badge-imu" class="badge"><div class="dot yellow"></div> IMU: Connecting...</div>
      <div id="badge-gps" class="badge"><div class="dot yellow"></div> GPS: Acquiring...</div>
      <div class="badge"><div class="dot green"></div> BLE: HC-05 Ready</div>
    </div>
  </div>

  <div class="container">
    <!-- SECTION 1: ARDUINO ROBOT CAR & MOTOR CONTROLLER -->
    <div class="card">
      <div class="card-head">
        <h2>Arduino UNO &bull; 4WD Motor Controller & Optical Wheel Encoder</h2>
        <span class="tag">Port: /dev/ttyUSB0 &bull; Baud: 9600</span>
      </div>
      <div class="robot-grid">
        <!-- RPM Display -->
        <div class="rpm-display">
          <div class="sub">WHEEL ENCODER SPEED</div>
          <div id="val-rpm" class="rpm-num">0.00</div>
          <div class="sub" style="font-weight: 600; color: #fff;">REVOLUTIONS / MIN (RPM)</div>
          <div style="margin-top: 8px; font-size: 13px; color: var(--blue); font-family: monospace;">
            Linear: <span id="val-linear" style="font-weight: 700;">0.00 km/h</span>
          </div>
        </div>

        <!-- D-PAD Controls -->
        <div class="dpad-container">
          <div style="font-size: 12px; color: var(--muted); font-weight: 600; margin-bottom: 2px;">
            MOTOR COMMANDS (Arrow Keys / Click)
          </div>
          <div class="dpad-row">
            <button class="btn-ctrl" id="btn-F" onclick="sendCmd('F')">&#x2B06; FORWARD</button>
          </div>
          <div class="dpad-row">
            <button class="btn-ctrl" id="btn-L" onclick="sendCmd('L')">&#x2B05; LEFT</button>
            <button class="btn-ctrl btn-stop" id="btn-S" onclick="sendCmd('S')">&#x23F9; STOP</button>
            <button class="btn-ctrl" id="btn-R" onclick="sendCmd('R')">&#x27A1; RIGHT</button>
          </div>
          <div class="dpad-row">
            <button class="btn-ctrl" id="btn-B" onclick="sendCmd('B')">&#x2B07; BACKWARD</button>
          </div>
        </div>

        <!-- Vehicle Telemetry & Status -->
        <div class="robot-info">
          <div class="info-row">
            <span style="color: var(--muted);">Active Command</span>
            <span id="txt-last-cmd" class="val" style="color: var(--yellow);">STOP (S)</span>
          </div>
          <div class="info-row">
            <span style="color: var(--muted);">Bluetooth Module</span>
            <span class="val" style="font-size: 11px;">HC-05 (00:25:00:00:D6:05)</span>
          </div>
          <div class="info-row">
            <span style="color: var(--muted);">Raw Serial Stream</span>
            <span id="txt-raw-serial" class="val" style="font-size: 11px; color: var(--blue);">RPM:0.00</span>
          </div>
        </div>
      </div>
    </div>

    <!-- SECTION 2: IMU ACCELEROMETER -->
    <div class="card">
      <div class="card-head">
        <h2>Grove IMU / 3-Axis Accelerometer (MMA7660)</h2>
        <span class="tag">Port: I2C-1 &bull; Address: 0x4c</span>
      </div>
      <div class="imu-grid">
        <div>
          <div class="viewport-3d">
            <div id="cube" class="cube">
              <div class="face front">GrovePi</div>
              <div class="face back">Back</div>
              <div class="face right">Right</div>
              <div class="face left">Left</div>
              <div class="face top">TOP (Z)</div>
              <div class="face bottom">Bottom</div>
            </div>
          </div>
          <div style="text-align: center; margin-top: 4px; font-size: 11px; color: var(--muted);">3D Orientation</div>
        </div>

        <div class="angle-boxes">
          <div class="angle-box">
            <div class="lbl">PITCH (X)</div>
            <div id="deg-pitch" class="deg">0.0°</div>
          </div>
          <div class="angle-box">
            <div class="lbl">ROLL (Y)</div>
            <div id="deg-roll" class="deg">0.0°</div>
          </div>
          <div class="angle-box" style="grid-column: span 2;">
            <div class="lbl">TILT REGISTER</div>
            <div id="val-tilt" style="font-family: monospace; font-size: 14px; font-weight: 700; color: #fff;">0x00</div>
          </div>
        </div>

        <div class="gauges">
          <div class="gauge">
            <div class="gauge-top"><span>X-Axis</span><span id="txt-ax" class="val">+0.00 g</span></div>
            <div class="gauge-bar-bg"><div id="bar-ax" class="gauge-bar" style="width: 50%;"></div></div>
          </div>
          <div class="gauge">
            <div class="gauge-top"><span>Y-Axis</span><span id="txt-ay" class="val">+0.00 g</span></div>
            <div class="gauge-bar-bg"><div id="bar-ay" class="gauge-bar" style="width: 50%;"></div></div>
          </div>
          <div class="gauge">
            <div class="gauge-top"><span>Z-Axis</span><span id="txt-az" class="val">+0.00 g</span></div>
            <div class="gauge-bar-bg"><div id="bar-az" class="gauge-bar" style="width: 50%;"></div></div>
          </div>
        </div>
      </div>
    </div>

    <!-- SECTION 3: GPS MODULE -->
    <div class="card">
      <div class="card-head">
        <h2>7SEMI U-blox NEO-M9N GNSS Receiver</h2>
        <span class="tag">Port: I2C-2 &bull; Address: 0x42</span>
      </div>
      <div class="gps-grid">
        <div>
          <div class="gps-stats">
            <div class="stat-card">
              <div class="lbl">Fix Status</div>
              <div id="gps-fix" class="val" style="color: var(--yellow);">Searching...</div>
            </div>
            <div class="stat-card">
              <div class="lbl">Satellites</div>
              <div id="gps-sats" class="val">0</div>
            </div>
            <div class="stat-card">
              <div class="lbl">Latitude</div>
              <div id="gps-lat" class="val">--.------°</div>
            </div>
            <div class="stat-card">
              <div class="lbl">Longitude</div>
              <div id="gps-lon" class="val">--.------°</div>
            </div>
            <div class="stat-card">
              <div class="lbl">Altitude</div>
              <div id="gps-alt" class="val">-- m</div>
            </div>
            <div class="stat-card">
              <div class="lbl">Speed</div>
              <div id="gps-speed" class="val">0.0 km/h</div>
            </div>
            <div class="stat-card">
              <div class="lbl">HDOP</div>
              <div id="gps-hdop" class="val">99.99</div>
            </div>
            <div class="stat-card">
              <div class="lbl">UTC Time</div>
              <div id="gps-utc" class="val">--:--:--</div>
            </div>
          </div>

          <div class="nmea-feed" id="nmea-feed">
            Listening on I2C-2 (Address 0x42)...
          </div>
        </div>

        <div class="radar-container">
          <svg class="radar-svg" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="45" stroke="rgba(56, 189, 248, 0.2)" stroke-width="1.5" fill="none"/>
            <circle cx="50" cy="50" r="30" stroke="rgba(56, 189, 248, 0.3)" stroke-width="1" fill="none"/>
            <circle cx="50" cy="50" r="15" stroke="rgba(56, 189, 248, 0.4)" stroke-width="1" fill="none"/>
            <line x1="5" y1="50" x2="95" y2="50" stroke="rgba(56, 189, 248, 0.2)" stroke-width="1"/>
            <line x1="50" y1="5" x2="50" y2="95" stroke="rgba(56, 189, 248, 0.2)" stroke-width="1"/>
            <text x="50" y="10" font-size="6" fill="#38bdf8" text-anchor="middle" font-weight="bold">N</text>
            <text x="92" y="52" font-size="6" fill="#94a3b8" text-anchor="middle">E</text>
            <text x="50" y="94" font-size="6" fill="#94a3b8" text-anchor="middle">S</text>
            <text x="8" y="52" font-size="6" fill="#94a3b8" text-anchor="middle">W</text>
            <circle id="radar-target" cx="50" cy="50" r="3.5" fill="#f59e0b">
              <animate attributeName="opacity" values="1;0.4;1" dur="1.5s" repeatCount="indefinite"/>
            </circle>
          </svg>
          <div id="radar-caption" style="margin-top: 4px; font-size: 11px; color: var(--muted); font-weight: 500;">
            Searching for Satellites...
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    async function sendCmd(cmd) {
      try {
        await fetch('/api/motor?cmd=' + cmd);
        highlightBtn(cmd);
      } catch (err) {
        console.error(err);
      }
    }

    function highlightBtn(cmd) {
      ['F', 'B', 'L', 'R', 'S'].forEach(c => {
        const el = document.getElementById('btn-' + c);
        if (el) el.classList.remove('active');
      });
      const activeEl = document.getElementById('btn-' + cmd);
      if (activeEl) activeEl.classList.add('active');
    }

    // Keyboard driving controls
    window.addEventListener('keydown', (e) => {
      if (e.repeat) return;
      if (e.key === 'ArrowUp' || e.key === 'w' || e.key === 'W') sendCmd('F');
      else if (e.key === 'ArrowDown' || e.key === 's' || e.key === 'S') sendCmd('B');
      else if (e.key === 'ArrowLeft' || e.key === 'a' || e.key === 'A') sendCmd('L');
      else if (e.key === 'ArrowRight' || e.key === 'd' || e.key === 'D') sendCmd('R');
      else if (e.key === ' ' || e.key === 'x' || e.key === 'X') sendCmd('S');
    });

    window.addEventListener('keyup', (e) => {
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'w', 'W', 's', 'S', 'a', 'A', 'd', 'D'].includes(e.key)) {
        sendCmd('S');
      }
    });

    function accelToPct(v) {
      let p = ((v + 1.5) / 3.0) * 100;
      return Math.max(0, Math.min(100, p));
    }

    async function poll() {
      try {
        const res = await fetch('/api/telemetry');
        const d = await res.json();

        // 1. Arduino Telemetry
        if (d.arduino && d.arduino.connected) {
          document.getElementById('badge-arduino').innerHTML = '<div class="dot green"></div> Arduino: Connected';
          document.getElementById('val-rpm').innerText = d.arduino.rpm.toFixed(2);
          document.getElementById('val-linear').innerText = d.arduino.speed_kmh.toFixed(2) + ' km/h';
          document.getElementById('txt-raw-serial').innerText = d.arduino.last_line || 'RPM:0.00';

          const cmdMap = { 'F': 'FORWARD (F)', 'B': 'BACKWARD (B)', 'L': 'LEFT (L)', 'R': 'RIGHT (R)', 'S': 'STOP (S)' };
          document.getElementById('txt-last-cmd').innerText = cmdMap[d.arduino.last_cmd] || d.arduino.last_cmd;
        } else {
          document.getElementById('badge-arduino').innerHTML = '<div class="dot red"></div> Arduino: Disconnected';
        }

        // 2. IMU Telemetry
        if (d.imu && d.imu.connected) {
          document.getElementById('badge-imu').innerHTML = '<div class="dot green"></div> IMU: Active';
          document.getElementById('deg-pitch').innerText = d.imu.pitch.toFixed(1) + '°';
          document.getElementById('deg-roll').innerText = d.imu.roll.toFixed(1) + '°';
          document.getElementById('val-tilt').innerText = '0x' + d.imu.tilt_raw.toString(16).toUpperCase();

          document.getElementById('txt-ax').innerText = (d.imu.ax >= 0 ? '+' : '') + d.imu.ax.toFixed(2) + ' g';
          document.getElementById('txt-ay').innerText = (d.imu.ay >= 0 ? '+' : '') + d.imu.ay.toFixed(2) + ' g';
          document.getElementById('txt-az').innerText = (d.imu.az >= 0 ? '+' : '') + d.imu.az.toFixed(2) + ' g';

          document.getElementById('bar-ax').style.width = accelToPct(d.imu.ax) + '%';
          document.getElementById('bar-ay').style.width = accelToPct(d.imu.ay) + '%';
          document.getElementById('bar-az').style.width = accelToPct(d.imu.az) + '%';

          const cube = document.getElementById('cube');
          cube.style.transform = `rotateX(${-d.imu.pitch}deg) rotateZ(${d.imu.roll}deg)`;
        } else {
          document.getElementById('badge-imu').innerHTML = '<div class="dot red"></div> IMU: Disconnected';
        }

        // 3. GPS Telemetry
        if (d.gps && d.gps.connected) {
          const fixTxt = document.getElementById('gps-fix');
          const radarCap = document.getElementById('radar-caption');
          const target = document.getElementById('radar-target');

          if (d.gps.fix) {
            document.getElementById('badge-gps').innerHTML = '<div class="dot green"></div> GPS: 3D Fix';
            fixTxt.innerText = d.gps.fix_quality;
            fixTxt.style.color = 'var(--green)';
            target.setAttribute('fill', '#22c55e');
            if (d.gps.latitude && d.gps.longitude) {
              document.getElementById('gps-lat').innerText = d.gps.latitude.toFixed(6) + '°';
              document.getElementById('gps-lon').innerText = d.gps.longitude.toFixed(6) + '°';
              radarCap.innerText = `${d.gps.latitude.toFixed(4)}°, ${d.gps.longitude.toFixed(4)}°`;
            }
          } else {
            document.getElementById('badge-gps').innerHTML = '<div class="dot yellow"></div> GPS: Acquiring Satellites';
            fixTxt.innerText = d.gps.fix_quality;
            fixTxt.style.color = 'var(--yellow)';
            target.setAttribute('fill', '#f59e0b');
            document.getElementById('gps-lat').innerText = '--.------°';
            document.getElementById('gps-lon').innerText = '--.------°';
            radarCap.innerText = 'Searching for Satellites...';
          }

          document.getElementById('gps-sats').innerText = d.gps.satellites;
          document.getElementById('gps-alt').innerText = (d.gps.altitude_m !== null) ? d.gps.altitude_m.toFixed(1) + ' m' : '-- m';
          document.getElementById('gps-speed').innerText = d.gps.speed_kmh.toFixed(1) + ' km/h';
          document.getElementById('gps-hdop').innerText = d.gps.hdop.toFixed(2);
          document.getElementById('gps-utc').innerText = d.gps.utc_time || '--:--:--';

          if (d.gps.raw_sentences && d.gps.raw_sentences.length > 0) {
            document.getElementById('nmea-feed').innerHTML = d.gps.raw_sentences.slice(-2).join('<br>');
          }
        } else {
          document.getElementById('badge-gps').innerHTML = '<div class="dot red"></div> GPS: Disconnected';
        }
      } catch (err) {
        console.error(err);
      }
    }

    setInterval(poll, 100);
    poll();
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/api/telemetry")
def get_telemetry():
    return jsonify(telemetry)

@app.route("/api/motor", methods=["GET", "POST"])
def motor_control():
    cmd = request.args.get("cmd")
    if not cmd and request.is_json:
        cmd = request.json.get("cmd")
    if cmd:
        sent = send_motor_command(cmd)
        return jsonify({"status": "ok", "cmd": cmd, "sent": sent})
    return jsonify({"status": "error", "message": "No command provided"}), 400

if __name__ == "__main__":
    init_bus()
    t_imu = threading.Thread(target=imu_worker, daemon=True)
    t_gps = threading.Thread(target=gps_worker, daemon=True)
    t_ard = threading.Thread(target=arduino_worker, daemon=True)
    t_imu.start()
    t_gps.start()
    t_ard.start()
    print("Starting GrovePi & Arduino Integrated Telemetry Server on port 5000...")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
