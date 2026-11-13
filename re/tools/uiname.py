"""Rename a film simulation in the X-Pro1 menus (default: PRO Neg. Hi → CLASSIC CHROME).

UI text lives in 35 language blocks of 0x20000 bytes each (file 0x104025c + n*0x20000, flash 0x1040000 + n*0x20000;
resource table in blob1 around 0x84bd1c: {flash offset, 1 block, RAM 0x4f0000}). The block of the selected language
is loaded whole to RAM 0x4f0000. A block is self-contained: packed NUL-terminated UTF-16LE strings (4-byte aligned),
12-byte text descriptors {u32 string pointer, u16 100, u16 100, u32 alignment} and a table of pointers to the
descriptors, all as absolute RAM addresses. Each block has three "PRO Neg. Hi" strings (one with the icon U+F201
before the name, or after it in the three right-to-left languages), each used by exactly one descriptor. The
strings have no spare room, but every block ends with at least 0xdb00 unused 0xff bytes. The new name is written
there and the three descriptors are pointed at it:

    tail (16-aligned, 16 bytes after the last used byte):
      'UINM', u32 record count, count x {u32 descriptor offset, u32 original pointer}, then the new strings

The original strings stay in place, so `restore` only needs the tail. Icons, EXIF (FilmMode "Pro Neg. Hi") and the
ASCII debug names in module 0x41 are not changed.

usage (run with ~/.venvs/xpro1-re/bin/python):
  uiname.py show                 live: the film-simulation name the camera currently shows (needs the USB debug firmware)
  uiname.py set [NAME]           live: rename in RAM (default CLASSIC CHROME). Lasts until the battery is removed or
                                 the menu language is changed
  uiname.py restore              live: back to PRO Neg. Hi
  uiname.py check FPUPDATE.DAT   offline: report what each language block of an update file holds
  uiname.py selftest             offline test on the official firmware in the repository root
Firmware builds use patch_image() (see build_cc3.py).
"""
import os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
RAM = 0x4f0000                       # every language block is linked for and loaded to this address
BLOCK = 0x20000
FILE0 = 0x104025c                    # first block (Japanese) in the update file; English is block 1
NBLOCKS = 35
OLD = 'PRO Neg. Hi'
NEW = 'CLASSIC CHROME'
MAGIC = b'UINM'
DESC = b'd\0d\0'                     # descriptor words 2-3: 100 %, 100 %


def _w(b, o): return struct.unpack('<I', b[o:o + 4])[0]


def find_tail(blk):
    """Offset of an existing rename tail, or None."""
    used = len(bytes(blk).rstrip(b'\xff'))
    for m in re.finditer(re.escape(MAGIC), bytes(blk[:used])):
        o = m.start()
        if o % 16 == 0 and all(x == 0xff for x in blk[o - 16:o]): return o
    return None


def unpatch(blk):
    """Undo a rename in a block image (bytearray). Returns True if there was one."""
    t = find_tail(blk)
    if t is None: return False
    n = _w(blk, t + 4); assert 1 <= n <= 8, 'rename tail damaged'
    for k in range(n):
        d, ptr = struct.unpack('<II', blk[t + 8 + 8 * k:t + 16 + 8 * k])
        assert blk[d + 4:d + 8] == DESC, 'rename tail damaged'
        blk[d:d + 4] = struct.pack('<I', ptr)
    end = len(bytes(blk).rstrip(b'\xff'))
    blk[t:end] = b'\xff' * (end - t)
    return True


