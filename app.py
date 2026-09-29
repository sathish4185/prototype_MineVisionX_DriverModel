#!/usr/bin/env python3
"""
Mine Vision-X | Unified System Entrypoint
Launches either the In-Cabin Vehicle ADAS Node or the Central Fleet Control Room.

Usage:
    python app.py                 # Default: Launches Vehicle In-Cabin ADAS Node (Port 5000)
    python app.py --mode vehicle  # Explicitly launches Vehicle Edge Node (Port 5000)
    python app.py --mode control  # Launches Central Office Fleet Control Room (Port 8080)
    python app.py --mode diag     # Lists available hardware diagnostic scripts
"""

import sys
import os
import argparse

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def run_vehicle_edge():
    """Launch the on-board vehicle ADAS and telemetry node."""
    print("=" * 70)
    print(" [*] LAUNCHING MINE VISION-X: ON-BOARD VEHICLE ADAS & TELEMETRICS NODE")
    print(" [*] Local In-Cabin Dashboard: http://127.0.0.1:5000")
    print("=" * 70)
    vehicle_dir = os.path.join(ROOT_DIR, "vehicle_edge")
    os.chdir(vehicle_dir)
    sys.path.insert(0, vehicle_dir)
    import app as vehicle_app
    # Run vehicle app
    vehicle_app.init_bus()
    t_cam = vehicle_app.threading.Thread(target=vehicle_app.camera_worker, daemon=True)
    t_sonic = vehicle_app.threading.Thread(target=vehicle_app.ultrasonic_worker, daemon=True)
    t_imu = vehicle_app.threading.Thread(target=vehicle_app.imu_worker, daemon=True)
    t_gps = vehicle_app.threading.Thread(target=vehicle_app.gps_worker, daemon=True)
    t_ard = vehicle_app.threading.Thread(target=vehicle_app.arduino_worker, daemon=True)
    
    t_cam.start()
    t_sonic.start()
    t_imu.start()
    t_gps.start()
    t_ard.start()
    
    vehicle_app.app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

def run_fleet_control():
    """Launch the Central Office Fleet Control Room & Security Surveillance Gateway."""
    print("=" * 70)
    print(" [*] LAUNCHING MINE VISION-X: CENTRAL FLEET CONTROL ROOM & SURVEILLANCE")
    print(" [*] Central Command Wall: http://127.0.0.1:8080")
    print("=" * 70)
    control_dir = os.path.join(ROOT_DIR, "fleet_control_room")
    os.chdir(control_dir)
    sys.path.insert(0, control_dir)
    import server as control_server
    
    t_bridge = control_server.threading.Thread(target=control_server.vehicle_bridge_worker, daemon=True)
    t_sim = control_server.threading.Thread(target=control_server.fleet_simulator_worker, daemon=True)
    t_vid = control_server.threading.Thread(target=control_server.video_renderer_worker, daemon=True)
    
    t_bridge.start()
    t_sim.start()
    t_vid.start()
    
    control_server.app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)

def list_diagnostics():
    """List available hardware diagnostic tools."""
    diag_dir = os.path.join(ROOT_DIR, "hardware_diagnostics")
    print("=" * 70)
    print(" [*] MINE VISION-X: HARDWARE DIAGNOSTICS & SENSOR SUITE")
    print("=" * 70)
    scripts = [f for f in os.listdir(diag_dir) if f.endswith(".py")]
    for s in sorted(scripts):
        print(f"  - python hardware_diagnostics/{s}")
    print("=" * 70)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mine Vision-X Launcher")
    parser.add_argument(
        "--mode", 
        choices=["vehicle", "control", "diag"], 
        default="vehicle",
        help="Subsystem to launch: 'vehicle' (Port 5000), 'control' (Port 8080), or 'diag'"
    )
    args = parser.parse_args()

    if args.mode == "vehicle":
        run_vehicle_edge()
    elif args.mode == "control":
        run_fleet_control()
    elif args.mode == "diag":
        list_diagnostics()
