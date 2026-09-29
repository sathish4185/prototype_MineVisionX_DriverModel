import smbus
import time

bus = smbus.SMBus(1)
UBLOX_ADDR = 0x42

raw_buffer = ""
sentences = []

print("Listening to U-Blox NEO-M9N for 5 seconds...")
start = time.time()
while time.time() - start < 5:
    try:
        msb = bus.read_byte_data(UBLOX_ADDR, 0xFD)
        lsb = bus.read_byte_data(UBLOX_ADDR, 0xFE)
        avail = (msb << 8) | lsb
        if avail > 0:
            chunk = bus.read_i2c_block_data(UBLOX_ADDR, 0xFF, min(avail, 32))
            for b in chunk:
                if b != 0xFF:
                    raw_buffer += chr(b)
        while "\r\n" in raw_buffer:
            line, raw_buffer = raw_buffer.split("\r\n", 1)
            line = line.strip()
            if line.startswith("$"):
                sentences.append(line)
    except Exception as e:
        print("I2C read err:", e)
    time.sleep(0.05)

print(f"Total NMEA sentences received: {len(sentences)}")
seen_tags = {}
for s in sentences:
    tag = s.split(",")[0]
    if tag not in seen_tags:
        seen_tags[tag] = s
        print(f"Sample {tag}: {s}")

print("\n--- Satellite view sentences (GSV) ---")
for s in sentences:
    if "GSV" in s:
        print(" ", s)
