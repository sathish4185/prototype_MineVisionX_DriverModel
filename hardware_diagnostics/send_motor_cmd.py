import sys
import time
import serial

cmd = sys.argv[1] if len(sys.argv) > 1 else 'F'
print(f"Opening /dev/ttyUSB0 and sending motor command: '{cmd}'...")

ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
time.sleep(2)  # Reset delay
ser.reset_input_buffer()

ser.write(cmd.encode('utf-8'))
print(f"Sent: '{cmd}'")
time.sleep(0.5)

# Read any reply
for _ in range(5):
    line = ser.readline().decode('utf-8', errors='replace').strip()
    if line:
        print("Received from Arduino:", line)

ser.close()
