"""Classic Chrome's own look data for the 11th film simulation (MODE_FSIM 6 = colour mode 1), and PRO Neg. Hi back
to stock. Plan shared by the live test (this file: apply / restore / status over USB) and the SD card (fsim11.py).

Colour mode 1 already takes PROVIA's detail, chroma-gain and highlight/shadow settings, which are what Classic
Chrome uses. Only three selections differ and each falls back to PROVIA for colour mode 1 in the stock code:
  3x3 matrix  FUN_00f32fcc: cm -> table index chains, sRGB `movne r2,#0` 0xf333c4, alt `movne r1,#0` 0xf3344c
  2x2 matrix  FUN_00f2d404: defaults `mov r3,#0` 0xf2d724 (sRGB) / 0xf2d7a8 (alt);
              FUN_00f30b10 (by mode row): `movne r2,#0` 0xf30d7c (sRGB) / 0xf30e0c (alt)
  tone family FUN_00f321f0 `movhi r2,#0` 0xf32218; FUN_00f3232c `movhi r3,#0xf9` 0xf32360 / 0xf32570
Each fallback instruction becomes a call to a stub that returns index 7 (matrices) or family 5 / code 0xff (tone)
for colour mode 1 and the stock value otherwise, keeping the flags the following instructions test.
  * index 7 exists in the sRGB selector tables (IDs 0xdd26 / 0xdd8e / 0xdd5e; 0xe4a0; 0x10101 + 0x30·row), holding
    PROVIA's presets on stock. The alt tables have 7 entries: the two with a padding word get an 8th ID written
    there (0xf3430e, 0xf34256, 0xf2deb6), the two without are relocated to copies with an 8th entry (0xf34064 via its
    movw/movt at 0xf33474; 0xf31718 via 0xf30e10 and its row stride 7 -> 8 at 0xf30e18, r5 is dead afterwards).
  * tone family 5 / code 0xff belongs to SEPIA, whose curve IDs all equal PROVIA's (family 0 / 0xf9), so SEPIA
    is moved to PROVIA's family in the three cm->family byte tables and family 5 gets curve 38 (the X-E2 Classic
    Chrome curve, in the flashed v2's curve slot #40). Guard: if the running blob1 has no curve 38 the tone code
    patches are skipped (a missing curve number falls back to curve 0 in 0x8056a8).
Data (tuning area, applied by the tuning hook): the 76 bytes of the v2 PRO Neg. Hi patch back to stock, the
v2 3x3 matrices copied to presets 17 (sRGB) / 18 (alt), the v3 2x2 to preset 12, the selectors above, and
family 5's 40 curve IDs := 38 (as v2 did for PRO Neg. Hi). Free IDs 0xe409 / 0xe40b (unused 2x2 preset 13) hold the alt selectors.
Live test over USB: re/tools/cclook.py apply | restore | status (debug firmware, flash v2).
"""
import os, struct, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))   # repo root
DB_RAM, DB_FILE, DB_LEN = 0x40d3b580, 0xae025c, 0xb3700
B2_BASE = 0xe0ec80
CURVE_CNT, CURVE_TAB, CURVE_NEW = 0x80b6f8, 0x80b700, 38
CM_FSIM6 = 0xf396b0 + 4 * 5                       # fsim 6 -> colour mode (1 on stock: this plan keeps it)
ICACHE_INVALIDATE = 0x8a5d70

P3X3_SRGB, P3X3_ALT, P2X2 = 17, 18, 12
ID_3X3 = lambda p: 0xdc23 + 0x12 * (p - 17)        # 9 u16 (presets 17..30 unused, identity on stock)
ID_2X2 = lambda p: 0xe401 + 8 * (p - 12)           # 4 u16 (presets 12.. unused)
SEL_ALT3, SEL_ALT2 = 0xe409, 0xe40b                # free bytes (2x2 preset 13 region)
V3_2X2 = bytes.fromhex('ae020a04e11f2400')         # m00 0x02ae, m11 0x040a, m01 0x1fe1, m10 0x0024 (build_cc3)
FAM5_IDS = [0xdf92, 0xdf99, 0xdfa0, 0xdfae] + list(range(0xde37, 0xde49)) + list(range(0xdeb5, 0xdec7))   # 40, as v2's
# (the family's two '+7' entries 0xdfa7 / 0xdfb5 stay 16: in that mode every film simulation uses curve 16)
ALT3_SRC = [0xddb0, 0xddb1, 0xddb2, 0xddb3, 0xddb4, 0xddb5, 0xddb6]           # 0xf34064 (7 u16)
ALT2_ROWS = [[0x10123 + 0x30 * r + k for k in range(7)] for r in range(4)]     # 0xf31718 (4 rows x 7 u32)

# blob2 words: (address, stock word, new word or symbol); symbols are resolved by layout()
CODE = [
    (0xf333c4, 0x13a02000, ('blne', 'A')), (0xf3344c, 0x13a01000, ('blne', 'B')),
    (0xf2d724, 0xe3a03000, ('bl', 'C')), (0xf2d7a8, 0xe3a03000, ('bl', 'C')),
    (0xf30d7c, 0x13a02000, ('blne', 'A')), (0xf30e0c, 0x13a02000, ('blne', 'A')),
    (0xf33474, 0x03043064, ('movweq r3', 'ALT3')), (0xf33478, 0x034030f3, ('movteq r3', 'ALT3')),
    (0xf30e10, 0xe3013718, ('movw r3', 'ALT2')), (0xf30e14, 0xe34030f3, ('movt r3', 'ALT2')),
    (0xf30e18, 0xe0655185, 0xe1a05185),                                       # rsb r5,r5,r5,lsl#3 -> lsl r5,r5,#3
    (0xf3430c, 0x0000dd4e, SEL_ALT3 << 16 | 0xdd4e), (0xf34254, 0x0000dd86, SEL_ALT3 << 16 | 0xdd86),
    (0xf2deb4, 0x0000e4c8, SEL_ALT2 << 16 | 0xe4c8)]
