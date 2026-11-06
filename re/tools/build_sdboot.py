# Build X-Pro1 (EXR Pro, firmware 3.82) SD dual-boot files: ffsys.bin, ffboot.bin, ffuser.bin.
# Nothing is written to the camera's flash: the boot ROM loads ffboot.bin, which loads ffuser.bin (a complete RAM image of
# the firmware, blobs already decompressed) into DRAM and jumps to it.
#
# usage: build_sdboot.py <FPUPDATE.DAT (stock or patched 3.82-based)> <fujimod exr-sd-loader.generated.bin> <outdir>
#                        [--marker 9]   (EXIF "Ver3.8<marker>" so photos show the camera ran from the card; default 9)
#
# Packaging follows fujimod's xpro1-382 recipe (github.com/justjake/fujimod, catalog/recovery/recipes.generated.json and
# crates/recovery/src/{exr,image}.rs). The fujimod loader binary is NOT part of this repo (the project has no licence);
# pass its path. Its 388-byte stage was disassembled and checked: copy to SRAM 0xfff00800, ROM open("ffuser.bin"), size
# check, chunked ROM reads into DRAM from 0, CRC32 check, jump to 0; any error halts (battery pull). No flash access.
import hashlib, os, struct, sys, zlib
sys.path.insert(0, os.path.dirname(__file__))
import lz

args = sys.argv[1:]; marker = '9'
if '--marker' in args:
    k = args.index('--marker'); marker = args[k + 1]; del args[k:k + 2]
assert len(args) == 3, __doc__
dat_path, loader_path, out = args
assert marker.isdigit() and len(marker) == 1

raw = open(dat_path, 'rb').read()
assert len(raw) == 38274200, 'not an X-Pro1 3.82-sized FPUPDATE.DAT'
img = bytes(x ^ 0xff for x in raw)                      # fujimod's "inverted" view (= our NOT-space image)
sha = lambda b: hashlib.sha256(b).hexdigest()

# ---- recipe (fujimod xpro1-382). Hashes are of the STOCK decoded sources; patched builds may differ only in blob1.
PLAN_SIZE = 0x16a0000
REGIONS = [  # name, RAM address, file offset, size, compressed, decoded size, stock sha256
    ('loader',        0x000000, 0x04025c, 0x040000, False, 0x040000, None),
    ('section-table', 0x770000, 0x0e025c, 0x000400, False, 0x000400, None),
    ('section-0',     0x040000, 0x08025c, 0x00d7a0, False, 0x00d7a0, None),
    ('section-1',     0x0d0000, 0x0a025c, 0x00d760, False, 0x00d760, None),
    ('section-2',     0x130000, 0xc8025c, 0x215a54, False, 0x215a54, None),
    ('section-3',     0x510000, 0x154025c, 0x081134, False, 0x081134, None),
    ('section-4',     0x774000, 0x10025c, 0x140000, True,  0x2549c0, None),   # blob1
    ('section-5',     0xe0ec80, 0x24025c, 0x220000, True,  0x3dbb00, None),   # blob2
    ('section-6',     0x1420000, 0x46025c, 0x280000, False, 0x280000, None),
]
BSS = [(0x9c89c0, 0x372bc0), (0x11ea780, 0x22bb40)]
EDITS = [  # address, old, new, what (fujimod)
    (0x486c, 0xebffff7d, 0xe3a00000, 'loader: retain preloaded section table'),
    (0x46d0, 0xeb000106, 0xe3a00000, 'loader: retain preloaded stock kernel/application'),
    (0x46dc, 0xeb000103, 0xe3a00000, 'loader: retain preloaded stock kernel/application'),
    (0x46f8, 0xeb000125, 0xe3a00000, 'loader: retain preloaded stock kernel/application'),
    (0x770008, 0x0, 0x1, 'section table: preloaded'),
]
# ours: SD-boot marker in the EXIF/firmware version string (blob1 0x857a68.. writes "Ver3.82" when DB[0x206] != 0xff)
MARK_ADDR, MARK_OLD = 0x857a98, 0xe3a03032                 # mov r3, #0x32 ('2')
MARK_NEW = 0xe3a03000 | ord(marker)
HEADER = (0x25c, 512, '83a3fc5e9e88e6eda0dacb8657cb4c8a83163f2df846bff250b53368e28c9a24')
ROM_OPEN, ROM_READ, ROM_FS = 0x80001a74, 0x80001b38, 0xfff00000
LOADER_STAGE, LOADER_CONFIG = 388, 368
LOADER_SHA = '6eeade09359659eb9de37d86405103439c39d033f9a7600044e43b29d679923a'

ram = bytearray(PLAN_SIZE); spans = []
for name, addr, off, size, comp, dsize, _ in REGIONS:
    if comp:
        hdr = struct.unpack('<5I', img[off:off + 20])
        data, p, err = lz.decode(img, off + 20, hdr[1] - 20)
        assert err is None and len(data) == dsize == hdr[0], name
    else:
        data = img[off:off + size]
    assert addr + len(data) <= PLAN_SIZE and not any(a < addr + len(data) and addr < b for a, b in spans), name
    ram[addr:addr + len(data)] = data; spans.append((addr, addr + len(data)))
    print(f'{name:14} @{addr:#09x} {len(data):#09x} bytes  sha256 {sha(bytes(data))[:16]}')
for a, n in BSS:
    assert not any(x < a + n and a < y for x, y in spans) and all(v == 0 for v in ram[a:a + n])
for a, old, new, what in EDITS + [(MARK_ADDR, MARK_OLD, MARK_NEW, f'marker: version string Ver3.8{marker}')]:
    cur = struct.unpack('<I', ram[a:a + 4])[0]
    assert cur == old, f'{what}: expected {old:#x} at {a:#x}, found {cur:#x}'
    ram[a:a + 4] = struct.pack('<I', new); print(f'edit {a:#09x} {old:#010x} -> {new:#010x}  {what}')

ffsys = bytearray(img[HEADER[0]:HEADER[0] + HEADER[1]])
assert sha(bytes(ffsys)) == HEADER[2], 'ffsys header differs from the 3.82 recipe'
assert struct.unpack('<3I', ffsys[:12]) == (0x00ffaa55, 0x01234567, 0x89abcdef)
assert struct.unpack('<I', ffsys[16:20])[0] == 0x300
ffsys[16:20] = struct.pack('<I', 0x301)                  # hold power through SD load

loader = open(loader_path, 'rb').read()
assert sha(loader) == LOADER_SHA, 'unexpected fujimod loader binary (re-audit before use)'
ffboot = bytearray(loader[:LOADER_STAGE])
assert ffboot[LOADER_CONFIG:LOADER_CONFIG + 20] == bytes(20)
ffuser = bytes(ram)
crc = zlib.crc32(ffuser) & 0xffffffff                    # same reflected CRC32 as the loader (0xedb88320, ~init, ~final)
ffboot[LOADER_CONFIG:LOADER_CONFIG + 20] = struct.pack('<5I', ROM_OPEN, ROM_READ, ROM_FS, len(ffuser), crc)
assert len(ffboot) < 0x10000

os.makedirs(out, exist_ok=True)
for n, b in (('ffsys.bin', ffsys), ('ffboot.bin', ffboot), ('ffuser.bin', ffuser)):
    open(os.path.join(out, n), 'wb').write(b); print(f'wrote {n:10} {len(b):9} bytes  sha256 {sha(bytes(b))}')
print(f'ffuser CRC32 {crc:#010x}; source {os.path.basename(dat_path)} sha256 {sha(raw)[:16]}')
