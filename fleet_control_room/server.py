#!/usr/bin/env python3
"""
Mine Vision-X | Central Fleet Control Room & Security Surveillance Gateway
Central Command Server: Ingests, transmutes, and monitors real-time HEMM vehicle
telemetry away from the open-pit mine site over LoRa Mesh / 4G APN.
"""

import os
import sys
import time
import math
import json
import io
import threading
from datetime import datetime, timezone
import urllib.request
import urllib.error
from flask import Flask, jsonify, request, Response, render_template, send_from_directory
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__, static_folder="static", template_folder="templates")

# ================= CONFIGURATION & CONSTANTS =================
PORT = 8080
DEFAULT_VEHICLE_BRIDGE_URL = "http://127.0.0.1:5000"

# Open-cast mine center coordinate (Dhanbad Coalfields / Jharia Basin reference)
MINE_CENTER_LAT = 23.7957
MINE_CENTER_LON = 86.4304

# ================= FLEET TELEMETRY STATE =================
# Multi-vehicle state database monitored by Central Office
fleet_lock = threading.Lock()

fleet_vehicles = {
    "HEMM-101": {
        "id": "HEMM-101",
        "name": "Haul Truck 101 (Mine Vision-X)",
        "model": "CAT 777G Off-Highway Truck",
        "payload_ton": 98.4,
        "operator": "Rajesh Kumar (Badge #409)",
        "shift": "Shift A (Morning)",
        "status": "ACTIVE_HAULING",
        "connection": {
            "type": "LORA_MESH_4G",
            "online": True,
            "is_physical_bridge": False,
            "bridge_url": DEFAULT_VEHICLE_BRIDGE_URL,
            "rssi_dbm": -76,
            "snr_db": 9.4,
            "pdr_pct": 99.8,
            "latency_ms": 38,
            "hops": 1,
            "gateway": "GW-TOWER-NORTH"
        },
        "gps": {
            "fix": True,
            "fix_quality": "GNSS Fix (Active)",
            "latitude": 23.79540,
            "longitude": 86.43080,
            "altitude_m": 242.0,
            "heading_deg": 48.0,
            "speed_kmh": 22.4,
            "satellites": 16,
            "hdop": 0.85
        },
        "imu": {
            "pitch_deg": 3.8,
            "roll_deg": -1.4,
            "ax": 0.04,
            "ay": 0.08,
            "az": 0.98,
            "rollover_risk": "SAFE",
            "tilt_raw": "0x05"
        },
        "powertrain": {
            "rpm": 1850.0,
            "speed_kmh": 22.4,
            "gear": "D3",
            "motor_load_pct": 68,
            "engine_temp_c": 86.5,
            "fuel_pct": 74.0,
            "last_cmd": "F"
        },
        "radar": {
            "connected": True,
            "frequency": "77 GHz mmWave",
            "obstacle_detected": True,
            "distance_m": 34.2,
            "rel_speed_kmh": -2.1,
            "alert_level": "CAUTION",
            "warning": "SLOWING VEHICLE AHEAD",
            "targets": [
                {"id": 1, "type": "HAUL_TRUCK", "dist_m": 34.2, "angle_deg": 2.5, "rel_speed_kmh": -2.1}
            ]
        },
        "ultrasonic": {
            "connected": True,
            "port": "D2",
            "distance_cm": 68.0,
            "warning": "CLEAR",
            "alert_level": "green"
        },
        "ai_vision": {
            "connected": True,
            "fps": 24.8,
            "fog_safe_mode": True,
            "thermal_mode": False,
            "detections": [
                {"label": "Dump Truck", "confidence": 0.96, "bbox": [260, 160, 390, 290]}
            ]
        },
        "safety": {
            "estop_active": False,
            "horn_sounding": False,
            "cabin_msg": "CONVOY SPEED 25 KM/H ENFORCED",
            "fog_protocol": False,
            "last_incident": None
        }
    },
    "HEMM-102": {
        "id": "HEMM-102",
        "name": "Haul Truck 102",
        "model": "Komatsu HD785-7",
        "payload_ton": 91.0,
        "operator": "Sunil Verma (Badge #312)",
        "shift": "Shift A (Morning)",
        "status": "UNLOADING_CRUSHER",
        "connection": {
            "type": "LORA_MESH",
            "online": True,
            "is_physical_bridge": False,
            "rssi_dbm": -81,
            "snr_db": 8.1,
            "pdr_pct": 98.9,
            "latency_ms": 44,
            "hops": 2,
            "gateway": "GW-TOWER-SOUTH"
        },
        "gps": {
            "fix": True,
            "fix_quality": "GNSS Fix (Active)",
            "latitude": 23.79780,
            "longitude": 86.43450,
            "altitude_m": 298.0,
            "heading_deg": 135.0,
            "speed_kmh": 0.0,
            "satellites": 14,
            "hdop": 0.95
        },
        "imu": {
            "pitch_deg": 1.2,
            "roll_deg": 0.4,
            "ax": 0.0,
            "ay": 0.0,
            "az": 1.0,
            "rollover_risk": "SAFE",
            "tilt_raw": "0x01"
        },
        "powertrain": {
            "rpm": 650.0,
            "speed_kmh": 0.0,
            "gear": "N",
            "motor_load_pct": 22,
            "engine_temp_c": 91.2,
            "fuel_pct": 58.5,
            "last_cmd": "S"
        },
        "radar": {
            "connected": True,
            "frequency": "77 GHz mmWave",
            "obstacle_detected": False,
            "distance_m": 85.0,
            "rel_speed_kmh": 0.0,
            "alert_level": "CLEAR",
            "warning": "CLEAR",
            "targets": []
        },
        "ultrasonic": {
            "connected": True,
            "port": "D2",
            "distance_cm": 250.0,
            "warning": "CLEAR",
            "alert_level": "green"
        },
        "ai_vision": {
            "connected": True,
            "fps": 25.0,
            "fog_safe_mode": False,
            "thermal_mode": False,
            "detections": [
                {"label": "Crusher Hopper", "confidence": 0.94, "bbox": [200, 140, 440, 320]}
            ]
        },
        "safety": {
            "estop_active": False,
            "horn_sounding": False,
            "cabin_msg": "PROCEED TO HOPPER #2",
            "fog_protocol": False,
            "last_incident": None
        }
    },
    "HEMM-204": {
        "id": "HEMM-204",
        "name": "Excavator 204",
        "model": "CAT 6020B Hydraulic Shovel",
        "payload_ton": 224.0,
        "operator": "Manoj Singh (Badge #118)",
        "shift": "Shift A (Morning)",
        "status": "DIGGING_BENCH_4",
        "connection": {
            "type": "LORA_MESH",
            "online": True,
            "is_physical_bridge": False,
            "rssi_dbm": -88,
            "snr_db": 6.8,
            "pdr_pct": 97.4,
            "latency_ms": 52,
            "hops": 2,
            "gateway": "GW-TOWER-PIT"
        },
        "gps": {
            "fix": True,
            "fix_quality": "GNSS Fix (Active)",
            "latitude": 23.79320,
            "longitude": 86.42750,
            "altitude_m": 182.0,
            "heading_deg": 270.0,
            "speed_kmh": 0.0,
            "satellites": 12,
            "hdop": 1.10
        },
        "imu": {
            "pitch_deg": -5.2,
            "roll_deg": 3.6,
            "ax": -0.08,
            "ay": 0.05,
            "az": 0.96,
            "rollover_risk": "CAUTION_SLOPE",
            "tilt_raw": "0x07"
        },
        "powertrain": {
            "rpm": 1950.0,
            "speed_kmh": 0.0,
            "gear": "P",
            "motor_load_pct": 89,
            "engine_temp_c": 94.0,
            "fuel_pct": 81.0,
            "last_cmd": "S"
        },
        "radar": {
            "connected": True,
            "frequency": "77 GHz mmWave",
            "obstacle_detected": True,
            "distance_m": 12.5,
            "rel_speed_kmh": 0.0,
            "alert_level": "CAUTION",
            "warning": "PIT WALL BENCH FACE 12.5M",
            "targets": [
                {"id": 1, "type": "PIT_WALL", "dist_m": 12.5, "angle_deg": -8.0, "rel_speed_kmh": 0.0}
            ]
        },
        "ultrasonic": {
            "connected": True,
            "port": "D2",
            "distance_cm": 180.0,
            "warning": "CAUTION",
            "alert_level": "yellow"
        },
        "ai_vision": {
            "connected": True,
            "fps": 20.0,
            "fog_safe_mode": True,
            "thermal_mode": True,
            "detections": [
                {"label": "Pit Wall", "confidence": 0.98, "bbox": [100, 100, 540, 360]}
            ]
        },
        "safety": {
            "estop_active": False,
            "horn_sounding": False,
            "cabin_msg": "BENCH 4 DIG CYCLE OK",
            "fog_protocol": False,
            "last_incident": None
        }
    },
    "HEMM-305": {
        "id": "HEMM-305",
        "name": "Wheel Loader 305",
        "model": "Komatsu WA600-8",
        "payload_ton": 54.0,
        "operator": "Amit Das (Badge #215)",
        "shift": "Shift A (Morning)",
        "status": "STOCKPILE_LOADING",
        "connection": {
            "type": "LORA_MESH",
            "online": True,
            "is_physical_bridge": False,
            "rssi_dbm": -72,
            "snr_db": 11.2,
            "pdr_pct": 100.0,
            "latency_ms": 32,
            "hops": 1,
            "gateway": "GW-TOWER-NORTH"
        },
        "gps": {
            "fix": True,
            "fix_quality": "GNSS Fix (Active)",
            "latitude": 23.79810,
            "longitude": 86.42890,
            "altitude_m": 275.0,
            "heading_deg": 190.0,
            "speed_kmh": 14.8,
            "satellites": 17,
            "hdop": 0.80
        },
        "imu": {
            "pitch_deg": 2.1,
            "roll_deg": -0.8,
            "ax": 0.02,
            "ay": -0.01,
            "az": 1.0,
            "rollover_risk": "SAFE",
            "tilt_raw": "0x02"
        },
        "powertrain": {
            "rpm": 1620.0,
            "speed_kmh": 14.8,
            "gear": "D2",
            "motor_load_pct": 54,
            "engine_temp_c": 82.0,
            "fuel_pct": 66.0,
            "last_cmd": "F"
        },
        "radar": {
            "connected": True,
            "frequency": "77 GHz mmWave",
            "obstacle_detected": False,
            "distance_m": 60.0,
            "rel_speed_kmh": 0.0,
            "alert_level": "CLEAR",
            "warning": "CLEAR",
            "targets": []
        },
        "ultrasonic": {
            "connected": True,
            "port": "D2",
            "distance_cm": 310.0,
            "warning": "CLEAR",
            "alert_level": "green"
        },
        "ai_vision": {
            "connected": True,
            "fps": 25.0,
            "fog_safe_mode": False,
            "thermal_mode": False,
            "detections": []
        },
        "safety": {
            "estop_active": False,
            "horn_sounding": False,
            "cabin_msg": "STOCKPILE YARD CLEAR",
            "fog_protocol": False,
            "last_incident": None
        }
    },
    "HEMM-408": {
        "id": "HEMM-408",
        "name": "Bulldozer 408",
        "model": "CAT D11T Track-Type Tractor",
        "payload_ton": 104.0,
        "operator": "Ramesh Yadav (Badge #504)",
        "shift": "Shift A (Morning)",
        "status": "ROAD_GRADING",
        "connection": {
            "type": "LORA_MESH",
            "online": True,
            "is_physical_bridge": False,
            "rssi_dbm": -84,
            "snr_db": 7.4,
            "pdr_pct": 98.2,
            "latency_ms": 48,
            "hops": 2,
            "gateway": "GW-TOWER-SOUTH"
        },
        "gps": {
            "fix": True,
            "fix_quality": "GNSS Fix (Active)",
            "latitude": 23.79410,
            "longitude": 86.43260,
            "altitude_m": 220.0,
            "heading_deg": 310.0,
            "speed_kmh": 8.2,
            "satellites": 15,
            "hdop": 0.90
        },
        "imu": {
            "pitch_deg": 6.8,
            "roll_deg": -4.2,
            "ax": 0.09,
            "ay": -0.06,
            "az": 0.92,
            "rollover_risk": "CAUTION_SLOPE",
            "tilt_raw": "0x09"
        },
        "powertrain": {
            "rpm": 1780.0,
            "speed_kmh": 8.2,
            "gear": "D1",
            "motor_load_pct": 78,
            "engine_temp_c": 89.0,
            "fuel_pct": 49.0,
            "last_cmd": "F"
        },
        "radar": {
            "connected": True,
            "frequency": "77 GHz mmWave",
            "obstacle_detected": True,
            "distance_m": 18.0,
            "rel_speed_kmh": 0.0,
            "alert_level": "CAUTION",
            "warning": "BOULDER BERM DETECTED",
            "targets": [
                {"id": 1, "type": "BERM", "dist_m": 18.0, "angle_deg": 0.0, "rel_speed_kmh": 0.0}
            ]
        },
        "ultrasonic": {
            "connected": True,
            "port": "D2",
            "distance_cm": 95.0,
            "warning": "CAUTION",
            "alert_level": "yellow"
        },
        "ai_vision": {
            "connected": True,
            "fps": 22.0,
            "fog_safe_mode": True,
            "thermal_mode": False,
            "detections": [
                {"label": "Berm Boulder", "confidence": 0.92, "bbox": [180, 220, 360, 310]}
            ]
        },
        "safety": {
            "estop_active": False,
            "horn_sounding": False,
            "cabin_msg": "ROAD REPAIR IN PROGRESS",
            "fog_protocol": False,
            "last_incident": None
        }
    },
    "LMV-012": {
        "id": "LMV-012",
        "name": "Mine Inspection 4x4",
        "model": "Toyota Hilux Heavy Duty Mine Patrol",
        "payload_ton": 3.2,
        "operator": "Security Officer Pradeep (Badge #02)",
        "shift": "Shift A (Morning)",
        "status": "SECURITY_PATROL",
        "connection": {
            "type": "4G_LTE_LORA",
            "online": True,
            "is_physical_bridge": False,
            "rssi_dbm": -68,
            "snr_db": 13.5,
            "pdr_pct": 100.0,
            "latency_ms": 22,
            "hops": 1,
            "gateway": "GW-TOWER-HQ"
        },
        "gps": {
            "fix": True,
            "fix_quality": "GNSS Fix (Active)",
            "latitude": 23.79630,
            "longitude": 86.42980,
            "altitude_m": 255.0,
            "heading_deg": 65.0,
            "speed_kmh": 38.5,
            "satellites": 19,
            "hdop": 0.70
        },
        "imu": {
            "pitch_deg": 0.8,
            "roll_deg": 0.2,
            "ax": 0.01,
            "ay": 0.01,
            "az": 1.0,
            "rollover_risk": "SAFE",
            "tilt_raw": "0x00"
        },
        "powertrain": {
            "rpm": 2200.0,
            "speed_kmh": 38.5,
            "gear": "D4",
            "motor_load_pct": 45,
            "engine_temp_c": 84.0,
            "fuel_pct": 89.0,
            "last_cmd": "F"
        },
        "radar": {
            "connected": True,
            "frequency": "77 GHz mmWave",
            "obstacle_detected": False,
            "distance_m": 120.0,
            "rel_speed_kmh": 0.0,
            "alert_level": "CLEAR",
            "warning": "CLEAR",
            "targets": []
        },
        "ultrasonic": {
            "connected": True,
            "port": "D2",
            "distance_cm": 400.0,
            "warning": "CLEAR",
            "alert_level": "green"
        },
        "ai_vision": {
            "connected": True,
            "fps": 30.0,
            "fog_safe_mode": False,
            "thermal_mode": True,
            "detections": [
                {"label": "Ground Personnel", "confidence": 0.95, "bbox": [420, 200, 450, 280]}
            ]
        },
        "safety": {
            "estop_active": False,
            "horn_sounding": False,
            "cabin_msg": "SECTOR NORTH PATROL CLEAR",
            "fog_protocol": False,
            "last_incident": None
        }
    }
}

