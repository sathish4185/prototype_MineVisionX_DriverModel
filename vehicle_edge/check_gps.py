import smbus2
import time

bus = smbus2.SMBus(1)
UBLOX_ADDR = 0x42

raw = ""
print("Listening to GNSS module for 5 seconds...")
for _ in range(50):
    try:
        msb = bus.read_byte_data(UBLOX_ADDR, 0xFD)
        lsb = bus.read_byte_data(UBLOX_ADDR, 0xFE)
        avail = (msb << 8) | lsb
        if avail > 0:
            to_read = min(avail, 128)
            while to_read > 0:
                block_len = min(to_read, 32)
                chunk = bus.read_i2c_block_data(UBLOX_ADDR, 0xFF, block_len)
                for b in chunk:
                    if b != 0xFF:
                        raw += chr(b)
                to_read -= block_len
    except:
        pass
    time.sleep(0.1)

sentences = [s.strip() for s in raw.split("\r\n") if s.startswith("$")]
print(f"Total NMEA sentences captured: {len(sentences)}")

unique_tags = set(s.split(",")[0] for s in sentences)
print(f"NMEA sentence types emitted: {sorted(list(unique_tags))}")

print("\n--- Raw Sample Sentences ---")
for s in sentences[:10]:
    print(s)

print("\n--- Satellite Signal Analysis ---")
gsv_lines = [s for s in sentences if "GSV" in s]
if gsv_lines:
    print(f"Found {len(gsv_lines)} GSV (Satellites in view) sentences:")
    for line in gsv_lines:
        print("  ", line)
else:
    print("No GSV sentences captured yet.")

print("\n--- Navigation Fix Analysis ---")
rmc_lines = [s for s in sentences if "RMC" in s]
if rmc_lines:
    print("Latest RMC:", rmc_lines[-1])
gga_lines = [s for s in sentences if "GGA" in s]
if gga_lines:
    print("Latest GGA:", gga_lines[-1])
gsa_lines = [s for s in sentences if "GSA" in s]
if gsa_lines:
    print("Latest GSA:", gsa_lines[-1])
