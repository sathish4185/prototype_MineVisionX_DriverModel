@echo off
title Mine Vision-X - Vehicle ADAS HUD & Edge Telematics
color 0B
echo ======================================================================
echo   MINE VISION-X - ON-BOARD VEHICLE ADAS & TELEMATICS NODE
echo   In-Cabin Operator HUD & Sensor Fusion Suite (Port 5000)
echo ======================================================================
echo.
echo [*] Starting Vehicle Telemetry Server on http://127.0.0.1:5000...
echo [*] Launching In-Cabin HUD Dashboard...
echo.

cd /d "%~dp0"
start "" http://127.0.0.1:5000
python app.py

pause
