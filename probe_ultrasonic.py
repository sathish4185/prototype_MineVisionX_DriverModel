import time
import grovepi

print("=== PROBING GROVEPI DIGITAL PORTS FOR ULTRASONIC SENSOR ===")
for pin in [2, 3, 4, 5, 6, 7, 8]:
    readings = []
    for _ in range(4):
        try:
            val = grovepi.ultrasonicRead(pin)
            readings.append(val)
        except Exception as e:
            readings.append(-1)
        time.sleep(0.06)
    valid = [r for r in readings if isinstance(r, (int, float)) and 0 < r < 450]
    print(f"Port D{pin}: {readings} -> Valid: {len(valid)} > 0 ({valid})")
