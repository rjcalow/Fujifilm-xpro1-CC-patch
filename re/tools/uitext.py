"""UI text by ID from the X-Pro1 language blocks (see NOTES 2026-11-12 night, "menu text").

Each 0x20000-byte language block (file 0x104025c + n*0x20000, loaded to RAM 0x4f0000) holds one ID-indexed table
of 1693 entries {u32 layout (low half width, high half lines), u32 text descriptor}; IDs are the same in every
language, only the table's offset differs (English 0x255c, Japanese 0x923c). The table starts 4 bytes before the
first run of {descriptor, layout} pairs.

usage: uitext.py [LANG] FIRST [COUNT]      (LANG = block number, default 1 = English)
"""
import os, struct, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
RAM, FILE0, BLOCK, N = 0x4f0000, 0x104025c, 0x20000, 1693
_not = None


def block(k):
    global _not
    if _not is None: _not = open(os.path.join(ROOT, 'work', 'not.bin'), 'rb').read()
    return _not[FILE0 + k * BLOCK:FILE0 + (k + 1) * BLOCK]


def base(k):
    """Offset of the text table in language block k."""
    return base_of(block(k))


def base_of(blk):
    """Offset of the text table in a language block image."""
    used = len(bytes(blk).rstrip(b'\xff'))
    w = lambda o: struct.unpack_from('<I', blk, o)[0]
    isp = lambda d: RAM <= d < RAM + used
    o = 0
    while o < used - 8:
        if isp(w(o)) and 0x10000 <= w(o + 4) < 0x80000 and (w(o + 4) & 0xffff) < 0x400:
            s = o; c = 0
            while isp(w(o)) and 0x10000 <= w(o + 4) < 0x80000: o += 8; c += 1
            if c >= 16: return s - 4
        else: o += 4
    raise ValueError('no text table')


def text(k, i):
    """(layout word, text) of text ID i in language block k."""
    blk = block(k); b = base(k)
    lay, d = struct.unpack_from('<II', blk, b + 8 * i)
    p = struct.unpack_from('<I', blk, d - RAM)[0]
    if p == 0: return lay, ''                           # ID 0: descriptor with a null string (empty text)
    p -= RAM; e = p
    while blk[e:e + 2] != b'\0\0': e += 2
    return lay, blk[p:e].decode('utf-16le', 'replace')


if __name__ == '__main__':
    a = [int(x, 0) for x in sys.argv[1:]]
    if not a: sys.exit(__doc__)
    k, first, count = (1, a[0], 1) if len(a) == 1 else (1, a[0], a[1]) if len(a) == 2 else a[:3]
    for i in range(first, first + count):
        lay, t = text(k, i); print(i, hex(i), hex(lay), repr(t))
