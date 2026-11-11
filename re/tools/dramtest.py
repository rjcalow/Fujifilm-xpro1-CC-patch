"""DRAM retention control test over USB (debug firmware): does unused DRAM keep data across a given kind of restart?

usage: ~/.venvs/xpro1-re/bin/python re/tools/dramtest.py write | check
  write  POKE a seeded pseudo-random 1 KiB marker into two blocks no normal boot touches, verify by read-back
  check  read both blocks, report the fraction of marker bits still intact (1.00 = survived, ~0.50 = lost)
Between write and check: unplug USB, do ONE kind of restart (power switch off/on, auto power off + shutter, ...),
replug. Purpose: decide whether breadcrumbs in DRAM (crumbs.py, 0x43f00000) can survive at all.
"""
import os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpdebug

BLOCKS = (0x43f00000, 0x46f00000)
WORDS = 256


def marker(addr):
    r = random.Random(addr)
    return [r.getrandbits(32) for _ in range(WORDS)]


def main(a):
    if not a or a[0] not in ('write', 'check'): sys.exit(__doc__)
    p = ptpdebug.PTP(); p.open()
    for addr in BLOCKS:
        want = marker(addr)
        if a[0] == 'write':
            for i, v in enumerate(want):
                r, _, _ = p.op(ptpdebug.POKE, addr + 4 * i, v)
                if r != 0x2001: sys.exit(f'POKE {addr + 4 * i:#x} → {r:#06x}')
        got = struct.unpack(f'<{WORDS}I', p.peek(addr, 4 * WORDS))
        bad = sum(bin(g ^ w).count('1') for g, w in zip(got, want))
        same = sum(g == w for g, w in zip(got, want))
        print(f'{addr:#x}: {1 - bad / (32 * WORDS):.4f} of marker bits intact, {same}/{WORDS} words exact; '
              f'first words {got[0]:08x} {got[1]:08x} (marker {want[0]:08x} {want[1]:08x})')
    p.op(0x1003)


if __name__ == '__main__':
    main(sys.argv[1:])