# ================= SECURITY INCIDENT AUDIT LOG =================
incident_log = [
    {
        "id": "INC-8091",
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "vehicle_id": "HEMM-101",
        "severity": "WARNING",
        "type": "PROXIMITY_HAZARD",
        "details": "77 GHz Radar obstacle distance dropped to 34.2m in Fog Zone B",
        "acknowledged": True,
        "operator": "Rajesh Kumar"
    },
    {
        "id": "INC-8089",
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "vehicle_id": "HEMM-204",
        "severity": "INFO",
        "type": "SLOPE_TILT_MONITOR",
        "details": "Bench #4 incline reached 5.2 deg pitch; rollover threshold verified safe",
        "acknowledged": True,
        "operator": "Manoj Singh"
    },
    {
        "id": "INC-8084",
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "vehicle_id": "LMV-012",
        "severity": "INFO",
        "type": "PERSON_DETECTED_THERMAL",
        "details": "Thermal vision detected ground personnel wearing high-vis gear near Haul Road 3",
        "acknowledged": True,
        "operator": "Pradeep Kumar"
    }
]

# LoRa Mesh Gateway Base Stations overlooking the mine
network_gateways = {
    "GW-TOWER-HQ": {"name": "Central Office Command Tower", "status": "ONLINE", "freq": "868.1 MHz", "nodes_linked": 6, "snr_avg": 12.4},
    "GW-TOWER-NORTH": {"name": "North Pit Rim Repeater #1", "status": "ONLINE", "freq": "868.3 MHz", "nodes_linked": 4, "snr_avg": 9.8},
    "GW-TOWER-SOUTH": {"name": "South Crusher Overlook #2", "status": "ONLINE", "freq": "868.5 MHz", "nodes_linked": 3, "snr_avg": 8.6},
    "GW-TOWER-PIT": {"name": "Pit Floor Bench Repeater #3", "status": "ONLINE", "freq": "868.1 MHz", "nodes_linked": 2, "snr_avg": 7.2}
}

