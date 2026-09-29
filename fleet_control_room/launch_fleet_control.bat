@echo off
title Mine Vision-X Central Fleet Control Room Gateway
color 0B
echo ======================================================================
echo   MINE VISION-X - CENTRAL FLEET CONTROL & SECURITY SURVEILLANCE
echo   Central Office Command Center (Away from Vehicle)
echo ======================================================================
echo.
echo [*] Starting Central Fleet Control Room Server on port 8080...
echo [*] Physical Vehicle Bridge listening on http://127.0.0.1:5000
echo [*] Ingesting LoRa Mesh / 4G Telemetry Streams...
echo.

cd /d "%~dp0"
start "" http://localhost:8080
python server.py

pause
