import urllib.request
import io
from PIL import Image
import numpy as np

def main():
    try:
        req = urllib.request.urlopen("http://127.0.0.1:5000/video_feed", timeout=5)
        # Read enough bytes to get a full JPEG
        data = bytearray()
        while True:
            chunk = req.read(4096)
            if not chunk:
                break
            data.extend(chunk)
            start = data.find(b"\xff\xd8")
            if start != -1:
                end = data.find(b"\xff\xd9", start)
                if end != -1:
                    jpg_data = bytes(data[start:end+2])
                    img = Image.open(io.BytesIO(jpg_data))
                    arr = np.array(img)
                    mean_rgb = arr.mean(axis=(0, 1))
                    overall_mean = float(arr.mean())
                    min_val, max_val = int(arr.min()), int(arr.max())
                    print(f"CAMERA LIVE STATUS: ACTIVE")
                    print(f"Resolution: {img.size[0]}x{img.size[1]} ({img.format})")
                    print(f"Mean RGB: R={mean_rgb[0]:.1f}, G={mean_rgb[1]:.1f}, B={mean_rgb[2]:.1f}")
                    print(f"Overall Mean Luminance: {overall_mean:.1f} / 255.0")
                    darkness_pct = max(0.0, min(100.0, (1.0 - overall_mean / 255.0) * 100.0))
                    print(f"Calculated Scene Darkness: {darkness_pct:.1f}%")
                    print(f"Pixel Dynamic Range: [{min_val}, {max_val}]")
                    with open("/home/pi/Desktop/robot_project/live_check.jpg", "wb") as f:
                        f.write(jpg_data)
                    print("Snapshot successfully saved to /home/pi/Desktop/robot_project/live_check.jpg")
                    return
    except Exception as e:
        print(f"Error checking camera feed: {e}")

if __name__ == "__main__":
    main()
