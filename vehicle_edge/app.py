import subprocess
import os
import time
import math
import io
import threading
import urllib.request
import numpy as np
from PIL import Image
from flask import Flask, jsonify, request, Response, render_template_string
try:
    import smbus
except ImportError:
    smbus = None
try:
    import serial
except ImportError:
    serial = None
try:
    import grovepi
except ImportError:
    grovepi = None
try:
    from picamera2 import Picamera2
except ImportError:
    Picamera2 = None

app = Flask(__name__)

telemetry = {
    "camera": {
        "connected": False,
        "resolution": "640x480",
        "error": None
    },
    "ultrasonic": {
        "connected": False,
        "port": "D2",
        "distance_cm": 0,
        "warning": "SAFE",
        "status": "SAFE",
        "alert_level": "green",
        "error": None
    },
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
        "connected": True,
        "fix": False,
        "has_satellite_fix": False,
        "fix_quality": "Searching (0 Sats - Indoors)",
        "satellites": 0,
        "latitude": 13.188447,
        "longitude": 80.106112,
        "city": "Vel Tech High Tech, Avadi",
        "region": "Chennai, Tamil Nadu",
        "altitude_m": 28.0,
        "speed_kmh": 0.0,
        "utc_time": "--:--:--",
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
    },
    "night_vision": {
        "mode": "auto",
        "active": False,
        "ambient_lux": 5.6,
        "darkness_pct": 94.4,
        "ir_flood_active": True,
        "exposure_gain": 1.6,
        "contrast_gain": 1.3,
        "clahe": True,
        "tactical_reticle": True,
        "current_palette": "green"
    }
}

i2c_lock = threading.Lock()
bus = None

arduino_lock = threading.Lock()
arduino_ser = None

camera_frame = None
camera_lock = threading.Lock()

def reset_grovepi():
    """Assert hardware reset pulse on GrovePi ATmega328P coprocessor via GPIO 8."""
    try:
        subprocess.run(["pinctrl", "set", "8", "op", "dl"], check=False)
        time.sleep(0.15)
        subprocess.run(["pinctrl", "set", "8", "op", "dh"], check=False)
        time.sleep(0.5)
        print("[GrovePi] Hardware reset pulse asserted on GPIO 8.")
        return True
    except Exception as e:
        print(f"[GrovePi] Reset error: {e}")
        return False

def init_bus():
    global bus
    reset_grovepi()
    try:
        bus = smbus.SMBus(1)
        return True
    except Exception as e:
        print(f"Error initializing I2C bus: {e}")
        return False

