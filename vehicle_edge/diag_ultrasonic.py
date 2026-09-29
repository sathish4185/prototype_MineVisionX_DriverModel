import time
import subprocess
import grovepi

def main():
    print("=== GROVEPI ULTRASONIC SENSOR DIAGNOSTIC ===")
    try:
        # Reset GrovePi
        subprocess.run(["pinctrl", "set", "8", "op", "dl"], check=False)
        time.sleep(0.15)
        subprocess.run(["pinctrl", "set", "8", "op", "dh"], check=False)
        time.sleep(0.4)
    except Exception as e:
        print(f"Reset err: {e}")

    for port in [2, 3, 4, 5, 6, 7, 8]:
        reads = []
        for _ in range(3):
            try:
                val = grovepi.ultrasonicRead(port)
                reads.append(val)
            except Exception as e:
                reads.append(f"err:{e}")
            time.sleep(0.05)
        print(f"Port D{port}: {reads}")

if __name__ == "__main__":
    main()
