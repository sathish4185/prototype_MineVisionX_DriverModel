import smbus
import time

bus = smbus.SMBus(1)
UBLOX_ADDR = 0x42

# Drain old buffer
print("Draining old buffer...")
while True:
    msb = bus.read_byte_data(UBLOX_ADDR, 0xFD)
    lsb = bus.read_byte_data(UBLOX_ADDR, 0xFE)
    avail = (msb << 8) | lsb
    if avail == 0:
        break
    to_read = min(avail, 32)
    bus.read_i2c_block_data(UBLOX_ADDR, 0xFF, to_read)
    if avail < 32:
        break

print("Monitoring new live NMEA sentences for 6 seconds...")
raw = ""
start = time.time()
while time.time() - start < 6:
    msb = bus.read_byte_data(UBLOX_ADDR, 0xFD)
    lsb = bus.read_byte_data(UBLOX_ADDR, 0xFE)
    avail = (msb << 8) | lsb
    if avail > 0:
        chunk = bus.read_i2c_block_data(UBLOX_ADDR, 0xFF, min(avail, 32))
        for b in chunk:
            if b != 0xFF:
                raw += chr(b)
    while "\r\n" in raw:
        line, raw = raw.split("\r\n", 1)
        line = line.strip()
        if line.startswith("$"):
            print("NMEA:", line)
    time.sleep(0.05)