# ================= NIGHT VISION & 3W IR ILLUMINATOR ISP =================
class NightVisionISP:
    def __init__(self):
        self.mode = "auto"              # "off", "auto", "mono", "green", "thermal"
        self.active = False
        self.exposure_gain = 1.6        # 1.0 to 3.0x
        self.contrast_gain = 1.3        # 1.0 to 2.5x
        self.clahe_enabled = True
        self.tactical_reticle = True
        self.ambient_lux = 5.6
        self.darkness_pct = 94.4
        self.ir_flood_active = True
        self.current_palette = "green"
        self._build_thermal_lut()

    def _build_thermal_lut(self):
        self.thermal_lut = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            x = i / 255.0
            if x < 0.25:
                r = int(x * 4 * 70)
                g = 0
                b = int(40 + x * 4 * 180)
            elif x < 0.5:
                t = (x - 0.25) * 4
                r = int(70 + t * 175)
                g = int(t * 30)
                b = int(220 * (1.0 - t * 0.85))
            elif x < 0.75:
                t = (x - 0.5) * 4
                r = int(245 + t * 10)
                g = int(30 + t * 195)
                b = int(35 * (1.0 - t))
            else:
                t = (x - 0.75) * 4
                r = 255
                g = 255
                b = int(t * 255)
            self.thermal_lut[i] = [r, g, b]

    def get_config(self):
        return {
            "mode": str(self.mode),
            "active": bool(self.active),
            "exposure_gain": round(float(self.exposure_gain), 2),
            "contrast_gain": round(float(self.contrast_gain), 2),
            "clahe": bool(self.clahe_enabled),
            "tactical_reticle": bool(self.tactical_reticle),
            "ambient_lux": round(float(self.ambient_lux), 1),
            "darkness_pct": round(float(self.darkness_pct), 1),
            "ir_flood_active": bool(self.ir_flood_active),
            "current_palette": str(self.current_palette)
        }

    def update_config(self, data):
        if "mode" in data and data["mode"] in ["off", "auto", "mono", "green", "thermal"]:
            self.mode = str(data["mode"])
        if "exposure_gain" in data:
            self.exposure_gain = max(1.0, min(3.0, float(data["exposure_gain"])))
        if "contrast_gain" in data:
            self.contrast_gain = max(1.0, min(2.5, float(data["contrast_gain"])))
        if "clahe" in data:
            self.clahe_enabled = bool(data["clahe"])
        if "tactical_reticle" in data:
            self.tactical_reticle = bool(data["tactical_reticle"])

    def process_frame(self, arr):
        H, W = arr.shape[:2]
        sample = arr[::8, ::8, :].astype(np.float32)
        lum = float((sample[:,:,0]*0.299 + sample[:,:,1]*0.587 + sample[:,:,2]*0.114).mean())
        self.ambient_lux = float(np.clip((lum / 255.0) * 100.0, 0.0, 100.0))
        self.darkness_pct = float(100.0 - self.ambient_lux)
        self.ir_flood_active = bool(self.darkness_pct >= 50.0)

        if self.mode == "off":
            self.active = False
            self.current_palette = "standard"
            return arr
        elif self.mode == "auto":
            self.active = bool(self.darkness_pct >= 55.0)
            target_palette = "green" if self.active else "standard"
        else:
            self.active = True
            target_palette = str(self.mode)

        self.current_palette = target_palette if self.active else "standard"
        if not self.active:
            return arr

        # Step 1: Grayscale conversion (IR response)
        r = arr[:, :, 0].astype(np.uint16)
        g = arr[:, :, 1].astype(np.uint16)
        b = arr[:, :, 2].astype(np.uint16)
        gray = ((r * 77 + g * 150 + b * 29) >> 8).astype(np.uint8)

        # Step 2: Dynamic contrast & Exposure Gain
        min_v = float(gray.min())
        max_v = float(gray.max())
        if self.clahe_enabled and max_v > min_v + 5:
            norm = (gray.astype(np.float32) - min_v) / (max_v - min_v) * 255.0
            enhanced = norm * self.exposure_gain
        else:
            enhanced = gray.astype(np.float32) * self.exposure_gain

        enhanced = np.clip((enhanced - 128.0) * self.contrast_gain + 128.0, 0.0, 255.0).astype(np.uint8)

        # Step 3: Apply Palette
        if self.current_palette == "green":
            # NVG Green Phosphor PVS-14
            r_ch = (enhanced.astype(np.uint16) * 28 >> 8).astype(np.uint8)
            g_ch = np.clip(enhanced.astype(np.uint16) * 290 >> 8, 0, 255).astype(np.uint8)
            b_ch = (enhanced.astype(np.uint16) * 48 >> 8).astype(np.uint8)
            out = np.stack([r_ch, g_ch, b_ch], axis=-1)
        elif self.current_palette == "thermal":
            # FLIR Ironbow Thermal Heatmap
            out = self.thermal_lut[enhanced]
        else:
            # Tactical B&W IR Monochrome
            out = np.stack([enhanced, enhanced, enhanced], axis=-1)

        # Step 4: Tactical Reticle HUD
        if self.tactical_reticle:
            self._draw_reticle(out, W, H)

        return out

    def _draw_reticle(self, out, W, H):
        cx, cy = W // 2, H // 2
        hud_col = [0, 255, 120] if self.current_palette == "green" else ([255, 200, 0] if self.current_palette == "thermal" else [220, 220, 220])
        out[cy, max(0, cx-16):max(0, cx-4)] = hud_col
        out[cy, min(W, cx+4):min(W, cx+16)] = hud_col
        out[max(0, cy-16):max(0, cy-4), cx] = hud_col
        out[min(H, cy+4):min(H, cy+16), cx] = hud_col
        out[cy, cx] = [255, 255, 255]
        b_len = 22
        ix, iy = 18, 18
        out[iy, ix:ix+b_len] = hud_col
        out[iy:iy+b_len, ix] = hud_col
        out[iy, W-ix-b_len:W-ix] = hud_col
        out[iy:iy+b_len, W-ix-1] = hud_col
        out[H-iy-1, ix:ix+b_len] = hud_col
        out[H-iy-b_len:H-iy, ix] = hud_col
        out[H-iy-1, W-ix-b_len:W-ix] = hud_col
        out[H-iy-b_len:H-iy, W-ix-1] = hud_col

nv_isp = NightVisionISP()

# ================= CAMERA WORKER (OV5647 CSI via Picamera2) =================
def camera_worker():
    global camera_frame
    try:
        if Picamera2 is None:
            raise RuntimeError("Picamera2 not installed")
        picam2 = Picamera2()
        config = picam2.create_video_configuration(main={"size": (640, 480), "format": "RGB888"})
        picam2.configure(config)
        picam2.start()
        telemetry["camera"]["connected"] = True
        time.sleep(0.5)
        
        last_is_nvg = None
        while True:
            is_nvg = nv_isp.active
            if is_nvg != last_is_nvg:
                last_is_nvg = is_nvg
                try:
                    if is_nvg:
                        picam2.set_controls({"AeExposureMode": 1, "AnalogueGain": min(12.0, 4.0 * nv_isp.exposure_gain)})
                    else:
                        picam2.set_controls({"AeExposureMode": 0, "AnalogueGain": 1.0})
                except Exception:
                    pass

            arr = picam2.capture_array("main")
            if arr is not None:
                if len(arr.shape) == 3 and arr.shape[2] == 4:
                    arr = arr[:, :, :3]
                processed = nv_isp.process_frame(arr)
                bio = io.BytesIO()
                Image.fromarray(processed).save(bio, format="JPEG", quality=75)
                data = bio.getvalue()
                with camera_lock:
                    camera_frame = data
            
            telemetry["night_vision"] = nv_isp.get_config()
            time.sleep(0.035) # ~28 FPS
    except Exception as e:
        telemetry["camera"]["connected"] = False
        telemetry["camera"]["error"] = str(e)
        print("Camera worker error:", e)

