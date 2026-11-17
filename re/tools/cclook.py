"""Live test of Classic Chrome's own look over USB (debug firmware, flash-booted v2): apply | restore | status.

The plan itself (data, stubs, blob2 words, tuning bytes) is re/classic_chrome/features/cc_look.py; the SD card gets
the same changes through re/classic_chrome/convert.py.
usage: ~/.venvs/xpro1-re/bin/python re/tools/cclook.py apply | restore | status
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from classic_chrome.features.cc_look import *          # noqa: F401,F403  (constants, layout, blobs, words, db_*)

# ---------------------------------------------------------------- live (USB debug firmware, flash-booted v2)
LIVE_BASE = 0xbc00


def main(a):
    if not a or a[0] not in ('apply', 'restore', 'status'): sys.exit(__doc__)
    import ptpdebug
    from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM
    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM); asm = lambda src, at: bytes(ks.asm(src, at)[0])
    stock, v2 = areas(); m = db_bytes(stock, v2); lay = layout(LIVE_BASE)
    p = ptpdebug.PTP(); p.open()
    w = lambda ad, n=1: list(struct.unpack(f'<{n}I', p.peek(ad, 4 * n)))
    def poke(ad, v):
        r, _, _ = p.op(ptpdebug.POKE, ad, v & 0xffffffff)
        if r != 0x2001 or w(ad)[0] != v & 0xffffffff: sys.exit(f'POKE {ad:#x} failed')
    curves = [w(CURVE_TAB + 0x48 * i)[0] for i in range(w(CURVE_CNT)[0])]
    tone = CURVE_NEW in curves
    wl = words(lay, asm, tone)
    if a[0] in ('apply', 'restore'):
        back = a[0] == 'restore'
        # tuning area, by word (read-modify-write, every byte checked)
        bywords = {}
        for i, (o, n) in m.items(): bywords.setdefault((DB_RAM + i) & ~3, []).append(((DB_RAM + i) & 3, o, n))
        bad = 0
        for ad, lst in sorted(bywords.items()):
            cur = bytearray(struct.pack('<I', w(ad)[0])); new = bytearray(cur)
            for off, o, n in lst:
                if cur[off] != (n if back else o): bad += 1; continue
                new[off] = o if back else n
            if new != cur: poke(ad, struct.unpack('<I', new)[0])
        print(f'tuning area: {len(m)} bytes, {bad} skipped (unexpected value)')
        if not back:
            for ad, blob in blobs(lay, asm).items():
                assert all(x == 0xff for x in p.peek(ad, (len(blob) + 3) & ~3)) or p.peek(ad, len(blob)) == blob, 'filler in use'
                for k in range(0, len(blob), 4): poke(ad + k, struct.unpack('<I', blob[k:k + 4].ljust(4, b'\0'))[0])
        skipped = 0
        for ad, o, n in wl:
            cur = w(ad)[0]
            if cur == (n if back else o): poke(ad, o if back else n)
            elif cur != (o if back else n): skipped += 1; print(f'  {ad:#x}: unexpected {cur:#010x}')
        p.peek(0x42000000, 0x200000)                                        # push the written lines out of the D-cache
        r, _, _ = p.op(ptpdebug.CALL, ICACHE_INVALIDATE, 0)
        print(f'blob2: {len(wl)} words, {skipped} skipped; I-cache invalidate -> {r:#06x}')
        if back:
            for ad, blob in blobs(lay, asm).items():
                for k in range(0, (len(blob) + 3) & ~3, 4): poke(ad + k, 0xffffffff)
    # status
    sel = {i: w((DB_RAM + i) & ~3)[0] >> 8 * ((DB_RAM + i) & 3) & 0xff for i in (0xdd26, 0xe4a0, SEL_ALT3, SEL_ALT2, 0xdf92, 0xde37, 0xe4ec, 0xffc6, 0xdf91)}
    print('selectors 3x3/2x2/alt3/alt2:', [sel[i] for i in (0xdd26, 0xe4a0, SEL_ALT3, SEL_ALT2)],
          ' fam5 curves:', [sel[0xdf92], sel[0xde37]], ' NegHi gain/detail/curve:', [sel[0xe4ec], sel[0xffc6], sel[0xdf91]])
    print('curve 38 in blob1:', tone, ' patched sites:', sum(1 for ad, o, n in wl if w(ad)[0] == n), '/', len(wl),
          ' fsim6 colour mode:', w(CM_FSIM6)[0])
    p.op(0x1003)


if __name__ == '__main__':
    main(sys.argv[1:])
