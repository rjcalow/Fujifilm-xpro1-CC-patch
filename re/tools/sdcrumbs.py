"""Read the SD-boot breadcrumbs (crumbs.py layout) over USB after the shutter-triggered flash boot.

usage: ~/.venvs/xpro1-re/bin/python re/tools/sdcrumbs.py [read] [--save FILE] | decode FILE
Needs the debug firmware (ptpdebug) on the camera, and the camera must NOT have been switched off or had its battery
removed since the SD-boot attempt (that clears DRAM).
Verdicts: magic present → DRAM survived and the record tells how far the SD-booted firmware got; magic absent and the
block shows the 00/ff power-up pattern → DRAM did not survive the restart (power was cut).
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crumbs as C

TYPES = {1: 'undefined instruction', 3: 'prefetch abort', 4: 'data abort'}


def where(a):
    for lo, hi, n in ((0x0, 0x40000, 'stock loader'), (0x40000, 0x4d7a0, 'section 0'), (0xd0000, 0xdd760, 'section 1'),
                      (0x774000, 0x9c89c0, 'blob1'), (0xe0ec80, 0x11ea780, 'blob2'), (0x1420000, 0x16a0000, 'modules'),
                      (0x80000000, 0x80004000, 'boot ROM')):
        if lo <= a < hi: return n
    return 'other'


def sdhci(v):
    ps, hc, clk, ist, ien, sig = v
    out = [f'present state {ps:#010x} (cmd inhibit {ps & 1}, dat inhibit {ps >> 1 & 1}, dat active {ps >> 2 & 1}, '
           f'card {"in" if ps >> 16 & 1 else "out"})',
           f'host/power {hc:#010x} (bus power {"on" if hc >> 8 & 1 else "off"})',
           f'clock/reset {clk:#010x} (int clock {clk & 1}, stable {clk >> 1 & 1}, SD clock {clk >> 2 & 1}, '
           f'reset bits {clk >> 24 & 7:#x})',
           f'int status {ist:#010x} (normal {ist & 0xffff:#06x}, error {ist >> 16:#06x})',
           f'int status enable {ien:#010x}, signal enable {sig:#010x}'
           + ('  ← SD interrupt line can be asserted' if (ist & sig & 0xffff7fff) else '')]
    return out


def snapshot(b, off, title, stub):
    w = lambda i: struct.unpack('<I', b[off + 4 * i:off + 4 * i + 4])[0]
    print(f'  {title}: cpsr {w(0):#x} (mode {w(0) & 0x1f:#x}, IRQ {"masked" if w(0) & 0x80 else "on"}, '
          f'A {"masked" if w(0) & 0x100 else "on"}), SCTLR {w(1):#010x}, MPU regions {(w(2) >> 8) & 0xff}, '
          f'enabled {w(3):#06x}')
    if stub: print(f'    pending ROM aborts drained: {w(4)} (DFSR {w(5):#x})')
    regs = [w(6 + i) for i in range(len(C.SNAP_REGS))]
    for name, v in zip(C.SNAP_NAMES[:3], regs[:3]): print(f'    {name}: {v:#010x}')
    for line in sdhci(regs[3:9]): print('    SDHCI0 ' + line)
    print('    intc', ' '.join(f'{v:08x}' for v in regs[9:]))


def decode(b):
    w = lambda o: struct.unpack('<I', b[o:o + 4])[0]
    if w(0) != C.MAGIC:
        words = struct.unpack('<256I', b)
        near = lambda v: min(bin(v).count('1'), 32 - bin(v).count('1')) <= 2     # ≤ 2 bits off 00000000/ffffffff
        pattern = sum(near(v) for v in words) >= 0.95 * len(words)                # DRAM power-up stripes + flips
        print('NO BREADCRUMBS.', 'The block shows the DRAM power-up pattern: DRAM did NOT survive the restart '
              '(power was cut), or the SD boot never reached the stub.' if pattern else
              'The block was overwritten by something else (no power-up pattern either).')
        return
    print('BREADCRUMBS FOUND: DRAM survived the restart.')
    bits, last = w(0x14), w(0x10)
    print('  progress:', ' → '.join(f'{c:#04x}' for c, _ in C.CODES if bits >> C.BIT[c] & 1))
    name = dict(C.CODES).get(last, '?')
    print(f'  last checkpoint {last:#04x}: {name}')
    nxt = [n for c, n in C.CODES if C.BIT[c] == C.BIT.get(last, -1) + 1]
    if nxt: print(f'  ⇒ stopped after "{name}", before "{nxt[0]}"')
    t = w(C.EXC)
    if t:
        lr, spsr, fsr, far, prog, sctlr = (w(C.EXC + 4 * i) for i in range(1, 7))
        print(f'  EXCEPTION: {TYPES.get(t, t)} at lr {lr:#010x} ({where(lr)}), spsr {spsr:#x}, fault status {fsr:#x}, '
              f'address {far:#010x}, progress {prog:#x}, SCTLR {sctlr:#x}; heartbeat {w(C.HEARTBEAT)} (CPU kept running)')
    else:
        print('  no exception recorded' + (' (so the CPU stopped without a fatal exception: stall, wait, or reset)'
                                           if last != 0x24 else ''))
    snapshot(b, C.SNAP_STUB, 'boot-ROM state at stub entry', True)
    if bits >> C.BIT[0x10] & 1: snapshot(b, C.SNAP_PRE, 'state at the loader\'s final jump', False)
    if bits >> C.BIT[0x10] & 1:
        p0, p2 = w(C.KEYS_SEEN), w(C.KEYS_SEEN + 4)
        print(f'  loader key snapshot before the fix: port 0 {p0:#06x} (Fn {"held" if not p0 >> 10 & 1 else "up"}, dial '
              f'{"held" if not p0 >> 11 & 1 else "up"}), port 2 {p2:#06x} (power-on bit 11 = {p2 >> 11 & 1}, POWER {p2 >> 10 & 1})')


def main(a):
    if a and a[0] == 'decode': return decode(open(a[1], 'rb').read()[:0x400])
    import ptpdebug
    p = ptpdebug.PTP(); p.open()
    b = p.peek(C.CRUMB, 0x400); p.op(0x1003)
    if '--save' in a: open(a[a.index('--save') + 1], 'wb').write(b)
    decode(b)


if __name__ == '__main__':
    main(sys.argv[1:])