def find_recs(blk, old=OLD):
    """The text descriptors that show `old` in an unpatched block: [(descriptor offset, string pointer, full text)]."""
    used = len(bytes(blk).rstrip(b'\xff'))
    enc = old.encode('utf-16le')
    recs = []                                                   # (descriptor offset, original pointer, full text)
    pua = lambda t: all(0xe000 <= ord(c) <= 0xf8ff for c in t) and len(t) <= 1
    for m in re.finditer(re.escape(enc), bytes(blk[:used])):
        s = m.start()
        if s % 2: continue
        e = s + len(enc)
        while blk[e:e + 2] != b'\0\0': e += 2
        s &= ~3                                                 # strings start 4-aligned: at most one character before
        text = blk[s:e].decode('utf-16le'); pre, _, suf = text.partition(old)
        assert pua(pre) and pua(suf), f'unexpected text around the name: {text!r}'   # icon before (or after: RTL)
        ptr = struct.pack('<I', RAM + s)
        ds = [x.start() for x in re.finditer(re.escape(ptr), bytes(blk[:used]))
              if x.start() % 4 == 0 and blk[x.start() + 4:x.start() + 8] == DESC]
        assert len(ds) == 1, f'string at {s:#x}: {len(ds)} descriptors (expected 1)'
        recs.append((ds[0], RAM + s, text))
    assert len(recs) == 3, f'{len(recs)} "{old}" strings (expected 3)'
    return recs


def patch(blk, new=NEW, old=OLD):
    """Rename `old` to `new` in one language block image (bytearray, linked at RAM). Returns the descriptor offsets."""
    assert len(blk) == BLOCK
    unpatch(blk)
    if new == old: return []
    assert new and all(0x20 <= ord(c) < 0x7f for c in new) and len(new) <= 24, 'name: 1-24 printable ASCII characters'
    used = len(bytes(blk).rstrip(b'\xff'))
    recs = find_recs(blk, old)
    tail = ((used + 15) & ~15) + 16
    body = MAGIC + struct.pack('<I', len(recs)) + b''.join(struct.pack('<II', d, p) for d, p, _ in recs)
    where = {}
    for text in sorted({r[2] for r in recs}):
        where[text] = tail + len(body)
        s = text.replace(old, new).encode('utf-16le') + b'\0\0'
        body += s + b'\0' * (-len(s) % 4)
    assert tail + len(body) + 16 <= BLOCK and all(x == 0xff for x in blk[used:]), 'no free space at the end of the block'
    blk[tail:tail + len(body)] = body
    for d, _, text in recs: blk[d:d + 4] = struct.pack('<I', RAM + where[text])
    return [d for d, _, _ in recs]


def current(blk, old=OLD):
    """The name the three descriptors show now (None if the block has no such strings)."""
    t = find_tail(blk)
    if t is None:
        return old if old.encode('utf-16le') + b'\0\0' in bytes(blk) else None
    d = _w(blk, t + 8); s = _w(blk, d) - RAM; e = s
    while blk[e:e + 2] != b'\0\0': e += 2
    return ''.join(c for c in blk[s:e].decode('utf-16le') if not 0xe000 <= ord(c) <= 0xf8ff)


def patch_image(img, new=NEW, old=OLD):
    """img: bit-inverted (decoded) update-file image as a bytearray. Renames in all 35 language blocks."""
    n = 0
    for k in range(NBLOCKS):
        a = FILE0 + k * BLOCK; blk = bytearray(img[a:a + BLOCK])
        patch(blk, new, old); img[a:a + BLOCK] = blk; n += 1
    return n


# ---------------------------------------------------------------------------------------------- live (USB)
def _live_apply(dev, before, after, descriptors_last):
    """Poke the words that differ. Order: when renaming, the tail first and the descriptor pointers last; when
    restoring, the pointers first. The menu therefore never follows a pointer to an unfinished string."""
    words = [o for o in range(0, BLOCK, 4) if before[o:o + 4] != after[o:o + 4]]
    t = find_tail(after) if descriptors_last else find_tail(before)
    is_tail = lambda o: t is not None and o >= t
    words.sort(key=lambda o: (is_tail(o) != descriptors_last, o) if descriptors_last else (is_tail(o), o))
    for o in words: dev.poke(RAM + o, _w(after, o))
    back = dev.peek(RAM, BLOCK)
    assert back == bytes(after), 'read-back mismatch'
    return len(words)


