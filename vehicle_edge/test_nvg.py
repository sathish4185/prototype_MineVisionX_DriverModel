import time
import io
import numpy as np
from PIL import Image

def test_pipeline():
    print("Testing Night Vision Pipeline with synthetic array...")
    arr = np.random.randint(10, 30, (480, 640, 3), dtype=np.uint8)
    
    # Fast luminance
    sample = arr[::8, ::8, :].astype(np.float32)
    lum = float((sample[:,:,0]*0.299 + sample[:,:,1]*0.587 + sample[:,:,2]*0.114).mean())
    ambient_lux = np.clip((lum / 255.0) * 100.0, 0.0, 100.0)
    darkness = 100.0 - ambient_lux
    print(f"Luminance: {lum:.1f}, Ambient Lux: {ambient_lux:.1f}%, Darkness: {darkness:.1f}%")
    
    # Grayscale
    r = arr[:, :, 0].astype(np.uint16)
    g = arr[:, :, 1].astype(np.uint16)
    b = arr[:, :, 2].astype(np.uint16)
    gray = ((r * 77 + g * 150 + b * 29) >> 8).astype(np.uint8)
    
    # Gain
    enhanced = np.clip(gray.astype(np.float32) * 1.6, 0, 255).astype(np.uint8)
    
    # NVG Green
    r_ch = (enhanced.astype(np.uint16) * 28 >> 8).astype(np.uint8)
    g_ch = np.clip(enhanced.astype(np.uint16) * 290 >> 8, 0, 255).astype(np.uint8)
    b_ch = (enhanced.astype(np.uint16) * 48 >> 8).astype(np.uint8)
    out = np.stack([r_ch, g_ch, b_ch], axis=-1)
    
    # JPEG encode
    bio = io.BytesIO()
    Image.fromarray(out).save(bio, format="JPEG", quality=75)
    print(f"SUCCESS: Generated NVG frame, JPEG size: {len(bio.getvalue())} bytes")

if __name__ == "__main__":
    test_pipeline()
