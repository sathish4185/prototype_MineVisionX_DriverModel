import time
import subprocess
import grovepi

def reset_grovepi():
    try:
        subprocess.run(["pinctrl", "set", "8", "op", "dl"], check=False)
        time.sleep(0.15)
        subprocess.run(["pinctrl", "set", "8", "op", "dh"], check=False)
        time.sleep(0.5)
        print("[GrovePi] Reset pulse asserted on GPIO 8.")
    except Exception as e:
        print(f"[GrovePi] Reset warning: {e}")

reset_grovepi()

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
    valid = [r for r in readings if isinstance(r, (int, float)) and 2 <= r <= 450]
    print(f"Port D{pin}: {readings} -> Valid: {len(valid)} > 0 ({valid})")

