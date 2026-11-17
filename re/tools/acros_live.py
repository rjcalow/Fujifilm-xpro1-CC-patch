"""Live preview of the ACROS-style tone on the X-Pro1 (USB debug firmware, flash boot): MONO temporarily shoots with
the ACROS-style curves. RAM only; `restore` or a power cycle undoes it. Nothing else changes.

What it does (classic_chrome/config/acros_curves.py, FINDINGS.md §10):
  * blob1 curve table (RAM 0x80b700): the knots of curves #1, #2, #3 (not used by any film simulation) := the
    ACROS-style versions of the curves MONO uses (#0, #14, #16). The curve numbers stay 1, 2, 3.
  * tuning area (RAM 0x40d3b580 + ID): MONO's base-tone curve IDs (tone family 6) 0xdf93, 0xdf9a (#0 → 1),
    0xdfa1, 0xdfaf (#14 → 2), 0xdfa8, 0xdfb6 (#16 → 3). Every other film simulation keeps its curves.
Visible effect: MONO, MONO+Ye/R/G pictures (and in-camera RAW conversions to MONO) get the ACROS-style tone:
deeper blacks, brighter mid-tones. The menu still says MONOCHROME.
usage: ~/.venvs/xpro1-re/bin/python re/tools/acros_live.py apply | restore | status
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, os.path.join(ROOT, 'public'))
import ptpdebug
from classic_chrome.config import acros_curves as AC

DB_RAM = 0x40d3b580
SLOTS = {0: 1, 14: 2, 16: 3}                          # MONO curve → slot (curve number) that gets its ACROS version
IDS = {0xdf93: 0, 0xdf9a: 0, 0xdfa1: 14, 0xdfaf: 14, 0xdfa8: 16, 0xdfb6: 16}   # family-6 base-tone IDs: stock curve


def plan():
    import xpro1_cc_patch as P
    def blob1(path, hdr):
        img = bytes(x ^ 0xff for x in open(path, 'rb').read()); size, packed = struct.unpack_from('<II', img, hdr)
        return P.lz_decode(img, hdr + 20, hdr + packed, size)
    x1 = blob1(os.path.join(ROOT, 'FPUPDATE.DAT'), 0x10025c); x2 = blob1(os.path.join(ROOT, 'FWUP0008.DAT'), 0x23025c)
    cur = AC.curves(x1, x2)
    words = []                                        # (RAM address, stock word, new word) in the curve table
    for src, slot in SLOTS.items():
        e = AC.entry(x1, AC.X1_BASE, AC.X1_TAB, AC.X1_CNT, slot)
        a = AC.X1_TAB + 0x48 * [struct.unpack_from('<I', x1, AC.X1_TAB - AC.X1_BASE + 0x48 * i)[0]
                                for i in range(AC.X1_CNT)].index(slot)
        new = bytearray(e); new[4:13] = cur[src][0][4:13]
        struct.pack_into('<27H', new, 0x10, *cur[src][1])
        for k in range(0, 0x48, 4):
            o, n = struct.unpack_from('<I', e, k)[0], struct.unpack_from('<I', new, k)[0]
            if o != n: words.append((a + k, o, n))
    return words


def main(a):
    if not a or a[0] not in ('apply', 'restore', 'status'): sys.exit(__doc__)
    words = plan()
    p = ptpdebug.PTP(); p.open()
    w = lambda ad: struct.unpack('<I', p.peek(ad, 4))[0]
    def poke(ad, v):
        r, _, _ = p.op(ptpdebug.POKE, ad, v & 0xffffffff)
        if r != 0x2001 or w(ad) != v & 0xffffffff: sys.exit(f'POKE {ad:#x} failed')
    def dbbyte(i): ad = (DB_RAM + i) & ~3; return w(ad) >> 8 * ((DB_RAM + i) & 3) & 0xff
    def setdb(i, old, new):
        ad = (DB_RAM + i) & ~3; sh = 8 * ((DB_RAM + i) & 3); cur = w(ad)
        if (cur >> sh) & 0xff != old: print(f'  ID {i:#x}: unexpected {(cur >> sh) & 0xff}, skipped'); return
        poke(ad, cur & ~(0xff << sh) | new << sh)
    if a[0] == 'apply':
        bad = [(ad, o) for ad, o, n in words if w(ad) not in (o, n)]
        if bad: sys.exit(f'curve table not as expected at {[hex(x) for x, _ in bad][:4]}; nothing written')
        for ad, o, n in words:
            if w(ad) == o: poke(ad, n)
        for i, src in IDS.items(): setdb(i, src, SLOTS[src]) if dbbyte(i) == src else None
        print(f'applied: {len(words)} curve-table words, {len(IDS)} MONO tone IDs → ACROS-style curves')
    elif a[0] == 'restore':
        for i, src in IDS.items():
            if dbbyte(i) == SLOTS[src]: setdb(i, SLOTS[src], src)
        for ad, o, n in words:
            if w(ad) == n: poke(ad, o)
        print('restored')
    cur = sum(1 for ad, o, n in words if w(ad) == n)
    print('status: curve words ACROS', cur, '/', len(words), ' MONO IDs:', {hex(i): dbbyte(i) for i in IDS})
    p.op(0x1003)


if __name__ == '__main__':
    main(sys.argv[1:])
