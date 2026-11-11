# Diagnostic SD-boot card for the X-Pro1 (3.82): the boot ROM loads ffboot.bin, which only lights the green status LED
# and halts. No ffuser.bin, no flash access. Green LED after the boot-button combination ⇒ the ROM ran our code from the
# card (SD boot works; any later failure is in the full image). No LED ⇒ the ROM did not load the card (combination,
# card format or header).
#
# usage: build_sdboot_led.py <FPUPDATE.DAT (3.82-based)> <fujimod green-led-arm.generated.bin> <outdir>
#
# Method and data follow fujimod (crates/recovery/src/green_led/initialization.rs, catalog green-led xpro1-382):
# LED descriptor pair in blob1 at decoded offset 0xd8498 (2 × 28 bytes: kind 1, port<<16|pin, polarity), stock GPIO table
# record for port 15 at loader 0x44c0. The 372-byte stub (sha256 checked below) was disassembled: cpsid aif; for each
# (address, clear, value): clear ? *a = value | (*a & ~clear) : *a = value; dsb; wfe loop.
import hashlib, os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import lz

dat_path, stub_path, out = sys.argv[1:4]
raw = open(dat_path, 'rb').read(); img = bytes(x ^ 0xff for x in raw)
sha = lambda b: hashlib.sha256(b).hexdigest()
word = lambda b, o: struct.unpack('<I', b[o:o + 4])[0]

hdr = struct.unpack('<5I', img[0x10025c:0x10025c + 20])
blob1, _, err = lz.decode(img, 0x10025c + 20, hdr[1] - 20); assert err is None
pair = bytes(blob1[0xd8498:0xd8498 + 56])
assert sha(pair) == 'b306f02a9171e1843017fe6c62a754b8aeb7444446360c3bb845c1c07bdc471d', 'LED descriptor proof differs'
loader = img[0x4025c:0x4025c + 0x40000]
assert sha(loader[0x4f7c:0x4f7c + 172]) == 'c55a310d7a339bdacc5876cb8e8869b4da1c53f31f176da7e23e9ef9dc6d65ef', 'GPIO init proof differs'
fields = loader[0x44c0:0x44c0 + 28]
assert sha(fields) == 'f02209ab23bb4b2c3ba86f7ae554571bbf867ed2ce16f030cac8acdc0fa13755', 'port-15 GPIO record differs'

pads = []
for row in (pair[:28], pair[28:]):
    assert word(row, 4) == 1 and word(row, 0) == 0 and not any(row[16:])
    pid, pol = word(row, 8), word(row, 12)
    assert pid >> 16 < 16 and pid & 0xffff < 16 and pol <= 1
    pads.append((pid >> 16, pid & 0xffff, pol))
writes = []
for index in (1, 0):                                   # index 0 = LED switched on (green), index 1 = the other, off
    port, pin, pol = pads[index]
    assert port == 15, f'unexpected LED port {port}'
    bit, mux_mask = 1 << pin, 3 << (2 * (pin % 8))
    extended, mux = word(fields, 0), word(fields, 4 * (1 + pin // 8))
    control, direction = word(fields, 12), word(fields, 16)
    assert extended & (3 << (2 * pin)) == 0 and mux & mux_mask == 0 and direction & bit == bit
    gpio = 0xfff89000 + port * 64
    high = pol if index == 0 else 1 - pol
    writes += [(gpio + 24, 3 << (2 * pin), 0), (gpio + 12 + 4 * (pin // 8), 0, mux_mask << 16),
               (gpio + 8, 0, (bit << 16) | (control & bit)), (gpio, 0, (bit << 16) | (high << pin)),
               (gpio + 4, 0, (bit << 16) | bit)]
    print(f'LED {"on " if index == 0 else "off"}: port {port} pin {pin} polarity {pol}')

stub = bytearray(open(stub_path, 'rb').read())
assert len(stub) == 372
assert stub[8:8 + 4 + 24 * 12] == bytes(4 + 24 * 12), 'stub config area not empty'
assert sha(bytes(stub)) == '494964bbea714915ee7bbdf4860bd34ddeebbf6c344ef2bc302f7abb50367099', 'unexpected fujimod green-led stub (re-audit before use)'
stub[8:12] = struct.pack('<I', len(writes))
for i, (a, c, v) in enumerate(writes):
    stub[12 + i * 12:24 + i * 12] = struct.pack('<3I', a, c, v); print(f'  write {a:#010x} clear {c:#010x} value {v:#010x}')

ffsys = bytearray(img[0x25c:0x25c + 512])
assert sha(bytes(ffsys)) == '83a3fc5e9e88e6eda0dacb8657cb4c8a83163f2df846bff250b53368e28c9a24'
ffsys[16:20] = struct.pack('<I', 0x301)               # hold power through SD load
os.makedirs(out, exist_ok=True)
for n, b in (('ffsys.bin', ffsys), ('ffboot.bin', stub)):
    open(os.path.join(out, n), 'wb').write(b); print(f'wrote {n} {len(b)} bytes sha256 {sha(bytes(b))}')