global_fog_mode = False

# ================= VIDEO FRAME BUFFERS =================
video_frames = {}
video_locks = {vid: threading.Lock() for vid in fleet_vehicles}

# ================= BACKGROUND WORKER: PHYSICAL VEHICLE BRIDGE =================
# If a real vehicle edge server is running (e.g. at http://127.0.0.1:5000 or on local Pi),
# this worker automatically transmutes its data into HEMM-101 in real-time!
physical_bridge_url = DEFAULT_VEHICLE_BRIDGE_URL

def vehicle_bridge_worker():
    global physical_bridge_url
    while True:
        try:
            url = f"{physical_bridge_url}/api/telemetry"
            req = urllib.request.Request(url, headers={"User-Agent": "MineVisionX-ControlRoom/1.0"})
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                if resp.status == 200:
                    raw_data = resp.read().decode("utf-8")
                    data = json.loads(raw_data)
                    
                    with fleet_lock:
                        v = fleet_vehicles["HEMM-101"]
                        v["connection"]["is_physical_bridge"] = True
                        v["connection"]["bridge_url"] = physical_bridge_url
                        v["connection"]["online"] = True
                        
                        # Ingest Ultrasonic
                        if "ultrasonic" in data:
                            u = data["ultrasonic"]
                            v["ultrasonic"]["connected"] = u.get("connected", True)
                            v["ultrasonic"]["distance_cm"] = u.get("distance_cm", v["ultrasonic"]["distance_cm"])
                            v["ultrasonic"]["warning"] = u.get("warning", v["ultrasonic"]["warning"])
                            v["ultrasonic"]["alert_level"] = u.get("alert_level", v["ultrasonic"]["alert_level"])
                            # Sync with radar distance
                            v["radar"]["distance_m"] = round(v["ultrasonic"]["distance_cm"] / 100.0 * 25.0, 1)
                            if v["ultrasonic"]["distance_cm"] < 30:
                                v["radar"]["alert_level"] = "CRITICAL"
                                v["radar"]["warning"] = "OBSTACLE IMMINENT!"
                            elif v["ultrasonic"]["distance_cm"] < 60:
                                v["radar"]["alert_level"] = "CAUTION"
                                v["radar"]["warning"] = "SLOWING VEHICLE AHEAD"
                            else:
                                v["radar"]["alert_level"] = "CLEAR"
                                v["radar"]["warning"] = "CLEAR"

                        # Ingest IMU
                        if "imu" in data:
                            imu = data["imu"]
                            v["imu"]["pitch_deg"] = imu.get("pitch", v["imu"]["pitch_deg"])
                            v["imu"]["roll_deg"] = imu.get("roll", v["imu"]["roll_deg"])
                            v["imu"]["ax"] = imu.get("ax", v["imu"]["ax"])
                            v["imu"]["ay"] = imu.get("ay", v["imu"]["ay"])
                            v["imu"]["az"] = imu.get("az", v["imu"]["az"])
                            v["imu"]["tilt_raw"] = str(imu.get("tilt_raw", v["imu"]["tilt_raw"]))
                            # Rollover risk evaluation
                            if abs(v["imu"]["roll_deg"]) > 22 or abs(v["imu"]["pitch_deg"]) > 20:
                                v["imu"]["rollover_risk"] = "CRITICAL_ROLLOVER"
                            elif abs(v["imu"]["roll_deg"]) > 12 or abs(v["imu"]["pitch_deg"]) > 12:
                                v["imu"]["rollover_risk"] = "CAUTION_SLOPE"
                            else:
                                v["imu"]["rollover_risk"] = "SAFE"

                        # Ingest Arduino / Powertrain
                        if "arduino" in data:
                            ard = data["arduino"]
                            v["powertrain"]["rpm"] = ard.get("rpm", v["powertrain"]["rpm"])
                            v["powertrain"]["speed_kmh"] = ard.get("speed_kmh", v["powertrain"]["speed_kmh"])
                            v["gps"]["speed_kmh"] = v["powertrain"]["speed_kmh"]
                            v["powertrain"]["last_cmd"] = ard.get("last_cmd", v["powertrain"]["last_cmd"])

                        # Ingest GPS
                        if "gps" in data:
                            g = data["gps"]
                            if g.get("latitude") and g.get("longitude"):
                                v["gps"]["latitude"] = g["latitude"]
                                v["gps"]["longitude"] = g["longitude"]
                            v["gps"]["fix"] = g.get("fix", True)
                            v["gps"]["fix_quality"] = g.get("fix_quality", "GNSS Fix (Active)")
                            v["gps"]["satellites"] = g.get("satellites", v["gps"]["satellites"])
                            v["gps"]["hdop"] = g.get("hdop", v["gps"]["hdop"])

        except Exception:
            # Physical bridge unavailable; fallback to simulated mining loop
            with fleet_lock:
                fleet_vehicles["HEMM-101"]["connection"]["is_physical_bridge"] = False
        
        time.sleep(0.1) # 10 Hz ingestion loop