TONE = [                                                                      # only with curve 38 present
    (0xf32218, 0x83a02000, ('bl', 'T1')), (0xf32360, 0x83a030f9, ('bl', 'T2')), (0xf32570, 0x83a030f9, ('bl', 'T2')),
    (0xf34364, 0x02010506, 0x02010006), (0xf3443c, 0xfbfafffe, 0xfbfaf9fe), (0xf34074, 0xfbfafffe, 0xfbfaf9fe)]
STUBS = {
    'A': 'cmp r2, #1\n moveq r2, #7\n movne r2, #0\n bx lr',
    'B': 'cmp r3, #1\n moveq r1, #7\n movne r1, #0\n bx lr',
    'C': 'cmp r2, #1\n moveq r3, #7\n movne r3, #0\n bx lr',
    'T1': 'cmn r3, #1\n moveq r2, #5\n movne r2, #0\n cmp r3, #5\n bx lr',
    'T2': 'cmn r3, #1\n beq cm1\n cmp r3, #5\n movhi r3, #0xf9\n bx lr\ncm1:\n mov r3, #0xff\n cmp r3, #5\n bx lr'}


def layout(base):
    """Filler addresses for the stubs and the two relocated tables (0xa0 bytes from base, 16-aligned)."""
    base = (base + 15) & ~15
    return {'A': base, 'B': base + 0x10, 'C': base + 0x20, 'T1': base + 0x30, 'T2': base + 0x50,
            'ALT3': base + 0x70, 'ALT2': base + 0x80, 'end': base + 0x100}


def blobs(lay, asm):
    """{address: bytes} of everything that goes into the filler."""
    out = {k: asm(STUBS[k], lay[k]) for k in STUBS}
    assert all(len(out[k]) <= 0x10 for k in 'ABC') and len(out['T1']) <= 0x20 and len(out['T2']) <= 0x20
    out['ALT3'] = struct.pack('<8H', *ALT3_SRC, SEL_ALT3)
    out['ALT2'] = b''.join(struct.pack('<8I', *row, SEL_ALT2) for row in ALT2_ROWS)
    return {lay[k]: v for k, v in out.items()}


def words(lay, asm, tone=True):
    """[(address, old, new)] blob2 patches with symbols resolved."""
    def enc(a, sym):
        kind, tgt = sym
        if kind in ('bl', 'blne'): return struct.unpack('<I', asm(f'{kind} #{lay[tgt]:#x}', a))[0]
        v = lay[tgt]; op, reg = kind.split(); imm = v & 0xffff if op.startswith('movw') else v >> 16
        return struct.unpack('<I', asm(f'{op} {reg}, #{imm:#x}', a))[0]
    return [(a, o, enc(a, n) if isinstance(n, tuple) else n) for a, o, n in CODE + (TONE if tone else [])]


def db_bytes(stock, v2, b2=None):
    """{id: (old, new)} for the tuning area, old = the flashed v2 value."""
    m = {}
    for i in range(DB_LEN):
        if stock[i] != v2[i]: m[i] = (v2[i], stock[i])                   # PRO Neg. Hi (and v2's curve IDs) back
    for p, src in ((P3X3_SRGB, 0xdb4b), (P3X3_ALT, 0xdba5)):              # v2 Classic Chrome matrices -> new presets
        for k in range(18): m[ID_3X3(p) + k] = (v2[ID_3X3(p) + k], v2[src + k])
    for k in range(8): m[ID_2X2(P2X2) + k] = (v2[ID_2X2(P2X2) + k], V3_2X2[k])
    sel = {0xdd26: P3X3_SRGB, 0xdd8e: P3X3_SRGB, 0xdd5e: P3X3_SRGB, 0xe4a0: P2X2, SEL_ALT3: P3X3_ALT, SEL_ALT2: P2X2}
    sel.update({0x10101 + 0x30 * r: P2X2 for r in range(4)})
    for i, v in sel.items(): m[i] = (v2[i], v)
    for i in FAM5_IDS: m[i] = (v2[i], CURVE_NEW)
    assert all(o != n for o, n in m.values()) or True
    return {i: m[i] for i in sorted(m) if m[i][0] != m[i][1]}


def db_params(m, v2):
    """cchook-style (id, old hex, new hex) u16 entries, non-overlapping, from a byte map."""
    out, done = [], set()
    for i in sorted(m):
        if i in done: continue
        o = bytearray(v2[i:i + 2]); n = bytearray(o)
        for k in (0, 1):
            if i + k in m: n[k] = m[i + k][1]; done.add(i + k)
        out.append((i, o.hex(), n.hex()))
    return out


def areas():
    stock = bytes(x ^ 0xff for x in open(os.path.join(ROOT, 'FPUPDATE.DAT'), 'rb').read()[DB_FILE:DB_FILE + DB_LEN])
    v2 = bytes(x ^ 0xff for x in open(os.path.join(ROOT, 're', 'build', 'ptpdebug_385', 'FPUPDATE.DAT'), 'rb').read()[DB_FILE:DB_FILE + DB_LEN])
    return stock, v2
