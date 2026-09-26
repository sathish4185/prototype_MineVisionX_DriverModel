import time
import serial

print("=== TESTING ARDUINO COMMAND INPUT ===")
ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
time.sleep(2)  # Reset delay

# Flush startup messages
ser.reset_input_buffer()

test_cmds = ['?', 'help', 'F', 'S', 'B', 'status', '1']

for cmd in test_cmds:
    ser.write((cmd + '\n').encode('utf-8'))
    time.sleep(0.3)
    response = []
    while ser.in_waiting > 0:
        line = ser.readline().decode('utf-8', errors='replace').strip()
        if line:
            response.append(line)
    print(f"Sent: '{cmd}' -> Received: {response}")

ser.close()