# ================= BACKGROUND WORKER: MINE FLEET MOTION SIMULATOR =================
# Accurately animates all vehicles moving on realistic open-pit haul roads
def fleet_simulator_worker():
    step = 0
    while True:
        step += 1
        with fleet_lock:
            # Haul Road Waypoints (Pit Rim -> Haul Road B -> Crusher -> Pit Floor)
            # Cycle HEMM-101 if not driven physically
            v101 = fleet_vehicles["HEMM-101"]
            if not v101["connection"]["is_physical_bridge"]:
                t = step * 0.05
                # Orbit around Dhanbad open pit haul road
                r_lat = 0.0035 * math.cos(t * 0.25)
                r_lon = 0.0045 * math.sin(t * 0.25)
                v101["gps"]["latitude"] = round(MINE_CENTER_LAT + r_lat, 6)
                v101["gps"]["longitude"] = round(MINE_CENTER_LON + r_lon, 6)
                v101["gps"]["heading_deg"] = round((math.degrees(t * 0.25 + math.pi/2)) % 360, 1)
                
                # Speed variations
                base_spd = 22.0 + 4.0 * math.sin(t * 0.8)
                v101["powertrain"]["speed_kmh"] = round(max(0.0, base_spd), 1)
                v101["gps"]["speed_kmh"] = v101["powertrain"]["speed_kmh"]
                v101["powertrain"]["rpm"] = round(v101["powertrain"]["speed_kmh"] / 0.01224, 1)
                
                # IMU vibration on rock surface
                v101["imu"]["pitch_deg"] = round(3.5 + 1.8 * math.sin(t * 0.5) + (math.sin(t * 6) * 0.4), 2)
                v101["imu"]["roll_deg"] = round(-1.2 + 2.4 * math.cos(t * 0.3) + (math.cos(t * 7) * 0.3), 2)
                
                # Radar obstacle target distance changes as truck drives
                dist_cycle = 35.0 + 20.0 * math.sin(t * 0.2)
                v101["radar"]["distance_m"] = round(max(14.0, dist_cycle), 1)
                v101["ultrasonic"]["distance_cm"] = round(v101["radar"]["distance_m"] * 2.5, 1)
                
                if v101["radar"]["distance_m"] < 18:
                    v101["radar"]["alert_level"] = "CRITICAL"
                    v101["radar"]["warning"] = "OBSTACLE CLOSE!"
                    v101["ultrasonic"]["alert_level"] = "red"
                elif v101["radar"]["distance_m"] < 38:
                    v101["radar"]["alert_level"] = "CAUTION"
                    v101["radar"]["warning"] = "SLOWING VEHICLE AHEAD"
                    v101["ultrasonic"]["alert_level"] = "yellow"
                else:
                    v101["radar"]["alert_level"] = "CLEAR"
                    v101["radar"]["warning"] = "CLEAR"
                    v101["ultrasonic"]["alert_level"] = "green"

            # Animate other fleet units
            # HEMM-305 (Wheel loader shuttling at stockpile)
            t_305 = step * 0.04
            fleet_vehicles["HEMM-305"]["gps"]["latitude"] = round(MINE_CENTER_LAT + 0.0024 + 0.0006 * math.sin(t_305), 6)
            fleet_vehicles["HEMM-305"]["gps"]["longitude"] = round(MINE_CENTER_LON - 0.0015 + 0.0008 * math.cos(t_305), 6)
            fleet_vehicles["HEMM-305"]["gps"]["heading_deg"] = round((math.degrees(t_305)) % 360, 1)

            # LMV-012 (Patrol 4x4 patrolling outer perimeter)
            t_012 = step * 0.08
            fleet_vehicles["LMV-012"]["gps"]["latitude"] = round(MINE_CENTER_LAT + 0.0050 * math.sin(t_012 * 0.5), 6)
            fleet_vehicles["LMV-012"]["gps"]["longitude"] = round(MINE_CENTER_LON + 0.0055 * math.cos(t_012 * 0.5), 6)
            fleet_vehicles["LMV-012"]["gps"]["heading_deg"] = round((math.degrees(t_012 * 0.5 + math.pi/2)) % 360, 1)

            # Check for proximity conflicts between vehicles (Collision Avoidance Engine)
            coords = []
            for vid, v in fleet_vehicles.items():
                coords.append((vid, v["gps"]["latitude"], v["gps"]["longitude"]))

            for i in range(len(coords)):
                for j in range(i + 1, len(coords)):
                    v_a, lat1, lon1 = coords[i]
                    v_b, lat2, lon2 = coords[j]
                    # Approx Euclidean distance in meters
                    d_lat = (lat1 - lat2) * 111139.0
                    d_lon = (lon1 - lon2) * 111139.0 * math.cos(math.radians(MINE_CENTER_LAT))
                    dist_m = math.sqrt(d_lat**2 + d_lon**2)
                    
                    if dist_m < 35.0: # Close proximity alert
                        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                        if not any(inc["details"].startswith(f"Proximity conflict between {v_a} and {v_b}") for inc in incident_log[-5:]):
                            incident_log.insert(0, {
                                "id": f"INC-{int(time.time()) % 10000}",
                                "timestamp": now_str,
                                "vehicle_id": v_a,
                                "severity": "WARNING",
                                "type": "FLEET_PROXIMITY_ALERT",
                                "details": f"Proximity conflict between {v_a} and {v_b}: Distance {dist_m:.1f}m",
                                "acknowledged": False,
                                "operator": "Control Room Dispatcher"
                            })
                            if len(incident_log) > 50:
                                incident_log.pop()

        time.sleep(0.1)