def live(cmd, new=NEW):
    import tune
    dev = tune.USB()
    blk = bytearray(dev.peek(RAM, BLOCK))
    now = current(blk)
    if now is None: sys.exit('no film-simulation strings at RAM 0x4f0000 (not the 3.82-based firmware?)')
    if cmd == 'show':
        print(f'the menu shows: {now!r}' + ('' if find_tail(blk) is None else '   (renamed live or by the firmware build)'))
        return
    after = bytearray(blk)
    if cmd == 'set': patch(after, new)
    else: unpatch(after)
    if after == blk: print(f'nothing to do: the menu already shows {now!r}'); return
    n = _live_apply(dev, blk, after, descriptors_last=(cmd == 'set'))
    print(f'{now!r} → {current(after)!r}: {n} words written and read back (RAM only)')


# ---------------------------------------------------------------------------------------------- offline
def check(path):
    raw = open(path, 'rb').read()
    names = {}
    for k in range(NBLOCKS):
        a = FILE0 + k * BLOCK; blk = bytes(255 - x for x in raw[a:a + BLOCK])
        names.setdefault(current(blk), []).append(k)
    for nm, ks in names.items(): print(f'{len(ks):2d} language blocks show {nm!r}')
    return names


def selftest():
    raw = open(os.path.join(ROOT, 'FPUPDATE.DAT'), 'rb').read()
    img = bytearray(255 - x for x in raw); stock = bytes(img)
    assert patch_image(img) == NBLOCKS
    diff = [i for i in range(len(img)) if img[i] != stock[i]]
    assert all(FILE0 <= i < FILE0 + NBLOCKS * BLOCK for i in diff)
    for k in range(NBLOCKS):
        a = FILE0 + k * BLOCK; blk = bytearray(img[a:a + BLOCK]); org = stock[a:a + BLOCK]
        assert current(blk) == NEW and current(org) == OLD
        used = len(org.rstrip(b'\xff')); t = find_tail(blk)
        ch = [i for i in range(BLOCK) if blk[i] != org[i]]
        descs = sorted({i & ~3 for i in ch if i < used})
        assert len(descs) == 3 and all(org[d + 4:d + 8] == DESC for d in descs), 'only three descriptor pointers change'
        assert all(i >= t for i in ch if i >= used) and t >= used + 16
        for d in descs:                                          # follow each descriptor like the firmware does
            s = _w(blk, d) - RAM; o = _w(org, d) - RAM; e = s
            while blk[e:e + 2] != b'\0\0': e += 2
            got = blk[s:e].decode('utf-16le'); eo = o
            while org[eo:eo + 2] != b'\0\0': eo += 2
            assert got == org[o:eo].decode('utf-16le').replace(OLD, NEW) and s % 4 == 0 and e + 2 <= BLOCK
        patch(blk, 'Classic Chrome'); assert current(blk) == 'Classic Chrome'          # rename again
        assert unpatch(blk) and bytes(blk) == org, 'restore gives the original block'
    # live ordering on a fake camera
    class Fake:
        def __init__(s, b): s.b = bytearray(b); s.log = []
        def peek(s, a, n): return bytes(s.b[a - RAM:a - RAM + n])
        def poke(s, a, v): s.b[a - RAM:a - RAM + 4] = struct.pack('<I', v); s.log.append(a - RAM)
    org = stock[FILE0 + BLOCK:FILE0 + 2 * BLOCK]; f = Fake(org); after = bytearray(org); ds = patch(after)
    _live_apply(f, bytearray(org), after, True)
    assert sorted(f.log[-3:]) == sorted(ds), 'descriptor pointers are written last'
    f.log.clear(); back = bytearray(after); unpatch(back); _live_apply(f, after, back, False)
    assert sorted(f.log[:3]) == sorted(ds) and bytes(f.b) == org, 'restore: pointers first, block = original'
    print(f'selftest OK ({NBLOCKS} language blocks, {len(diff)} bytes differ in the image)')


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a or a[0] in ('-h', '--help'): sys.exit(__doc__)
    sys.path.insert(0, HERE)
    if a[0] == 'selftest': selftest()
    elif a[0] == 'check': check(a[1])
    elif a[0] in ('show', 'restore'): live(a[0])
    elif a[0] == 'set': live('set', a[1] if len(a) > 1 else NEW)
    else: sys.exit(__doc__)
