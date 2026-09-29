import smbus

bus = smbus.SMBus(1)
found = []
for addr in range(0x03, 0x78):
    try:
        bus.read_byte(addr)
        found.append(hex(addr))
    except Exception:
        pass
print("I2C Bus 1 addresses found:", found)