# ================= BACKGROUND WORKER: SYNTHETIC / PROXIED VIDEO STREAMS =================
# Generates realistic optical & thermal feeds for Central Security Surveillance
def video_renderer_worker():
    frame_idx = 0
    while True:
        frame_idx += 1
        w, h = 640, 480
        
        for vid in ["HEMM-101", "HEMM-102", "HEMM-204", "LMV-012"]:
            with fleet_lock:
                v = fleet_vehicles.get(vid, fleet_vehicles["HEMM-101"])
                speed = v["powertrain"]["speed_kmh"]
                dist_m = v["radar"]["distance_m"]
                pitch = v["imu"]["pitch_deg"]
                roll = v["imu"]["roll_deg"]
                radar_alert = v["radar"]["alert_level"]
                fog_on = v["ai_vision"]["fog_safe_mode"] or global_fog_mode
                thermal_on = v["ai_vision"]["thermal_mode"]

            # Check if HEMM-101 should proxy from physical vehicle
            proxied_frame = None
            if vid == "HEMM-101" and v["connection"]["is_physical_bridge"]:
                try:
                    p_url = f"{physical_bridge_url}/video_feed"
                    # We can proxy single frames if needed, but synthetic generator ensures 30fps without network lag
                except Exception:
                    pass

            # Create base image
            if thermal_on:
                # Thermal IR Ironbow color palette (purple background, hot orange/white objects)
                img = Image.new("RGB", (w, h), (18, 12, 38))
                draw = ImageDraw.Draw(img)
                # Cool terrain slopes (dark purple to blue gradient)
                draw.polygon([(0, 180), (160, 230), (140, 290), (0, 340)], fill=(32, 20, 60))
                draw.polygon([(w, 170), (480, 230), (510, 300), (w, 350)], fill=(35, 22, 65))
                # Road
                draw.polygon([(180, 210), (460, 210), (600, h), (40, h)], fill=(45, 28, 75))
                
                # Hot thermal exhaust of vehicle ahead
                scale = max(0.2, min(1.0, 1.0 - (dist_m - 10.0) / 100.0))
                tw = int(120 * scale)
                th = int(90 * scale)
                tcx, tcy = 320, int(210 + scale * 140)
                # Engine hot core (bright yellow & white)
                draw.ellipse([tcx - tw//3, tcy - th//2, tcx + tw//3, tcy + th//4], fill=(255, 240, 160))
                draw.ellipse([tcx - tw//5, tcy - th//3, tcx + tw//5, tcy + th//8], fill=(255, 255, 255))
                # Hot tires
                draw.rectangle([tcx - tw//2, tcy - th//4, tcx - tw//3, tcy + th//3], fill=(250, 140, 30))
                draw.rectangle([tcx + tw//3, tcy - th//4, tcx + tw//2, tcy + th//3], fill=(250, 140, 30))
                
                # Ground personnel heat signature walking on berm
                draw.ellipse([140, 270, 152, 285], fill=(255, 250, 180)) # Head
                draw.rectangle([138, 285, 154, 315], fill=(255, 160, 40)) # Body
                draw.line([(142, 315), (140, 335)], fill=(255, 120, 20), width=2)
                draw.line([(150, 315), (152, 335)], fill=(255, 120, 20), width=2)
                
                # Thermal HUD watermark
                draw.text((20, 20), f"THERMAL IR [FLIR IRONBOW] • {vid}", fill=(255, 220, 100))
                draw.text((20, 38), "HEAT SIGNATURES: 1 DUMPER (88°C) | 1 PERSON (37°C)", fill=(255, 180, 50))
            else:
                # Optical FPV Camera Feed
                img = Image.new("RGB", (w, h), (35, 45, 60))
                draw = ImageDraw.Draw(img)
                
                # Fog atmosphere haze
                fog_alpha = 180 if fog_on else 70
                draw.rectangle([0, 0, w, 220], fill=(70, 80, 95))
                
                # Mining benches & quarry walls
                draw.polygon([(0, 140), (150, 185), (120, 240), (0, 310)], fill=(75, 68, 58), outline=(95, 88, 78))
                draw.polygon([(w, 130), (490, 180), (520, 250), (w, 320)], fill=(80, 72, 62), outline=(100, 92, 82))
                
                # Haul road surface
                horizon_y = 210
                draw.polygon([(180, horizon_y), (460, horizon_y), (600, h), (40, h)], fill=(90, 82, 72), outline=(110, 100, 90))
                
                # Moving gravel tracks
                shift = int((frame_idx * max(2, int(speed * 0.2))) % 70)
                for r_y in range(horizon_y + 10, h - 30, 40):
                    y_pos = min(h - 30, r_y + (shift // 2))
                    x_l = int(180 + (40 - 180) * ((y_pos - horizon_y) / (h - horizon_y)))
                    x_r = int(460 + (600 - 460) * ((y_pos - horizon_y) / (h - horizon_y)))
                    draw.line([(x_l + 35, y_pos), (x_l + 60, y_pos + 8)], fill=(65, 58, 48), width=2)
                    draw.line([(x_r - 60, y_pos), (x_r - 35, y_pos + 8)], fill=(65, 58, 48), width=2)
                
                # Truck Ahead in Fog
                scale = max(0.18, min(1.0, 1.0 - (dist_m - 10.0) / 100.0))
                tw = int(160 * scale)
                th = int(115 * scale)
                tcx, tcy = 320, int(horizon_y + scale * 150)
                tl = tcx - tw // 2
                tr = tcx + tw // 2
                tt = tcy - th
                tb = tcy
                
                # Dumper Tires
                draw.rectangle([tl, tb - int(th*0.4), tl + int(tw*0.18), tb], fill=(25, 25, 25))
                draw.rectangle([tr - int(tw*0.18), tb - int(th*0.4), tr, tb], fill=(25, 25, 25))
                # Yellow Body
                draw.rectangle([tl + int(tw*0.15), tt, tr - int(tw*0.15), tb - 8], fill=(235, 175, 25), outline=(185, 135, 15), width=2)
                # Cabin
                draw.rectangle([tl + int(tw*0.2), tt - int(th*0.25), tl + int(tw*0.55), tt], fill=(210, 150, 20))
                # Red hazard brake lights
                draw.ellipse([tl + int(tw*0.16), tb - 18, tl + int(tw*0.25), tb - 8], fill=(255, 30, 30))
                draw.ellipse([tr - int(tw*0.25), tb - 18, tr - int(tw*0.16), tb - 8], fill=(255, 30, 30))
                
                # AI Perception Bounding Box Overlay
                box_color = (255, 23, 68) if radar_alert == "CRITICAL" else (255, 214, 0) if radar_alert == "CAUTION" else (0, 230, 118)
                draw.rectangle([tl - 6, tt - int(th*0.28), tr + 6, tb + 4], outline=box_color, width=2)
                draw.rectangle([tl - 6, tt - int(th*0.28) - 18, tl + 160, tt - int(th*0.28)], fill=box_color)
                draw.text((tl - 2, tt - int(th*0.28) - 16), f"HEMM DUMPER [{dist_m:.1f}m | 96%]", fill=(0, 0, 0))
                
                # Watermark & HUD telemetry
                draw.text((20, 20), f"OPTICAL CSI 1080p • {vid} (TRANSMUTED TO CENTRAL ROOM)", fill=(0, 229, 255))
                draw.text((20, 38), f"SPEED: {speed:.1f} km/h | RANGE: {dist_m:.1f}m | RADAR: {radar_alert}", fill=(255, 255, 255))

            # Cockpit Artificial Horizon Overlay (IMU Pitch & Roll)
            ch_y = int(240 + pitch * 2.8)
            draw.line([(300, ch_y), (340, ch_y)], fill=(0, 229, 255), width=2)
            draw.line([(320, ch_y - 12), (320, ch_y + 12)], fill=(0, 229, 255), width=2)
            
            # Save frame to buffer
            bio = io.BytesIO()
            img.save(bio, format="JPEG", quality=80)
            data = bio.getvalue()
            
            with video_locks[vid]:
                video_frames[vid] = data

        time.sleep(0.04) # ~25 FPS

# ================= FLASK API ROUTES =================

@app.route("/")
def index():
    """Main Central Office Security Surveillance & Fleet Control Room UI."""
    return render_template("index.html")

@app.route("/api/fleet")
def get_fleet():
    """Returns complete real-time status of all monitored HEMM vehicles."""
    with fleet_lock:
        return jsonify({
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_vehicles": len(fleet_vehicles),
            "global_fog_mode": global_fog_mode,
            "gateways": network_gateways,
            "vehicles": fleet_vehicles
        })

@app.route("/api/vehicle/<vehicle_id>")
def get_vehicle(vehicle_id):
    """Returns detailed telemetry for a single vehicle."""
    with fleet_lock:
        if vehicle_id in fleet_vehicles:
            return jsonify({"status": "ok", "vehicle": fleet_vehicles[vehicle_id]})
        return jsonify({"status": "error", "message": "Vehicle not found"}), 404

@app.route("/api/telemetry/ingest", methods=["POST"])
def ingest_telemetry():
    """
    Ingest telemetry transmitted from an on-board vehicle computer
    (Raspberry Pi, NVIDIA Jetson Orin, or LoRa Mesh Gateway).
    """
    data = request.get_json(silent=True)
    if not data or "vehicle_id" not in data:
        return jsonify({"status": "error", "message": "Invalid telemetry payload"}), 400

    vid = data["vehicle_id"]
    with fleet_lock:
        if vid not in fleet_vehicles:
            return jsonify({"status": "error", "message": f"Vehicle {vid} not registered"}), 404

        v = fleet_vehicles[vid]
        v["connection"]["online"] = True
        v["connection"]["last_seen"] = datetime.now(timezone.utc).isoformat()
        
        # Merge incoming fields
        if "speed_kmh" in data:
            v["powertrain"]["speed_kmh"] = float(data["speed_kmh"])
            v["gps"]["speed_kmh"] = float(data["speed_kmh"])
        if "rpm" in data:
            v["powertrain"]["rpm"] = float(data["rpm"])
        if "gps" in data:
            v["gps"].update(data["gps"])
        if "imu" in data:
            v["imu"].update(data["imu"])
        if "radar" in data:
            v["radar"].update(data["radar"])
        if "ultrasonic" in data:
            v["ultrasonic"].update(data["ultrasonic"])
        if "network" in data:
            v["connection"].update(data["network"])

    return jsonify({"status": "ok", "message": "Telemetry transmuted and logged successfully"})

@app.route("/api/control/estop", methods=["POST"])
def remote_estop():
    """Dispatcher Emergency Stop remote trigger."""
    data = request.get_json(silent=True) or {}
    vid = data.get("vehicle_id", "HEMM-101")
    
    with fleet_lock:
        if vid in fleet_vehicles:
            fleet_vehicles[vid]["safety"]["estop_active"] = True
            fleet_vehicles[vid]["powertrain"]["speed_kmh"] = 0.0
            fleet_vehicles[vid]["powertrain"]["rpm"] = 0.0
            fleet_vehicles[vid]["powertrain"]["last_cmd"] = "S"
            fleet_vehicles[vid]["status"] = "EMERGENCY_STOPPED"
            
            # Log incident
            incident_log.insert(0, {
                "id": f"ESTOP-{int(time.time()) % 10000}",
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                "vehicle_id": vid,
                "severity": "CRITICAL",
                "type": "REMOTE_ESTOP_TRIGGERED",
                "details": f"Central Office Dispatcher executed emergency remote powertrain cut on {vid}",
                "acknowledged": True,
                "operator": "Security Dispatcher"
            })
            return jsonify({"status": "ok", "vehicle_id": vid, "estop": True})
    return jsonify({"status": "error", "message": "Vehicle not found"}), 404

@app.route("/api/control/horn", methods=["POST"])
def remote_horn():
    """Dispatcher remote horn / siren pulse."""
    data = request.get_json(silent=True) or {}
    vid = data.get("vehicle_id", "HEMM-101")
    duration_s = data.get("duration", 2.0)
    
    with fleet_lock:
        if vid in fleet_vehicles:
            fleet_vehicles[vid]["safety"]["horn_sounding"] = True
            
            def reset_horn():
                time.sleep(duration_s)
                with fleet_lock:
                    if vid in fleet_vehicles:
                        fleet_vehicles[vid]["safety"]["horn_sounding"] = False
            threading.Thread(target=reset_horn, daemon=True).start()
            
            return jsonify({"status": "ok", "vehicle_id": vid, "horn_sounding": True})
    return jsonify({"status": "error", "message": "Vehicle not found"}), 404

@app.route("/api/control/cabin_message", methods=["POST"])
def send_cabin_message():
    """Send dispatcher message to vehicle cabin HUD."""
    data = request.get_json(silent=True) or {}
    vid = data.get("vehicle_id", "HEMM-101")
    msg = data.get("message", "DISPATCH ALERT")
    
    with fleet_lock:
        if vid in fleet_vehicles:
            fleet_vehicles[vid]["safety"]["cabin_msg"] = msg
            return jsonify({"status": "ok", "vehicle_id": vid, "message": msg})
    return jsonify({"status": "error", "message": "Vehicle not found"}), 404

@app.route("/api/control/fog_mode", methods=["POST"])
def toggle_fog_mode():
    """Toggle mine-wide Fog Safe Protocol."""
    global global_fog_mode
    data = request.get_json(silent=True) or {}
    global_fog_mode = data.get("enable", not global_fog_mode)
    
    with fleet_lock:
        for vid, v in fleet_vehicles.items():
            v["safety"]["fog_protocol"] = global_fog_mode
            v["ai_vision"]["fog_safe_mode"] = global_fog_mode
            if global_fog_mode:
                v["safety"]["cabin_msg"] = "FOG CONVOY MODE: MAX 15 KM/H"
                
    incident_log.insert(0, {
        "id": f"FOG-{int(time.time()) % 10000}",
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "vehicle_id": "ALL_FLEET",
        "severity": "WARNING" if global_fog_mode else "INFO",
        "type": "FOG_SAFE_PROTOCOL",
        "details": f"Global Fog Safe convoy protocol {'ACTIVATED' if global_fog_mode else 'DEACTIVATED'} by Central Office",
        "acknowledged": True,
        "operator": "Safety Supervisor"
    })
    return jsonify({"status": "ok", "fog_mode": global_fog_mode})

@app.route("/api/settings/bridge_url", methods=["POST"])
def set_bridge_url():
    """Set custom vehicle edge IP / URL (e.g. http://192.168.1.100:5000)."""
    global physical_bridge_url
    data = request.get_json(silent=True) or {}
    new_url = data.get("url", DEFAULT_VEHICLE_BRIDGE_URL).strip().rstrip("/")
    physical_bridge_url = new_url
    return jsonify({"status": "ok", "bridge_url": physical_bridge_url})

@app.route("/api/incidents")
def get_incidents():
    """Returns security audit log."""
    return jsonify({"status": "ok", "incidents": incident_log})

@app.route("/api/incidents/acknowledge", methods=["POST"])
def ack_incident():
    """Acknowledge an incident."""
    data = request.get_json(silent=True) or {}
    inc_id = data.get("id")
    for inc in incident_log:
        if inc["id"] == inc_id:
            inc["acknowledged"] = True
            return jsonify({"status": "ok", "incident": inc})
    return jsonify({"status": "error", "message": "Incident not found"}), 404

@app.route("/video_feed/<vehicle_id>")
def video_stream(vehicle_id):
    """MJPEG surveillance stream for specified vehicle."""
    if vehicle_id not in video_locks:
        vehicle_id = "HEMM-101"

    def generate():
        while True:
            with video_locks[vehicle_id]:
                frame = video_frames.get(vehicle_id)
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.04) # 25 FPS

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ================= SERVER ENTRYPOINT =================
if __name__ == "__main__":
    print("=" * 70)
    print(" [*] MINE VISION-X -- CENTRAL FLEET CONTROL & SECURITY SURVEILLANCE ROOM")
    print("=" * 70)
    print(f" [*] Central Command Gateway: http://127.0.0.1:{PORT}")
    print(f" [*] Monitoring Fleet: {list(fleet_vehicles.keys())}")
    print(f" [*] Physical Bridge Polling: {physical_bridge_url}")
    print(f" [*] LoRa Mesh & 4G Ingestion API: http://127.0.0.1:{PORT}/api/telemetry/ingest")
    print("=" * 70)
    
    # Start Background Workers
    t_bridge = threading.Thread(target=vehicle_bridge_worker, daemon=True)
    t_sim = threading.Thread(target=fleet_simulator_worker, daemon=True)
    t_vid = threading.Thread(target=video_renderer_worker, daemon=True)
    
    t_bridge.start()
    t_sim.start()
    t_vid.start()
    
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
