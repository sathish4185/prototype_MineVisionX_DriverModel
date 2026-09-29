import time
import json
import urllib.request

print("=== CHECKING IMU STABILITY (5 SAMPLES OVER 1.5 SECONDS) ===")
for i in range(5):
    res = urllib.request.urlopen("http://127.0.0.1:5000/api/telemetry")
    data = json.loads(res.read().decode('utf-8'))['imu']
    print(f"Sample {i+1}: Pitch={data['pitch']} deg | Roll={data['roll']} deg | Accel: X={data['ax']}g, Y={data['ay']}g, Z={data['az']}g")
    time.sleep(0.3)
