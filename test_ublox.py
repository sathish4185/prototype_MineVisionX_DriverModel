import smbus
import time

bus = smbus.SMBus(1)
UBLOX_ADDR = 0x42

print("=== Reading U-Blox NEO-M9N GNSS at I2C address 0x42 ===")

for i in range(10):
    try:
        msb = bus.read_byte_data(UBLOX_ADDR, 0xFD)
        lsb = bus.read_byte_data(UBLOX_ADDR, 0xFE)
        avail = (msb << 8) | lsb
        print(f"[{i}] Bytes available in buffer: {avail}")
        
        if avail > 0:
            bytes_to_read = min(avail, 32)
            chunk = bus.read_i2c_block_data(UBLOX_ADDR, 0xFF, bytes_to_read)
            chars = "".join([chr(b) for b in chunk if b != 0xFF])
            print(f"    Raw data: {repr(chars)}")
    except Exception as e:
        print(f"[{i}] Error: {e}")
    time.sleep(0.5)
