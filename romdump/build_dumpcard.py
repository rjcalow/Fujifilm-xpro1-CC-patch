"""Build an X-Pro1 SD dual-boot card whose only addition is one read-only USB operation, for dumping memory (the
16 KiB boot ROM in particular) over USB. The camera's flash is never written; without the key combination at
power-on, or after taking the battery out, the camera boots exactly as before.

usage (Linux, research environment from re/tools/setup_work.sh):
  ~/.venvs/xpro1-re/bin/python romdump/build_dumpcard.py FPUPDATE.DAT OUTDIR [--stub re/work/chain/chain_crumbs.bin]

FPUPDATE.DAT must be the official X-Pro1 3.82 update file (your own copy; nothing from Fujifilm is in this script).
OUTDIR receives ffboot.bin, ffsys.bin and card.txt (hashes). Copy the two .bin files to the root of a FAT32 card.

What the card does (all in RAM, every write checks the old value first and is skipped if it does not match):
  1. Boot ROM (Fn + command-dial press at power-on) loads ffsys.bin + ffboot.bin. ffboot.bin = our chain stub
     (re/sdchain) + the stock boot loader from your file, compressed. The stub unpacks the loader and starts it; the
     loader loads the firmware from flash as usual.
  2. Loader final jump → the tested SD-boot hook (re/tools/crumbs.py: power-on cause fix, DRAM breadcrumbs, EXIF
     marker "Ver3.89" in photos taken while SD-booted). Same code as the card that booted on the camera
     (ffboot e7af6d5a…), plus step 3.
  3. Stage B also redirects blob1's call that starts blob2 (0x972520 `bl 0x854e48`) to DUMP_HOOK. By then blob1 has
     loaded blob2 into RAM. DUMP_HOOK sets PTP vendor opcode 0x9010 in blob2's handler table (slot 0xf4c0dc, stock
     value 0xf4bff0 = "operation not supported") to a PEEK handler, records its status, then starts blob2.
     blob2's code is not changed. There is no write or call operation.
  4. PEEK (0x9010): p1 = address (word aligned), p2 = length (≤ 0x10000, whole words) → data phase. Needs an open
     PTP session. Same handler as the USB debug firmware (re/tools/build_ptpdebug.py), assembled at PEEK_AT.
Filler layout (loader 0xb000..0xb3ff, unused 0xff bytes, still 0xff in a running camera): ID_AT 'XPRO1 ROMDUMP' +
version, STATUS_AT (1 = PEEK enabled in RAM, 2 = slot already in use, e.g. a flashed debug firmware; stays 0xffffffff if the
hook never ran), DUMP_HOOK, PEEK handler. romdump.py reads ID and status to tell what is running.
"""
import hashlib, os, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(ROOT, 're', 'tools')); sys.path.insert(0, os.path.join(ROOT, 'public'))
import xpro1_cc_patch as P                      # official-file check, container checksums, LZ decoder
import crumbs                                   # tested SD-boot hook (needs keystone-engine)
import build_ptpdebug as PTP                    # PEEK handler source and blob2 addresses

VERSION = 1
LOADER_SHA = 'ff31ef67c7b024a33ea3757cbff3d9564618c9660a90bbbbfecffaf6a31f24a7'
FFSYS_SHA = '83a3fc5e9e88e6eda0dacb8657cb4c8a83163f2df846bff250b53368e28c9a24'
STUB_DEFAULT = os.path.join(ROOT, 're', 'work', 'chain', 'chain_crumbs.bin')
B1_HDR, B1_BASE, B2_HDR, B2_BASE = 0x10025c, 0x774000, 0x24025c, PTP.B2_BASE
SITE, START_B2 = 0x972520, 0x854e48            # blob1: `bl 0x854e48` (start blob2) inside 0x972518
SLOT = PTP.TABLE90 + 4 * 0x10                   # handler table entry of opcode 0x9010
AREA, AREA_END = 0xb000, 0xb400                 # loader filler, free when --cc is not used (cchook area)
ID_AT, STATUS_AT, HOOK_AT, PEEK_AT = AREA, AREA + 0x1c, AREA + 0x20, AREA + 0x80
ID = b'XPRO1 ROMDUMP\0\0\0' + struct.pack('<I', VERSION)
# ffboot.bin of the reference build (official 3.82 + chain_crumbs.bin 19069ea8…), emulator-checked; see README
REFERENCE_FFBOOT = '79118fee084ce0abf5561a99a48d2709898c9272a2d66a80bde07f790b6fab6f'


def add_peek(L, asm, bl):
    """crumbs.patch(extra=...) callback: writes ID, hook and PEEK handler; returns the stage B blob1 patch."""
    assert all(b == 0xff for b in L[AREA:AREA_END]), 'dump area is not free filler'
    imm = lambda r, v: f'movw {r}, #{v & 0xffff}\n    movt {r}, #{v >> 16}'
    hook = asm(f'''
    push {{r0, r1, r2, lr}}
    {imm('r1', SLOT)}
    ldr r2, [r1]
    {imm('r0', PTP.GENERIC)}
    cmp r2, r0
    {imm('r0', PEEK_AT)}
    streq r0, [r1]
    mcreq p15, 0, r1, c7, c10, 1
    moveq r2, #1
    movne r2, #2
    {imm('r1', STATUS_AT)}
    str r2, [r1]
    dsb
    pop {{r0, r1, r2, lr}}
    b {START_B2:#x}''', HOOK_AT)
    peek, at = PTP.handlers(base=PEEK_AT, ops=('peek',), limit=AREA_END)
    assert HOOK_AT + len(hook) <= PEEK_AT and at['peek'] == PEEK_AT
    L[ID_AT:ID_AT + len(ID)] = ID
    L[HOOK_AT:HOOK_AT + len(hook)] = hook
    L[PEEK_AT:PEEK_AT + len(peek)] = peek
    patch = (SITE, bl(SITE, START_B2), bl(SITE, HOOK_AT))
    return [patch], {'hook': HOOK_AT, 'peek': PEEK_AT, 'peek_bytes': len(peek), 'site': SITE}