# ================= ULTRASONIC WORKER (GrovePi Port D2) =================
def ultrasonic_worker():
    ULTRASONIC_PORT = 2
    smooth_dist = None
    consecutive_fails = 0

    while True:
        val = None
        for _ in range(3):
            try:
                with i2c_lock:
                    raw = grovepi.ultrasonicRead(ULTRASONIC_PORT)
                if isinstance(raw, (int, float)) and 2 <= raw <= 400:
                    val = float(raw)
                    break
            except Exception:
                pass
            time.sleep(0.04)

        if val is not None:
            consecutive_fails = 0
            if smooth_dist is None:
                smooth_dist = val
            else:
                if val < smooth_dist - 15:
                    smooth_dist = val
                else:
                    smooth_dist = 0.55 * val + 0.45 * smooth_dist

            final_dist = round(smooth_dist, 1)
            telemetry["ultrasonic"]["connected"] = True
            telemetry["ultrasonic"]["distance_cm"] = final_dist

            if final_dist <= 50.0:
                telemetry["ultrasonic"]["warning"] = "DANGER"
                telemetry["ultrasonic"]["status"] = "DANGER"
                telemetry["ultrasonic"]["alert_level"] = "red"
            elif final_dist <= 90.0:
                telemetry["ultrasonic"]["warning"] = "OBJECT DETECTED"
                telemetry["ultrasonic"]["status"] = "OK / CAUTION"
                telemetry["ultrasonic"]["alert_level"] = "yellow"
            else:
                telemetry["ultrasonic"]["warning"] = "SAFE"
                telemetry["ultrasonic"]["status"] = "SAFE"
                telemetry["ultrasonic"]["alert_level"] = "green"
            telemetry["ultrasonic"]["error"] = None
        else:
            consecutive_fails += 1
            if consecutive_fails >= 8:
                telemetry["ultrasonic"]["connected"] = False
                telemetry["ultrasonic"]["warning"] = "OFFLINE"
                telemetry["ultrasonic"]["error"] = "Sensor read timeout"
            if consecutive_fails >= 20 and (consecutive_fails % 30 == 0):
                print("[GrovePi] Re-asserting reset due to consecutive timeouts...")
                with i2c_lock:
                    reset_grovepi()

        time.sleep(0.06)

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
                bus.write_byte_data(MMA7660_ADDR, 0x07, 0x00)
                bus.write_byte_data(MMA7660_ADDR, 0x08, (3 << 5) | 0x02)
                bus.write_byte_data(MMA7660_ADDR, 0x07, 0x01)
                telemetry["imu"]["connected"] = True
        except Exception as e:
            telemetry["imu"]["error"] = str(e)

    def parse_6bit(val):
        if val & 0x40:
            return None
        v = val & 0x3F
        if v & 0x20:
            v -= 0x40
        return v

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
                raw_history.append((sx, sy, sz))
                if len(raw_history) > 5:
                    raw_history.pop(0)

                xs = sorted([s[0] for s in raw_history])
                ys = sorted([s[1] for s in raw_history])
                zs = sorted([s[2] for s in raw_history])
                med_x = xs[len(xs) // 2]
                med_y = ys[len(ys) // 2]
                med_z = zs[len(zs) // 2]

                inst_ax = med_x / 21.33
                inst_ay = med_y / 21.33
                inst_az = med_z / 21.33

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

                raw_pitch = math.atan2(smooth_ax, math.sqrt(smooth_ay**2 + smooth_az**2 + 1e-6)) * 180 / math.pi
                raw_roll = math.atan2(smooth_ay, math.sqrt(smooth_ax**2 + smooth_az**2 + 1e-6)) * 180 / math.pi

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
        time.sleep(0.04)

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

# Exact coordinates: Vel Tech High Tech Dr. Rangarajan Dr. Sakunthala Engineering College
COARSE_LAT = 13.188447
COARSE_LON = 80.106112

def network_location_worker():
    global COARSE_LAT, COARSE_LON
    while True:
        try:
            if not telemetry["gps"].get("has_satellite_fix"):
                telemetry["gps"]["latitude"] = COARSE_LAT
                telemetry["gps"]["longitude"] = COARSE_LON
                telemetry["gps"]["city"] = "Vel Tech High Tech, Avadi"
                telemetry["gps"]["region"] = "Chennai, Tamil Nadu"
                telemetry["gps"]["altitude_m"] = 28.0
        except Exception:
            pass
        time.sleep(30)

def gps_worker():
    UBLOX_ADDR = 0x42
    raw_buffer = ""
    gsv_in_view = {}

    while True:
        try:
            with i2c_lock:
                if bus:
                    msb = bus.read_byte_data(UBLOX_ADDR, 0xFD)
                    lsb = bus.read_byte_data(UBLOX_ADDR, 0xFE)
                    avail = (msb << 8) | lsb
                    if avail > 0:
                        to_read = min(avail, 128)
                        while to_read > 0:
                            block_len = min(to_read, 32)
                            chunk = bus.read_i2c_block_data(UBLOX_ADDR, 0xFF, block_len)
                            for b in chunk:
                                if b != 0xFF:
                                    raw_buffer += chr(b)
                            to_read -= block_len
                        telemetry["gps"]["connected"] = True

            if len(raw_buffer) > 4096:
                raw_buffer = raw_buffer[-2048:]

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

                if (tag.endswith("GGA") or tag.endswith("GNS")) and len(parts) >= 10:
                    utc = parts[1]
                    lat = parse_nmea_coords(parts[2], parts[3])
                    lon = parse_nmea_coords(parts[4], parts[5])
                    quality = parts[6]
                    sats = int(parts[7]) if parts[7].isdigit() else 0
                    hdop = float(parts[8]) if parts[8] else 99.99
                    alt = float(parts[9]) if parts[9] else None

                    qual_map = {
                        "0": "Searching (0 Sats)", "1": "GNSS 3D Fix", "2": "DGPS Fix",
                        "4": "RTK Fixed", "5": "RTK Float"
                    }
                    has_fix = quality not in ["0", "", None] and (lat is not None) and (lon is not None)

                    telemetry["gps"]["connected"] = True
                    telemetry["gps"]["satellites"] = sats
                    telemetry["gps"]["hdop"] = hdop
                    if utc and len(utc) >= 6:
                        telemetry["gps"]["utc_time"] = f"{utc[:2]}:{utc[2:4]}:{utc[4:6]}"

                    if has_fix:
                        telemetry["gps"].update({
                            "fix": True,
                            "has_satellite_fix": True,
                            "fix_quality": qual_map.get(quality, "3D Lock"),
                            "latitude": lat,
                            "longitude": lon,
                            "altitude_m": alt if alt is not None else telemetry["gps"].get("altitude_m", 16.0),
                        })
                    else:
                        telemetry["gps"]["fix"] = False
                        telemetry["gps"]["has_satellite_fix"] = False
                        telemetry["gps"]["fix_quality"] = f"Searching ({sats} Sats - Indoors)"

                elif tag.endswith("GSV") and len(parts) >= 4:
                    constellation = tag[1:3]
                    if parts[3].isdigit():
                        gsv_in_view[constellation] = int(parts[3])
                        total_in_view = sum(gsv_in_view.values())
                        telemetry["gps"]["satellites_in_view"] = total_in_view
                        if not telemetry["gps"].get("has_satellite_fix"):
                            if total_in_view > 0:
                                telemetry["gps"]["fix_quality"] = f"Acquiring ({total_in_view} in view)"
                            else:
                                telemetry["gps"]["fix_quality"] = "Searching (0 Sats - Indoors)"

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
                            telemetry["gps"]["has_satellite_fix"] = True
                            telemetry["gps"]["fix_quality"] = "GNSS 3D Fix"
                    else:
                        telemetry["gps"]["speed_kmh"] = 0.0

        except Exception as e:
            telemetry["gps"]["error"] = str(e)
            # Retain connected state on transient I2C bus contention
            pass

        time.sleep(0.05)

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Autonomous Robot Telemetry & FPV</title>
  <style>
    :root {
      --bg-dark: #070a12;
      --card-bg: rgba(16, 23, 38, 0.9);
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
      background: radial-gradient(circle at 50% 0%, #121c2e 0%, #05070c 100%);
      color: var(--text);
      min-height: 100vh;
      padding: 16px 20px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      max-width: 1400px;
      margin: 0 auto 12px auto;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--card-border);
    }
    .title h1 {
      font-size: 20px;
      font-weight: 700;
      background: linear-gradient(135deg, #ffffff 0%, #94a3b8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .badges { display: flex; gap: 8px; flex-wrap: wrap; }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 11px;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid var(--card-border);
    }
    .dot { width: 8px; height: 8px; border-radius: 50%; }
    .dot.green { background: var(--green); box-shadow: 0 0 8px var(--green); }
    .dot.yellow { background: var(--yellow); box-shadow: 0 0 8px var(--yellow); }
    .dot.red { background: var(--red); box-shadow: 0 0 8px var(--red); }

    .container {
      max-width: 1400px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 14px 18px;
      box-shadow: 0 8px 22px rgba(0,0,0,0.4);
    }
    .card-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .card-head h2 { font-size: 15px; font-weight: 600; }
    .tag {
      font-size: 11px;
      font-weight: 600;
      color: var(--blue);
      background: rgba(56, 189, 248, 0.12);
      padding: 3px 8px;
      border-radius: 6px;
    }

    /* TOP ROW: CAMERA & CONTROLLER */
    .top-split {
      display: grid;
      grid-template-columns: 1.1fr 1fr;
      gap: 12px;
    }
    @media (max-width: 1050px) {
      .top-split { grid-template-columns: 1fr; }
    }

    /* FPV CAMERA CARD */
    .cam-box {
      width: 100%;
      height: 250px;
      background: #000;
      border-radius: 10px;
      overflow: hidden;
      position: relative;
      border: 1px solid rgba(255, 255, 255, 0.1);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .cam-box img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .cam-overlay {
      position: absolute;
      top: 10px;
      left: 12px;
      right: 12px;
      display: flex;
      justify-content: space-between;
      pointer-events: none;
      font-size: 11px;
      font-family: monospace;
      color: #38bdf8;
      text-shadow: 0 1px 3px #000;
    }
    .crosshair {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: 32px;
      height: 32px;
      pointer-events: none;
      opacity: 0.6;
    }
    .crosshair::before, .crosshair::after {
      content: '';
      position: absolute;
      background: rgba(56, 189, 248, 0.8);
    }
    .crosshair::before { top: 15px; left: 0; width: 32px; height: 2px; }
    .crosshair::after { top: 0; left: 15px; width: 2px; height: 32px; }

    /* ULTRASONIC SENSOR CARD */
    .sonic-container {
      display: grid;
      grid-template-columns: 140px 1fr;
      gap: 16px;
      align-items: center;
      margin-top: 10px;
      background: rgba(0,0,0,0.25);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 12px 16px;
    }
    .sonic-num {
      text-align: center;
    }
    .sonic-num .val {
      font-size: 38px;
      font-weight: 800;
      font-family: monospace;
      line-height: 1;
      color: var(--blue);
    }
    .sonic-num .lbl { font-size: 11px; color: var(--muted); margin-top: 4px; text-transform: uppercase; }

    .sonic-meter {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .sonic-bar-bg {
      height: 12px;
      background: rgba(255,255,255,0.08);
      border-radius: 6px;
      overflow: hidden;
      position: relative;
    }
    .sonic-bar-fill {
      height: 100%;
      width: 100%;
      border-radius: 6px;
      background: var(--green);
      transition: width 0.15s ease-out, background 0.2s;
    }
    .sonic-status-tag {
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      display: inline-block;
      padding: 3px 8px;
      border-radius: 4px;
    }

    /* ROBOT & ENCODER SECTION */
    .robot-grid {
      display: grid;
      grid-template-columns: 160px 1fr 170px;
      gap: 14px;
      align-items: center;
    }
    @media (max-width: 1050px) {
      .robot-grid { grid-template-columns: 1fr; }
    }
    .rpm-display {
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 12px;
      text-align: center;
    }
    .rpm-display .rpm-num {
      font-size: 34px;
      font-weight: 800;
      font-family: monospace;
      color: var(--blue);
      line-height: 1;
      margin: 6px 0;
    }

    .dpad-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
    }
    .dpad-row { display: flex; gap: 6px; }
    .btn-ctrl {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid var(--card-border);
      color: #fff;
      font-size: 13px;
      font-weight: 700;
      padding: 10px 18px;
      border-radius: 8px;
      cursor: pointer;
      user-select: none;
      transition: all 0.1s;
      min-width: 60px;
      text-align: center;
    }
    .btn-ctrl:hover { background: rgba(56, 189, 248, 0.25); border-color: var(--blue); }
    .btn-ctrl:active, .btn-ctrl.active {
      background: var(--blue);
      color: #000;
      transform: scale(0.95);
      box-shadow: 0 0 12px var(--blue);
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
      gap: 6px;
    }
    .info-row {
      background: rgba(0,0,0,0.25);
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 6px 10px;
      display: flex;
      justify-content: space-between;
      font-size: 12px;
    }
    .info-row span.val { font-family: monospace; font-weight: 700; color: #fff; }

    /* IMU & GPS BOTTOM ROW */
    .bottom-split {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    @media (max-width: 1050px) {
      .bottom-split { grid-template-columns: 1fr; }
    }

    /* IMU */
    .imu-grid {
      display: grid;
      grid-template-columns: 150px 1fr 1fr;
      gap: 14px;
      align-items: center;
    }
    .viewport-3d {
      width: 100%;
      height: 120px;
      perspective: 600px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: rgba(0,0,0,0.3);
      border-radius: 10px;
      border: 1px dashed rgba(255,255,255,0.1);
    }
    .cube {
      width: 60px;
      height: 60px;
      position: relative;
      transform-style: preserve-3d;
      transition: transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);
      will-change: transform;
    }
    .face {
      position: absolute;
      width: 60px;
      height: 60px;
      border: 2px solid rgba(56, 189, 248, 0.8);
      background: rgba(56, 189, 248, 0.2);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 10px;
      color: #fff;
      border-radius: 4px;
    }
    .face.front  { transform: rotateY(0deg) translateZ(30px); background: rgba(56, 189, 248, 0.4); }
    .face.back   { transform: rotateY(180deg) translateZ(30px); }
    .face.right  { transform: rotateY(90deg) translateZ(30px); }
    .face.left   { transform: rotateY(-90deg) translateZ(30px); }
    .face.top    { transform: rotateX(90deg) translateZ(30px); background: rgba(34, 197, 94, 0.4); }
    .face.bottom { transform: rotateX(-90deg) translateZ(30px); }

    .angle-boxes { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .angle-box {
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 8px;
      text-align: center;
    }
    .angle-box .lbl { font-size: 10px; color: var(--muted); text-transform: uppercase; margin-bottom: 2px; }
    .angle-box .deg { font-size: 18px; font-weight: 700; font-family: monospace; color: var(--blue); }

    .gauges { display: flex; flex-direction: column; gap: 6px; }
    .gauge { display: flex; flex-direction: column; gap: 3px; }
    .gauge-top { display: flex; justify-content: space-between; font-size: 11px; color: var(--muted); }
    .gauge-top .val { font-family: monospace; font-weight: 700; color: #fff; }
    .gauge-bar-bg { height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden; }
    .gauge-bar { height: 100%; background: linear-gradient(90deg, var(--blue), var(--purple)); border-radius: 3px; transition: width 0.25s cubic-bezier(0.2, 0.8, 0.2, 1); }

    /* GPS */
    .gps-grid { display: grid; grid-template-columns: 1.3fr 1fr; gap: 12px; }
    .gps-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
    .stat-card {
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 6px 8px;
    }
    .stat-card .lbl { font-size: 9px; color: var(--muted); text-transform: uppercase; margin-bottom: 2px; }
    .stat-card .val { font-size: 13px; font-weight: 700; font-family: monospace; color: #fff; }

    .radar-container {
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      height: 120px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      position: relative;
    }
    .radar-svg { width: 85px; height: 85px; }

    .nmea-feed {
      margin-top: 8px;
      background: rgba(0,0,0,0.45);
      border-radius: 6px;
      padding: 6px 10px;
      font-family: monospace;
      font-size: 10px;
      color: var(--blue);
      max-height: 38px;
      overflow: hidden;
      white-space: nowrap;
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="title">
      <h1>Autonomous Vehicle Telemetry & FPV Suite</h1>
      <span style="font-size: 11px; color: var(--muted);">Raspberry Pi 4 &bull; Camera &bull; Ultrasonic D2 &bull; IMU &bull; GPS &bull; Arduino</span>
    </div>
    <div class="badges">
      <div id="badge-cam" class="badge"><div class="dot green"></div> CAM: OV5647 FPV</div>
      <div id="badge-sonic" class="badge"><div class="dot green"></div> Ultrasonic: D2</div>
      <div id="badge-arduino" class="badge"><div class="dot green"></div> Arduino: Connected</div>
      <div id="badge-imu" class="badge"><div class="dot green"></div> IMU: Active</div>
      <div id="badge-gps" class="badge"><div class="dot yellow"></div> GPS: Acquiring</div>
    </div>
  </div>

  <div class="container">
    <!-- TOP ROW: FPV CAMERA & VEHICLE MOTOR CONTROLLER -->
    <div class="top-split">
      <!-- FPV CAMERA FEED CARD -->
      <div class="card">
        <div class="card-head">
          <h2>Live FPV Camera Feed (OmniVision OV5647)</h2>
          <span class="tag">640x480 &bull; ~25 FPS</span>
        </div>
        <div class="cam-box">
          <img src="/video_feed" alt="Live FPV Camera Stream" />
          <div class="crosshair"></div>
          <div class="cam-overlay">
            <span>REC &#x25CF; LIVE FPV</span>
            <span id="cam-hud-dist">SONIC: -- cm</span>
          </div>
        </div>

        <!-- ULTRASONIC SENSOR PROXIMITY METER -->
        <div class="sonic-container">
          <div class="sonic-num">
            <div id="sonic-cm" class="val">--</div>
            <div class="lbl">DISTANCE (CM)</div>
          </div>
          <div class="sonic-meter">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 12px; font-weight: 600; color: var(--muted);">PROXIMITY WARNING:</span>
              <span id="sonic-badge" class="sonic-status-tag" style="background: rgba(34, 197, 94, 0.2); color: var(--green);">CLEAR</span>
            </div>
            <div class="sonic-bar-bg">
              <div id="sonic-bar" class="sonic-bar-fill" style="width: 100%;"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 10px; color: var(--muted);">
              <span>0 cm (STOP)</span>
              <span>20 cm</span>
              <span>50 cm</span>
              <span>100+ cm</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ARDUINO 4WD CONTROLLER & ENCODER -->
      <div class="card">
        <div class="card-head">
          <h2>Arduino UNO &bull; 4WD Motor Controller & Encoder</h2>
          <span class="tag">/dev/ttyUSB0 &bull; 9600 Baud</span>
        </div>
        <div class="robot-grid">
          <div class="rpm-display">
            <div style="font-size: 11px; color: var(--muted); text-transform: uppercase;">WHEEL SPEED</div>
            <div id="val-rpm" class="rpm-num">0.00</div>
            <div style="font-size: 11px; color: var(--muted); font-weight: 600;">RPM</div>
            <div style="margin-top: 6px; font-size: 12px; color: var(--blue); font-family: monospace;">
              <span id="val-linear">0.00 km/h</span>
            </div>
          </div>

          <div class="dpad-container">
            <div style="font-size: 11px; color: var(--muted); font-weight: 600;">DRIVE CONTROLS (Arrows / Click)</div>
            <div class="dpad-row">
              <button class="btn-ctrl" id="btn-F" onclick="sendCmd('F')">&#x2B06; FWD</button>
            </div>
            <div class="dpad-row">
              <button class="btn-ctrl" id="btn-L" onclick="sendCmd('L')">&#x2B05; LFT</button>
              <button class="btn-ctrl btn-stop" id="btn-S" onclick="sendCmd('S')">&#x23F9; STOP</button>
              <button class="btn-ctrl" id="btn-R" onclick="sendCmd('R')">&#x27A1; RGT</button>
            </div>
            <div class="dpad-row">
              <button class="btn-ctrl" id="btn-B" onclick="sendCmd('B')">&#x2B07; REV</button>
            </div>
          </div>

          <div class="robot-info">
            <div class="info-row">
              <span style="color: var(--muted);">Command</span>
              <span id="txt-last-cmd" class="val" style="color: var(--yellow);">STOP (S)</span>
            </div>
            <div class="info-row">
              <span style="color: var(--muted);">Bluetooth</span>
              <span class="val" style="font-size: 10px;">HC-05 Active</span>
            </div>
            <div class="info-row">
              <span style="color: var(--muted);">Serial</span>
              <span id="txt-raw-serial" class="val" style="font-size: 10px; color: var(--blue);">RPM:0.00</span>
            </div>
          </div>
        </div>

        <div style="margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--card-border); font-size: 12px; color: var(--muted);">
          Keyboard: <kbd style="background:rgba(255,255,255,0.1); padding:2px 5px; border-radius:3px;">&uarr;</kbd> Forward &bull;
          <kbd style="background:rgba(255,255,255,0.1); padding:2px 5px; border-radius:3px;">&darr;</kbd> Backward &bull;
          <kbd style="background:rgba(255,255,255,0.1); padding:2px 5px; border-radius:3px;">&larr;</kbd> Left &bull;
          <kbd style="background:rgba(255,255,255,0.1); padding:2px 5px; border-radius:3px;">&rarr;</kbd> Right &bull;
          <kbd style="background:rgba(255,255,255,0.1); padding:2px 5px; border-radius:3px;">Space</kbd> Stop
        </div>
      </div>
    </div>

    <!-- BOTTOM ROW: IMU & GPS SENSORS -->
    <div class="bottom-split">
      <!-- IMU SENSOR -->
      <div class="card">
        <div class="card-head">
          <h2>Grove IMU 3-Axis Accelerometer (MMA7660)</h2>
          <span class="tag">Port: I2C-1 &bull; 0x4c</span>
        </div>
        <div class="imu-grid">
          <div>
            <div class="viewport-3d">
              <div id="cube" class="cube">
                <div class="face front">GrovePi</div>
                <div class="face back">Back</div>
                <div class="face right">Right</div>
                <div class="face left">Left</div>
                <div class="face top">Z+</div>
                <div class="face bottom">Z-</div>
              </div>
            </div>
            <div style="text-align: center; margin-top: 4px; font-size: 10px; color: var(--muted);">3D Orientation</div>
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
              <div class="lbl">TILT STATUS</div>
              <div id="val-tilt" style="font-family: monospace; font-size: 13px; font-weight: 700; color: #fff;">0x00</div>
            </div>
          </div>

          <div class="gauges">
            <div class="gauge">
              <div class="gauge-top"><span>X</span><span id="txt-ax" class="val">+0.00 g</span></div>
              <div class="gauge-bar-bg"><div id="bar-ax" class="gauge-bar" style="width: 50%;"></div></div>
            </div>
            <div class="gauge">
              <div class="gauge-top"><span>Y</span><span id="txt-ay" class="val">+0.00 g</span></div>
              <div class="gauge-bar-bg"><div id="bar-ay" class="gauge-bar" style="width: 50%;"></div></div>
            </div>
            <div class="gauge">
              <div class="gauge-top"><span>Z</span><span id="txt-az" class="val">+0.00 g</span></div>
              <div class="gauge-bar-bg"><div id="bar-az" class="gauge-bar" style="width: 50%;"></div></div>
            </div>
          </div>
        </div>
      </div>

      <!-- GPS SENSOR -->
      <div class="card">
        <div class="card-head">
          <h2>7SEMI U-blox NEO-M9N GNSS Receiver</h2>
          <span class="tag">Port: I2C-2 &bull; 0x42</span>
        </div>
        <div class="gps-grid">
          <div>
            <div class="gps-stats">
              <div class="stat-card">
                <div class="lbl">Fix</div>
                <div id="gps-fix" class="val" style="color: var(--yellow);">Searching</div>
              </div>
              <div class="stat-card">
                <div class="lbl">Sats</div>
                <div id="gps-sats" class="val">0</div>
              </div>
              <div class="stat-card">
                <div class="lbl">HDOP</div>
                <div id="gps-hdop" class="val">99.9</div>
              </div>
              <div class="stat-card">
                <div class="lbl">Latitude</div>
                <div id="gps-lat" class="val">--.----°</div>
              </div>
              <div class="stat-card">
                <div class="lbl">Longitude</div>
                <div id="gps-lon" class="val">--.----°</div>
              </div>
              <div class="stat-card">
                <div class="lbl">Speed</div>
                <div id="gps-speed" class="val">0.0 km/h</div>
              </div>
            </div>
            <div class="nmea-feed" id="nmea-feed">NMEA Stream Listening...</div>
          </div>

          <div class="radar-container">
            <svg class="radar-svg" viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="45" stroke="rgba(56, 189, 248, 0.2)" stroke-width="1.5" fill="none"/>
              <circle cx="50" cy="50" r="30" stroke="rgba(56, 189, 248, 0.3)" stroke-width="1" fill="none"/>
              <circle cx="50" cy="50" r="15" stroke="rgba(56, 189, 248, 0.4)" stroke-width="1" fill="none"/>
              <line x1="5" y1="50" x2="95" y2="50" stroke="rgba(56, 189, 248, 0.2)" stroke-width="1"/>
              <line x1="50" y1="5" x2="50" y2="95" stroke="rgba(56, 189, 248, 0.2)" stroke-width="1"/>
              <text x="50" y="10" font-size="6" fill="#38bdf8" text-anchor="middle" font-weight="bold">N</text>
              <circle id="radar-target" cx="50" cy="50" r="3.5" fill="#f59e0b">
                <animate attributeName="opacity" values="1;0.4;1" dur="1.5s" repeatCount="indefinite"/>
              </circle>
            </svg>
            <div id="radar-caption" style="margin-top: 3px; font-size: 10px; color: var(--muted);">Acquiring Lock...</div>
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

        // 1. Ultrasonic Sensor
        if (d.ultrasonic && d.ultrasonic.connected) {
          const dist = d.ultrasonic.distance_cm;
          document.getElementById('sonic-cm').innerText = dist;
          document.getElementById('cam-hud-dist').innerText = 'SONIC: ' + dist + ' cm';
          
          const bar = document.getElementById('sonic-bar');
          const badge = document.getElementById('sonic-badge');
          
          let pct = Math.min(100, Math.max(5, (dist / 120) * 100));
          bar.style.width = pct + '%';

          if (d.ultrasonic.alert_level === 'red') {
            bar.style.background = 'var(--red)';
            badge.style.background = 'rgba(239, 68, 68, 0.25)';
            badge.style.color = 'var(--red)';
            badge.innerText = d.ultrasonic.warning;
          } else if (d.ultrasonic.alert_level === 'yellow') {
            bar.style.background = 'var(--yellow)';
            badge.style.background = 'rgba(245, 158, 11, 0.25)';
            badge.style.color = 'var(--yellow)';
            badge.innerText = d.ultrasonic.warning;
          } else {
            bar.style.background = 'var(--green)';
            badge.style.background = 'rgba(34, 197, 94, 0.25)';
            badge.style.color = 'var(--green)';
            badge.innerText = d.ultrasonic.warning;
          }
        }

        // 2. Arduino Telemetry
        if (d.arduino && d.arduino.connected) {
          document.getElementById('badge-arduino').innerHTML = '<div class="dot green"></div> Arduino: Connected';
          document.getElementById('val-rpm').innerText = d.arduino.rpm.toFixed(2);
          document.getElementById('val-linear').innerText = d.arduino.speed_kmh.toFixed(2) + ' km/h';
          document.getElementById('txt-raw-serial').innerText = d.arduino.last_line || 'RPM:0.00';

          const cmdMap = { 'F': 'FORWARD (F)', 'B': 'BACKWARD (B)', 'L': 'LEFT (L)', 'R': 'RIGHT (R)', 'S': 'STOP (S)' };
          document.getElementById('txt-last-cmd').innerText = cmdMap[d.arduino.last_cmd] || d.arduino.last_cmd;
        }

        // 3. IMU Telemetry
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
        }

        // 4. GPS Telemetry
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
              document.getElementById('gps-lat').innerText = d.gps.latitude.toFixed(4) + '°';
              document.getElementById('gps-lon').innerText = d.gps.longitude.toFixed(4) + '°';
              radarCap.innerText = `${d.gps.latitude.toFixed(3)}°, ${d.gps.longitude.toFixed(3)}°`;
            }
          } else {
            document.getElementById('badge-gps').innerHTML = '<div class="dot yellow"></div> GPS: Acquiring';
            fixTxt.innerText = d.gps.fix_quality;
            fixTxt.style.color = 'var(--yellow)';
            target.setAttribute('fill', '#f59e0b');
            radarCap.innerText = 'Acquiring Satellites...';
          }

          document.getElementById('gps-sats').innerText = d.gps.satellites;
          document.getElementById('gps-speed').innerText = d.gps.speed_kmh.toFixed(1) + ' km/h';
          document.getElementById('gps-hdop').innerText = d.gps.hdop.toFixed(1);

          if (d.gps.raw_sentences && d.gps.raw_sentences.length > 0) {
            document.getElementById('nmea-feed').innerHTML = d.gps.raw_sentences.slice(-1).join('');
          }
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
    html_file = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(html_file):
        with open(html_file, "r", encoding="utf-8") as f:
            return f.read()
    return render_template_string(HTML_PAGE)

@app.route("/api/telemetry")
def get_telemetry():
    telemetry["night_vision"] = nv_isp.get_config()
    return jsonify(telemetry)

@app.route("/api/camera/night_vision", methods=["GET", "POST"])
def night_vision_api():
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form.to_dict()
        if data:
            nv_isp.update_config(data)
            telemetry["night_vision"] = nv_isp.get_config()
            return jsonify({"status": "ok", "config": nv_isp.get_config()})
    return jsonify(nv_isp.get_config())

@app.route("/video_feed")
def video_feed():
    def generate():
        while True:
            with camera_lock:
                frame = camera_frame
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.04)
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/api/motor", methods=["GET", "POST"])
def motor_control():
    cmd = request.args.get("cmd")
    if not cmd and request.is_json:
        cmd = request.json.get("cmd")
    if cmd:
        sent = send_motor_command(cmd)
        return jsonify({"status": "ok", "cmd": cmd, "sent": sent})
    return jsonify({"status": "error", "message": "No command provided"}), 400

_tile_cache = {}

@app.route("/map_tile/<layer>/<int:z>/<int:x>/<int:y>.png")
def map_tile_proxy(layer, z, x, y):
    cache_key = (layer, z, x, y)
    if cache_key in _tile_cache:
        return Response(_tile_cache[cache_key], mimetype='image/png', headers={'Cache-Control': 'public, max-age=86400'})

    lyrs = 'y' if layer == 'sat' else 'm'
    google_url = f"https://mt1.google.com/vt/lyrs={lyrs}&x={x}&y={y}&z={z}"
    try:
        req = urllib.request.Request(google_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = resp.read()
            if len(_tile_cache) > 600:
                _tile_cache.clear()
            _tile_cache[cache_key] = data
            return Response(data, mimetype='image/png', headers={'Cache-Control': 'public, max-age=86400'})
    except Exception as e:
        try:
            osm_url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            req = urllib.request.Request(osm_url, headers={'User-Agent': 'MineVisionX/1.0'})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = resp.read()
                return Response(data, mimetype='image/png', headers={'Cache-Control': 'public, max-age=86400'})
        except Exception:
            return Response(status=404)

if __name__ == "__main__":
    init_bus()
    t_cam = threading.Thread(target=camera_worker, daemon=True)
    t_sonic = threading.Thread(target=ultrasonic_worker, daemon=True)
    t_imu = threading.Thread(target=imu_worker, daemon=True)
    t_gps = threading.Thread(target=gps_worker, daemon=True)
    t_ard = threading.Thread(target=arduino_worker, daemon=True)
    t_net = threading.Thread(target=network_location_worker, daemon=True)
    
    t_cam.start()
    t_sonic.start()
    t_imu.start()
    t_gps.start()
    t_ard.start()
    t_net.start()
    
    print("Starting Autonomous Robot Telemetry Server on port 5000...")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
