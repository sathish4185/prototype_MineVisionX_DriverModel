import time
import smbus

bus = smbus.SMBus(1)

print("=" * 60)
print("1. PROBING 7SEMI UBLOX NEO-M9N (I2C Address: 0x42)")
print("=" * 60)
try:
    # U-blox registers 0xFD and 0xFE contain number of bytes available in the buffer
    bytes_avail_msb = bus.read_byte_data(0x42, 0xFD)
    bytes_avail_lsb = bus.read_byte_data(0x42, 0xFE)
    bytes_avail = (bytes_avail_msb << 8) | bytes_avail_lsb
    print(f"Bytes available in Ublox buffer: {bytes_avail}")

    # Read from data stream register 0xFF
    nmea_data = []
    # Try reading available bytes or up to 256 bytes
    count = min(bytes_avail, 256) if bytes_avail > 0 else 64
    for _ in range(count):
        b = bus.read_byte_data(0x42, 0xFF)
        if b != 0xFF:  # 0xFF indicates empty
            nmea_data.append(chr(b))
    
    text = "".join(nmea_data)
    print("Received NMEA/Data stream from NEO-M9N:")
    if text.strip():
        for line in text.splitlines():
            if line.strip():
                print(f"  {line.strip()}")
    else:
        print("  (Buffer empty or waiting for satellite acquisition, device acknowledged on 0x42)")
    print("Status: Ublox NEO-M9N responding on 0x42: SUCCESS")
except Exception as e:
    print(f"Error reading Ublox: {e}")

print("\n" + "=" * 60)
print("2. PROBING IMU / ACCELEROMETER (I2C Address: 0x4c)")
print("=" * 60)
try:
    # Read first 16 registers to inspect chip behavior
    regs = [bus.read_byte_data(0x4c, r) for r in range(16)]
    print(f"Registers 0x00 - 0x0F: {[hex(x) for x in regs]}")

    # Check for MMA7660 (Grove 3-Axis Accelerometer)
    # Reg 0x07 is MODE. Bit 0 = Standby(0) / Active(1)
    # Set to Active mode:
    bus.write_byte_data(0x4c, 0x07, 0x01)
    time.sleep(0.05)

    def parse_mma7660(val):
        # 6-bit signed integer
        if val & 0x40:  # alert bit / invalid reading, retry
            return None
        # 6-bit signed: if bit 5 is 1, negative
        val = val & 0x3F
        if val & 0x20:
            val -= 0x40
        return val

    print("Reading acceleration values (sample over 1 second):")
    samples = []
    for _ in range(5):
        raw_x = bus.read_byte_data(0x4c, 0x00)
        raw_y = bus.read_byte_data(0x4c, 0x01)
        raw_z = bus.read_byte_data(0x4c, 0x02)
        tilt = bus.read_byte_data(0x4c, 0x03)
        x = parse_mma7660(raw_x)
        y = parse_mma7660(raw_y)
        z = parse_mma7660(raw_z)
        print(f"  Raw: [X={hex(raw_x)}, Y={hex(raw_y)}, Z={hex(raw_z)}, Tilt={hex(tilt)}] -> Interpreted: X={x}, Y={y}, Z={z}")
        time.sleep(0.2)
    print("Status: IMU responding on 0x4c: SUCCESS")
except Exception as e:
    print(f"Error reading IMU: {e}")
print("=" * 60)
