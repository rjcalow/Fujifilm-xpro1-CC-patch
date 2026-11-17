"""Menu texts for new entries: repoint unused UI text IDs to new strings, in all 35 language blocks.

The X-Pro1 cannot get new text IDs (the draw code stops at 0x69f), so an unused ID is reused: its descriptor in each
language block is pointed at a string in the block's free tail (cchook.py's language hook writes the tail and the
pointers at run time, every time a language block is loaded). Used by the card through chain.patch(cc_lang=...).

Tail layout (cchook.TAIL_LEN = 0x80): 'UINM', string count, three 8-byte records the hook fills, then one 0x20-byte
slot per string (UTF-16LE, NUL-terminated, at most 15 characters). Hence at most three strings: two per film
simulation (name + icon). A second new film simulation needs a longer tail (cchook.TAIL_LEN and its copy loop).
"""
import struct
from classic_chrome.engine import hooks as cchook

# language blocks: 35 x 0x20000 bytes from file 0x104025c, each loaded to RAM 0x4f0000; text table of N entries
# {u32 layout, u32 descriptor}, same IDs in every language, table offset differs per block (base_of)
RAM, FILE0, BLOCK, N = 0x4f0000, 0x104025c, 0x20000, 1693


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

SLOT = 0x20


def lang(fw, texts):
    """(entries, tail template) for cchook.install(lang=...). texts: {text ID: string}, in slot order."""
    assert len(texts) <= 3, 'at most three repointed texts with the current tail (see module docstring)'
    t = bytearray(cchook.TAIL_LEN)
    t[0:8] = b'UINM' + struct.pack('<I', len(texts)); t[8:0x20] = b'\xff' * 0x18
    offs = {}
    for k, (tid, s) in enumerate(texts.items()):
        off = SLOT * (k + 1); offs[tid] = off
        b = s.encode('utf-16le') + b'\0\0'
        assert len(b) <= SLOT, f'text {tid}: {s!r} longer than 15 characters'
        t[off:off + len(b)] = b
    out = []
    for k in range(35):
        a = FILE0 + k * BLOCK; blk = fw.img[a:a + BLOCK]
        assert all(x == 0xff for x in blk[cchook.TAIL - 16:]), f'language block {k}: tail in use'
        base = base_of(blk)
        for tid, off in offs.items():
            d = struct.unpack_from('<I', blk, base + 8 * tid + 4)[0]
            users = [i for i in range(N) if struct.unpack_from('<I', blk, base + 8 * i + 4)[0] == d]
            # the ID must be the only user of its descriptor, and that descriptor an unused placeholder ('d' 'd')
            assert users == [tid] and blk[d - RAM + 4:d - RAM + 8] == b'd\0d\0', \
                f'language {k}: text ID {tid} is shared or in use'
            out.append((d, struct.unpack_from('<I', blk, d - RAM)[0], RAM + cchook.TAIL + off))
    return out, bytes(t)
