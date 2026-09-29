import smbus
import time

bus = smbus.SMBus(1)
UBLOX_ADDR = 0x42

def send_ubx(msg_class, msg_id, payload=b""):
    length = len(payload)
    header = bytes([0xB5, 0x62, msg_class, msg_id, length & 0xFF, (length >> 8) & 0xFF])
    msg = header + payload
    ck_a, ck_b = 0, 0
    for b in msg[2:]:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    packet = msg + bytes([ck_a, ck_b])
    
    # Write to I2C register 0xFF
    for i in range(0, len(packet), 16):
        chunk = list(packet[i:i+16])
        bus.write_i2c_block_data(UBLOX_ADDR, 0xFF, chunk)
        time.sleep(0.005)

print("Polling UBX-MON-VER (Hardware & Firmware Info)...")
send_ubx(0x0A, 0x04) # UBX-MON-VER poll
time.sleep(0.3)

msb = bus.read_byte_data(UBLOX_ADDR, 0xFD)
lsb = bus.read_byte_data(UBLOX_ADDR, 0xFE)
avail = (msb << 8) | lsb
print(f"Available bytes after poll: {avail}")
if avail > 0:
    raw = []
    to_read = min(avail, 256)
    while to_read > 0:
        step = min(to_read, 32)
        chunk = bus.read_i2c_block_data(UBLOX_ADDR, 0xFF, step)
        raw.extend(chunk)
        to_read -= step
    
    # Search for UBX sync 0xB5 0x62
    raw_bytes = bytes(raw)
    idx = raw_bytes.find(b"\xb5\x62\x0a\x04")
    if idx >= 0:
        sw_version = raw_bytes[idx+6:idx+36].split(b"\x00")[0].decode('latin1', errors='ignore')
        hw_version = raw_bytes[idx+36:idx+46].split(b"\x00")[0].decode('latin1', errors='ignore')
        print(f"--> U-Blox Detected! SW: {sw_version}, HW: {hw_version}")
    else:
        print("Received raw stream:", "".join([chr(b) if 32 <= b < 127 else "." for b in raw[:80]]))
