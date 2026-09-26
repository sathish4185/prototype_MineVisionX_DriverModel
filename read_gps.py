import smbus
import time

bus = smbus.SMBus(1)
UBLOX_ADDR = 0x42

def get_bytes_available():
    try:
        msb = bus.read_byte_data(UBLOX_ADDR, 0xFD)
        lsb = bus.read_byte_data(UBLOX_ADDR, 0xFE)
        return (msb << 8) | lsb
    except:
        return 0

def read_nmea_stream(duration_sec=3):
    start = time.time()
    buffer = ""
    while time.time() - start < duration_sec:
        avail = get_bytes_available()
        if avail > 0:
            to_read = min(avail, 32)
            try:
                chunk = bus.read_i2c_block_data(UBLOX_ADDR, 0xFF, to_read)
                for b in chunk:
                    if b != 0xFF:
                        buffer += chr(b)
            except Exception as e:
                pass
        time.sleep(0.05)
    return buffer

print("Capturing live NMEA stream from NEO-M9N for 3 seconds...")
nmea = read_nmea_stream(3)
lines = [l for l in nmea.split("\r\n") if l.startswith("$")]
print(f"Captured {len(lines)} NMEA sentences:")
for l in lines[:10]:
    print(" ", l)
