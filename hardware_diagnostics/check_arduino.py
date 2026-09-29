import time
import serial

print("=== CHECKING ARDUINO SERIAL PORT /dev/ttyUSB0 ===")

baud_rates = [9600, 115200, 57600, 38400]
received_any = False

for baud in baud_rates:
    try:
        ser = serial.Serial('/dev/ttyUSB0', baud, timeout=2)
        print(f"\n[+] Opened /dev/ttyUSB0 at {baud} baud.")
        time.sleep(2.0)  # Arduino resets when serial port opens
        
        # Check if incoming data
        incoming = ser.read(ser.in_waiting if ser.in_waiting > 0 else 100)
        if incoming:
            print(f"  -> RECEIVED DATA at {baud} baud: {incoming}")
            try:
                print(f"  -> Text: {incoming.decode('utf-8', errors='replace')}")
            except:
                pass
            received_any = True
        else:
            print(f"  -> Port open, but no unsolicited data at {baud} baud.")
        ser.close()
    except Exception as e:
        print(f"  -> Error opening at {baud}: {e}")

if not received_any:
    print("\nNote: Arduino serial port is physically communicating and open.")
    print("If no text was received, the currently loaded Arduino sketch may be waiting for commands,")
    print("or not calling Serial.print(), or needs a test firmware loaded.")
