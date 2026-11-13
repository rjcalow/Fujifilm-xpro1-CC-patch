"""Live test: load the X-E2 font (has the Classic Chrome icon U+F2B9) over the X-Pro1 font in RAM (debug firmware).

Fonts are "FDL Font" files: X-Pro1 file 0x154025c, 0x81134 bytes, RAM 0x510000; X-E2 (FWUP0004.DAT) file
0x166025c, 0x84294 bytes. RAM after the X-Pro1 font is zero up to the X-E2 size. Only words that differ are written.
RAM only: a power cycle / battery pull reloads the stock font.
usage: ~/.venvs/xpro1-re/bin/python re/tools/fontswap.py xe2 | stock | status
"""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpdebug

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
RAM, XP_OFF, XP_LEN, XE_OFF, XE_LEN = 0x510000, 0x154025c, 0x81134, 0x166025c, 0x84294


def image(name, off, n):
    d = open(os.path.join(ROOT, name), 'rb').read()[off:off + n]
    return bytes(x ^ 0xff for x in d)


def main(a):
    if not a or a[0] not in ('xe2', 'stock', 'status'): sys.exit(__doc__)
    xp = image('FPUPDATE.DAT', XP_OFF, XP_LEN); xe = image('FWUP0004.DAT', XE_OFF, XE_LEN)
    assert xp[:8] == b'FDL Font' and xe[:8] == b'FDL Font'
    n = (XE_LEN + 3) & ~3
    xp = xp.ljust(n, b'\0'); xe = xe.ljust(n, b'\0')
    p = ptpdebug.PTP(); p.open()
    live = p.peek(RAM, n)
    print('font in RAM:', 'X-Pro1 stock' if live == xp else 'X-E2' if live == xe else 'mixed/unknown')
    if a[0] != 'status':
        want = xe if a[0] == 'xe2' else xp
        todo = [i for i in range(0, n, 4) if live[i:i + 4] != want[i:i + 4]]
        print(len(todo), 'words to write'); t = time.time()
        for k, i in enumerate(todo):
            r, _, _ = p.op(ptpdebug.POKE, RAM + i, struct.unpack_from('<I', want, i)[0])
            if r != 0x2001: sys.exit(f'POKE failed at {RAM + i:#x}')
            if k % 20000 == 0: print(f'  {k}/{len(todo)} {time.time() - t:.0f}s', flush=True)
        live = p.peek(RAM, n)
        print('verify:', 'OK' if live == want else 'MISMATCH', f'{time.time() - t:.0f}s')
    p.op(0x1003)


if __name__ == '__main__':
    main(sys.argv[1:])
