import time
import serial

print("=== READING ARDUINO TELEMETRY AT 9600 BAUD ===")
ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
time.sleep(2)  # Reset delay

start = time.time()
lines = []
while time.time() - start < 4:
    line = ser.readline().decode('utf-8', errors='replace').strip()
    if line:
        print(f"[{time.strftime('%H:%M:%S')}] {line}")
        lines.append(line)

ser.close()
print(f"\nTotal lines captured in 4s: {len(lines)}")
