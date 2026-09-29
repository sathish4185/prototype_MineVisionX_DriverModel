import time
import io
import numpy as np
from PIL import Image

def build_thermal_lut():
    lut = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        x = i / 255.0
        if x < 0.25:
            r = int(x * 4 * 70)
            g = 0
            b = int(40 + x * 4 * 180)
        elif x < 0.5:
            t = (x - 0.25) * 4
            r = int(70 + t * 175)
            g = int(t * 30)
            b = int(220 * (1.0 - t * 0.85))
        elif x < 0.75:
            t = (x - 0.5) * 4
            r = int(245 + t * 10)
            g = int(30 + t * 195)
            b = int(35 * (1.0 - t))
        else:
            t = (x - 0.75) * 4
            r = 255
            g = 255
            b = int(t * 255)
        lut[i] = [r, g, b]
    return lut

def test_all():
    lut = build_thermal_lut()
    arr = np.random.randint(10, 30, (480, 640, 3), dtype=np.uint8)
    r = arr[:, :, 0].astype(np.uint16)
    g = arr[:, :, 1].astype(np.uint16)
    b = arr[:, :, 2].astype(np.uint16)
    gray = ((r * 77 + g * 150 + b * 29) >> 8).astype(np.uint8)

    # Thermal
    t0 = time.time()
    thermal = lut[gray]
    bio = io.BytesIO()
    Image.fromarray(thermal).save(bio, format="JPEG", quality=75)
    dt_th = (time.time() - t0) * 1000
    print(f"Thermal frame: {dt_th:.2f} ms, size: {len(bio.getvalue())} bytes")

    # Mono
    t0 = time.time()
    mono = np.stack([gray, gray, gray], axis=-1)
    bio = io.BytesIO()
    Image.fromarray(mono).save(bio, format="JPEG", quality=75)
    dt_mono = (time.time() - t0) * 1000
    print(f"Mono frame: {dt_mono:.2f} ms, size: {len(bio.getvalue())} bytes")

if __name__ == "__main__":
    test_all()