def check_firmware(img):
    """The addresses used here, checked against the decoded blob1/blob2 of the input file."""
    w = lambda b, base, a: struct.unpack('<I', b[a - base:a - base + 4])[0]
    u1, p1 = struct.unpack('<II', img[B1_HDR:B1_HDR + 8]); b1 = P.lz_decode(img, B1_HDR + 20, B1_HDR + p1, u1)
    u2, p2 = struct.unpack('<II', img[B2_HDR:B2_HDR + 8]); b2 = P.lz_decode(img, B2_HDR + 20, B2_HDR + p2, u2)
    from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM
    bl = struct.unpack('<I', bytes(Ks(KS_ARCH_ARM, KS_MODE_ARM).asm(f'bl {START_B2:#x}', SITE)[0]))[0]
    assert w(b1, B1_BASE, SITE) == bl, 'blob1: blob2 start call not found'
    assert w(b1, B1_BASE, START_B2 + 8) == 0xe3a00005, 'blob1: 0x854e48 is not the section-5 start routine'
    assert w(b2, B2_BASE, SLOT) == PTP.GENERIC, 'blob2: opcode 0x9010 is not free'
    for f, first in ((PTP.F_COPYREQ, 0xe52db004), (PTP.F_SEND, 0xe92d4870), (PTP.F_RESP, 0xe92d4870)):
        assert w(b2, B2_BASE, f) == first, f'blob2: {f:#x} is not the expected function entry'
    return b1, b2


def build(dat, out, stub_path=STUB_DEFAULT):
    raw = open(dat, 'rb').read()
    if hashlib.sha256(raw).hexdigest() != P.STOCK_SHA256:
        sys.exit('input is not the official X-Pro1 3.82 FPUPDATE.DAT (sha256 709e26f6…)')
    assert P.check(raw)[0], 'container checksums'
    img = bytes(x ^ 0xff for x in raw)
    print('checking blob1 / blob2 addresses ...'); check_firmware(img)
    loader = bytearray(img[0x4025c:0x4025c + 0x40000])
    assert hashlib.sha256(loader).hexdigest() == LOADER_SHA, 'loader differs from 3.82'
    if not os.path.exists(stub_path): sys.exit(f'{stub_path} missing: run sh re/tools/setup_work.sh first')
    stub = bytearray(open(stub_path, 'rb').read())
    assert struct.pack('<2I', 0xfff44024, 0xfff44028) in stub, 'needs the chain_crumbs.bin stub (-DCRUMBS)'
    info = crumbs.patch(loader, img[0x8025c:0x8025c + 0xd7a0], extra=add_peek)
    print('hook:', {k: (hex(v) if isinstance(v, int) else v) for k, v in info['extra'].items()})
    # card assembly, as re/tools/build_sdchain.py
    loader = bytes(loader)
    c = zlib.compressobj(9, zlib.DEFLATED, -15, 9); payload = c.compress(loader) + c.flush()
    m = bytes(stub).find(struct.pack('<I', 0x4e494843)); cfg = m - 0x14
    assert m > 0 and bytes(stub).count(struct.pack('<I', 0x4e494843)) == 1 and stub[cfg:m] == bytes(20), 'stub config'
    stub += bytes(-len(stub) % 4)
    off = len(stub); total = off + len(payload); total += -total % 4
    struct.pack_into('<5I', stub, cfg, total, off, len(payload), len(loader), zlib.crc32(loader) & 0xffffffff)
    ffboot = bytes(stub) + payload + bytes(total - off - len(payload))
    assert len(ffboot) < 0x10000, 'ffboot.bin too large: the boot ROM reads only 16 bits of the length'
    ffsys = bytearray(img[0x25c:0x25c + 512])
    assert hashlib.sha256(ffsys).hexdigest() == FFSYS_SHA
    ffsys[16:20] = struct.pack('<I', 0x301)          # "hold power through the SD load"
    os.makedirs(out, exist_ok=True)
    lines = [f'X-Pro1 ROM dump card v{VERSION} (romdump/build_dumpcard.py)']
    for n, b in (('ffboot.bin', ffboot), ('ffsys.bin', bytes(ffsys))):
        open(os.path.join(out, n), 'wb').write(b)
        h = hashlib.sha256(b).hexdigest(); lines.append(f'{h}  {n}'); print(f'wrote {n} {len(b)} bytes sha256 {h}')
    open(os.path.join(out, 'card.txt'), 'w').write('\n'.join(lines) + '\n')
    h = hashlib.sha256(ffboot).hexdigest()
    if REFERENCE_FFBOOT:
        print('ffboot.bin matches the reference build' if h == REFERENCE_FFBOOT else
              'WARNING: ffboot.bin differs from the reference build (different stub or assembler version?): '
              'run the emulator checks in romdump/README.md before using it')
    return ffboot


if __name__ == '__main__':
    a = sys.argv[1:]; stub = STUB_DEFAULT
    if '--stub' in a: k = a.index('--stub'); stub = a[k + 1]; del a[k:k + 2]
    if len(a) != 2: sys.exit(__doc__)
    build(a[0], a[1], stub)
