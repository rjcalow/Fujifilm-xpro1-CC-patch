"""Live call logger for the film-simulation property path (RAM only, USB debug firmware).

Question it answers: when a RAW conversion runs, which code writes the conversion's film simulation, from which
struct, with which value? (The RAW-conversion menu keeps its choice as a film code + COLOR code in 0x9d4d28; the
code that turns those into the film simulation is not found statically, NOTES 2026-11-14/15.)

Each hooked function's first instruction becomes a branch to a stub that appends an entry
{tag, lr, r0, r1, x0, x1, x2, x3} (x = values loaded through r0/r1, per hook) to a ring in the loader filler, then
runs the original instruction and continues. Hooks:
  1 blob1 0x9913a8  set property-struct film sim (+0x3a)   r0 = struct, r1 = MODE_FSIM
  2 blob1 0x98e844  set image bank film sim               r0 = image handle, r1 = MODE_FSIM
  3 blob1 0x98f854  copy a property struct into a bank    r1 = source struct; x0 = its film sim byte +0x3a
  4 blob1 0x98e888  read image bank film sim              r0 = image handle
  5 blob1 0x9bc068  settings -> property struct           r1 = settings; x0..x3 = +0x128 (film sim), +0x12c,
                                                          +0x134 (colour), byte +0x164 (film code)
  9 blob1 0x991390  raw getter of property-struct byte +0x3a   r0 = struct; x0 = the byte
 10 blob1 0x9942e8  clone current bank into bank r0          x0 = current bank index
  8 blob2 0xf38a00  tuning ctx: film sim -> colour mode (+0xc4)   r0 = ctx, r1 = film sim; x0 = caller's saved lr
  7 blob2 0xf99e30  playback job: settings copy from *0x121cb5c   x0 = *0x121cb50 (message), x1 = *0x121cb5c,
                                                          x2 = its +0x128, x3 = its byte +0x164
Ring: index word at 0xc300, entries from 0xc310 (100 x 32 bytes, to 0xcf90). Stubs at 0xbd00 (9 x 0x90). Nothing in flash
changes; a power cycle removes everything.
usage: ~/.venvs/xpro1-re/bin/python re/tools/fsimlog.py install | read | remove
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpdebug

# (tag, site, original word, extra asm: r3 = scratch, r12 = entry pointer; r0/r1 still the call's arguments)
X = lambda slot, src: f'{src}\n    str r3, [r12, #{16 + 4 * slot}]'
HOOKS = [
    (1, 0x9913a8, 0xe92d4800, ''),
    (2, 0x98e844, 0xe92d4830, ''),
    (3, 0x98f854, 0xe92d48f0, X(0, 'ldrb r3, [r1, #0x3a]')),
    (4, 0x98e888, 0xe92d4810, ''),
    (5, 0x9bc068, 0xe92d4ff0, '\n    '.join([X(0, 'ldr r3, [r1, #0x128]'), X(1, 'ldr r3, [r1, #0x12c]'),
                                            X(2, 'ldr r3, [r1, #0x134]'), X(3, 'ldrb r3, [r1, #0x164]')])),
    (7, 0xf99e30, 0xe92d4830, '\n    '.join([
        'movw r3, #0xcb50\n    movt r3, #0x121\n    ldr r3, [r3]\n    str r3, [r12, #16]',
        'movw r3, #0xcb5c\n    movt r3, #0x121\n    ldr r3, [r3]\n    str r3, [r12, #20]',
        'cmp r3, #0\n    ldrne r3, [r3, #0x128]\n    str r3, [r12, #24]',
        'ldr r3, [r12, #20]\n    cmp r3, #0\n    ldrbne r3, [r3, #0x164]\n    str r3, [r12, #28]'])),
    (8, 0xf38a00, 0xe92d4800, X(0, 'ldr r3, [fp]')),
    (9, 0x991390, 0xe52db004, X(0, 'ldrb r3, [r0, #0x3a]')),
    (10, 0x9942e8, 0xe92d4810, X(0, 'movw r3, #0x54a8\n    movt r3, #0xa8\n    ldr r3, [r3]')),
]
STUBS, SLOT, RING, N, ESZ = 0xbd00, 0x90, 0xc300, 100, 32
ICACHE_INVALIDATE = 0x8a5d70
NAMES = {1: 'set struct fsim', 2: 'set bank fsim', 3: 'copy struct->bank', 4: 'read bank fsim',
         5: 'settings->struct', 6: 'settings fsim map', 7: 'playback settings', 8: 'fsim -> colour mode', 9: 'raw +0x3a getter', 10: 'bank clone'}


def stub(asm, tag, site, orig, extra, at):
    return asm(f'''
    push {{r2, r3, r12}}
    movw r2, #{RING & 0xffff}
    movt r2, #{RING >> 16}
    ldr r3, [r2]
    cmp r3, #{N}
    movhs r3, #0
    add r12, r3, #1
    str r12, [r2]
    add r12, r2, #0x10
    add r12, r12, r3, lsl #5
    mov r3, #{tag}
    str r3, [r12]
    str lr, [r12, #4]
    str r0, [r12, #8]
    str r1, [r12, #12]
    {extra}
    pop {{r2, r3, r12}}
    .word {orig:#x}
    b {site + 4:#x}''', at)


def main(a):
    if not a or a[0] not in ('install', 'read', 'remove'): sys.exit(__doc__)
    p = ptpdebug.PTP(); p.open()
    w = lambda ad: struct.unpack('<I', p.peek(ad, 4))[0]
    def poke(ad, v):
        r, _, _ = p.op(ptpdebug.POKE, ad, v & 0xffffffff)
        if r != 0x2001 or w(ad) != v & 0xffffffff: sys.exit(f'POKE {ad:#x} failed')
    def flush():
        p.peek(0x42000000, 0x200000)
        r, _, _ = p.op(ptpdebug.CALL, ICACHE_INVALIDATE, 0)
        if r != 0x2001: sys.exit('I-cache invalidate failed')
    ring_end = RING + 0x10 + N * ESZ
    if a[0] == 'install':
        from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM
        ks = Ks(KS_ARCH_ARM, KS_MODE_ARM); asm = lambda s, at: bytes(ks.asm(s, at)[0])
        for tag, site, orig, _ in HOOKS:
            assert w(site) == orig, f'{site:#x}: unexpected {w(site):#x} (already installed? run remove)'
        assert all(x == 0xff for x in p.peek(STUBS, len(HOOKS) * SLOT)), 'stub area in use'
        assert all(x == 0xff for x in p.peek(RING, ring_end - RING)), 'ring area in use'
        for k in range(0, ring_end - RING, 4): poke(RING + k, 0)
        at = STUBS
        for tag, site, orig, extra in HOOKS:
            code = stub(asm, tag, site, orig, extra, at); assert len(code) <= SLOT, (tag, len(code))
            for k in range(0, len(code), 4): poke(at + k, struct.unpack('<I', code[k:k + 4])[0])
            flush()
            poke(site, struct.unpack('<I', asm(f'b {at:#x}', site))[0]); at += SLOT
        assert at <= RING
        flush()
        print('installed', len(HOOKS), 'hooks; ring cleared')
    elif a[0] == 'remove':
        for tag, site, orig, _ in HOOKS:
            if w(site) != orig: poke(site, orig)
        flush()
        for k in range(0, max(ring_end, 0xd010) - STUBS, 4): poke(STUBS + k, 0xffffffff)   # also older layouts
        print('removed')
    else:
        idx = w(RING); raw = p.peek(RING + 0x10, N * ESZ)
        ent = [struct.unpack('<8I', raw[ESZ * i:ESZ * i + ESZ]) for i in range(N)]
        total = idx
        print('next index', idx, f'(ring of {N} entries; oldest first)')
        for i in list(range(idx, N)) + list(range(idx)):
            tag, lr, r0, r1, *x = ent[i]
            if tag: print(f'  {NAMES.get(tag, tag):18} caller {lr - 4:#010x}  r0 {r0:#010x}  r1 {r1:#010x}  '
                          + ' '.join(f'{v:#x}' for v in x))
    p.op(0x1003)


if __name__ == '__main__':
    main(sys.argv[1:])
