"""Live test: label UI text IDs with visible markers to see which ID a screen draws (RAM only, debug firmware).

The current language block is in RAM at 0x4f0000 (English: text table at 0x4f255c, entries {u32 layout,
u32 descriptor}). `apply ID...` writes, for each ID, a new descriptor + string "#<ID>" into the unused 0xff area at
0x4f0000 + AREA and points the table entry at it; the original descriptor pointers are kept in the area header so
`restore` puts them back. A battery pull or a language change also restores everything.
`apply ID=TEXT` writes TEXT instead of the marker (e.g. 819='CLASSIC CHROME').
usage: ~/.venvs/xpro1-re/bin/python re/tools/uitextmark.py apply ID[=TEXT] [...] | restore | show ID [ID...]
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpdebug, uitext

RAM = 0x4f0000
AREA = RAM + 0x1e000           # English block uses < 0x11000; the cchook/uiname tail lives at 0x1f000
MAGIC = 0x4b52414d             # 'MARK'


def w(p, a, n=1): return list(struct.unpack(f'<{n}I', p.peek(a, 4 * n)))


def poke(p, a, v):
    r, _, _ = p.op(ptpdebug.POKE, a, v & 0xffffffff)
    if r != 0x2001: sys.exit(f'POKE {a:#x} failed')


def table(p):
    """Text table base of the language currently in RAM (match against the 35 blocks in the update file)."""
    head = p.peek(RAM, 0x40)
    for k in range(35):
        if uitext.block(k)[:0x40] == head: return k, RAM + uitext.base(k)
    sys.exit('language block in RAM matches no block of the update file')


def text_at(p, desc):
    s = w(p, desc)[0]; d = p.peek(s, 0x80); e = 0
    while d[e:e + 2] != b'\0\0' and e < 0x7e: e += 2
    return d[:e].decode('utf-16le', 'replace')


def main(a):
    if not a: sys.exit(__doc__)
    p = ptpdebug.PTP(); p.open()
    k, tb = table(p)
    hdr = w(p, AREA, 2)
    if a[0] == 'apply':
        if hdr[0] == MAGIC: sys.exit('markers already applied: restore first')
        assert all(x == 0xffffffff for x in w(p, AREA, 0x400)), 'area not free'
        spec = [x.split('=', 1) for x in a[1:]]              # ID or ID=TEXT (\\uXXXX escapes allowed)
        ids = [int(x[0], 0) for x in spec]
        texts = {int(x[0], 0): x[1].encode('ascii', 'backslashreplace').decode('unicode_escape') for x in spec if len(x) == 2}
        rec = AREA + 8; data = AREA + 8 + 8 * len(ids)
        for i in ids:
            old = w(p, tb + 8 * i + 4)[0]
            s = texts.get(i, f'#{i}').encode('utf-16le') + b'\0\0'; s += b'\0' * (-len(s) % 4)
            desc = data; strp = data + 12
            for j, v in enumerate((strp, 0x00640064, 0)): poke(p, desc + 4 * j, v)
            for j in range(0, len(s), 4): poke(p, strp + j, struct.unpack('<I', s[j:j + 4])[0])
            poke(p, rec, i); poke(p, rec + 4, old); rec += 8; data = strp + len(s)
            poke(p, tb + 8 * i + 4, desc)
        poke(p, AREA + 4, len(ids)); poke(p, AREA, MAGIC)
        a = ['show'] + [str(i) for i in ids]
    elif a[0] == 'restore':
        if hdr[0] != MAGIC: sys.exit('nothing to restore')
        for j in range(hdr[1]):
            i, old = w(p, AREA + 8 + 8 * j, 2); poke(p, tb + 8 * i + 4, old)
        for j in range(0x400): poke(p, AREA + 4 * j, 0xffffffff)
        print('restored', hdr[1], 'entries'); p.op(0x1003); return
    print(f'language block {k}, table {tb:#x}')
    for x in a[1:]:
        i = int(x, 0); print(i, repr(text_at(p, w(p, tb + 8 * i + 4)[0])))
    p.op(0x1003)


if __name__ == '__main__':
    main(sys.argv[1:])
