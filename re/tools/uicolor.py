"""Recolour the camera UI live over USB (debug firmware): rewrite colour records in the UI resource DB in RAM.

The UI resource DB (file 0xc8025c, RAM 0x130000, 0x215a54 bytes) holds 2178 GVFF vector graphics (pointer table of
RAM addresses). Colours are records `00 1b 00 00` + RGBA as four float32 in 0..1. Pure red (1,0,0,1) occurs 1701 times.

usage: ~/.venvs/xpro1-re/bin/python re/tools/uicolor.py list                 colour statistics (offline, from the file)
       ... uicolor.py check                                                  compare the live DB in RAM with the file
       ... uicolor.py set R,G,B [--from R,G,B] [--limit N] [--skip N]       rewrite matching records live (default from 1,0,0)
       ... uicolor.py restore                                                write the file's colours back
RAM edits are undone by a battery pull; switch OFF/ON keeps them (standby). Unplug USB to see the result.
"""
import os, struct, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(HERE, '..', 'work', 'not.bin')
DB_FILE, DB_RAM, DB_LEN = 0xc8025c, 0x130000, 0x215a54
TAG = b'\x00\x1b\x00\x00'
F1 = 0x3f800000


def db():
    return open(FILE, 'rb').read()[DB_FILE:DB_FILE + DB_LEN]


def records(d):
    """(offset of the R float, (r, g, b, a) raw words) for every colour record."""
    out = []
    i = d.find(TAG)
    while i >= 0:
        if i % 4 == 0 and i + 20 <= len(d):
            w = struct.unpack_from('<4I', d, i + 4)
            f = struct.unpack_from('<4f', d, i + 4)
            if all(0.0 <= x <= 1.0 for x in f): out.append((i + 4, w))
        i = d.find(TAG, i + 1)
    return out


def fword(x): return struct.unpack('<I', struct.pack('<f', x))[0]
def rgb(s): return tuple(float(v) / (255 if max(map(float, s.split(','))) > 1 else 1) for v in s.split(','))


def main(a):
    if not a: sys.exit(__doc__)
    d = db(); recs = records(d)
    if a[0] == 'list':
        c = collections.Counter(tuple(round(x * 255) for x in struct.unpack('<4f', struct.pack('<4I', *w))) for _, w in recs)
        for t, k in c.most_common(30): print(t, k)
        return
    import ptpdebug
    p = ptpdebug.PTP(); p.open()
    if a[0] == 'check':
        live = p.peek(DB_RAM, DB_LEN)
        diff = sum(1 for i in range(0, DB_LEN, 4) if live[i:i + 4] != d[i:i + 4])
        print(f'live DB vs file: {diff} differing words of {DB_LEN // 4}')
        changed = [o for o, w in recs if live[o:o + 16] != d[o:o + 16]]
        print(f'colour records changed live: {len(changed)} of {len(recs)}')
    elif a[0] in ('set', 'restore', 'swaprg'):
        if a[0] == 'set':
            src = rgb(a[a.index('--from') + 1]) if '--from' in a else (1.0, 0.0, 0.0)
            want = tuple(round(x * 255) for x in src)
            new = tuple(fword(x) for x in rgb(a[1]))
            b8 = lambda w: tuple(round(x * 255) for x in struct.unpack('<3f', struct.pack('<3I', *w[:3])))
            sel = [(o, w) for o, w in recs if b8(w) == want]
            skip = int(a[a.index('--skip') + 1]) if '--skip' in a else 0
            lim = int(a[a.index('--limit') + 1]) if '--limit' in a else len(sel)
            sel = sel[skip:skip + lim]
            plan = [(o + 4 * k, w[k], new[k]) for o, w in sel for k in range(3) if w[k] != new[k]]
        elif a[0] == 'swaprg':                          # every colour record: swap red and green (red → green)
            plan = [(o + 4 * k, w[k], w[1 - k]) for o, w in recs for k in (0, 1) if w[0] != w[1]]
            a[0] = 'set'
        else:
            live = p.peek(DB_RAM, DB_LEN)
            plan = [(o + 4 * k, struct.unpack_from('<I', live, o + 4 * k)[0], w[k]) for o, w in recs for k in range(3)
                    if struct.unpack_from('<I', live, o + 4 * k)[0] != w[k]]
        print(f'{len(plan)} word writes')
        n = 0
        for off, old, val in plan:
            cur = struct.unpack('<I', p.peek(DB_RAM + off, 4))[0] if a[0] == 'set' else old
            if a[0] == 'set' and cur != old: print(f'skip {DB_RAM + off:#x}: live {cur:#x} != file {old:#x}'); continue
            r, _, _ = p.op(ptpdebug.POKE, DB_RAM + off, val)
            if r != 0x2001: sys.exit(f'POKE {DB_RAM + off:#x} → {r:#06x}')
            n += 1
        print(f'done: {n} words written')
    p.op(0x1003)


if __name__ == '__main__':
    main(sys.argv[1:])
