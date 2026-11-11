# Section-0 checkpoints for the SD chain boot (diagnostic; used together with sec0_trap.py). Uses keystone.
#
# Result of the sec0trap card (2026-11-08): stub flicker → stage A ORANGE → nothing (no exception report, no stage B).
# So section 0 stops between its entry and 0x40bac without taking any CPU exception. The only device accesses there
# are the interrupt controller 0xfffb3xxx (routines 4 and 5 below): a stalled bus access would hang without an abort.
#
# Question for the camera: in which of the five start-up routines does section 0 stop, and is the CPU stuck there
# (LED stays lit) or is the camera powered off / reset (LED goes dark)?
# Before each call k (1..5) the GREEN LED blinks k times, then ORANGE stays on steadily while routine k runs.
#   G×k then ORANGE forever      → stuck inside routine k (bus stall or loop)
#   G×k, ORANGE, then dark       → power cut / reset while routine k ran (none of them touches GPIO)
#   G×5, ORANGE, GREEN long, off → stage B reached (loader_hook): section 0 start-up completed
#   MARK + bits                  → exception (sec0_trap report)
# Runs first at the loader's final jump (0x405c → CPI), patches the five `bl` sites of section 0 in RAM (old word
# checked, line cleaned; stage A invalidates the I-cache afterwards), then continues with sec0_trap PRE.
import struct
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM

CPI, CPS = 0xb000, 0xb200
CALLS = [(0x40b90, 0x40460), (0x40b98, 0x42810), (0x40b9c, 0x43db4), (0x40ba0, 0x43fc0), (0x40ba4, 0x40d40)]
NAMES = {1: '0x40460 handler table', 2: '0x42810(0)', 3: '0x43db4', 4: '0x43fc0 VIC init (0xfffb3xxx)',
         5: '0x40d40 VIC source 0x5a'}
UNIT = 0x00a00000                   # loader_hook.DIAG_UNIT: ~0.15-0.2 s per phase with caches on
GPIO15 = 0xfff893c0
G_ON, O_ON, OFF = 0x00050001, 0x00050004, 0x00050005


def patch(L, S0, next_hook):
    """L: loader image (already patched by loader_hook + sec0_trap); S0: section 0 image; next_hook: where to continue
    (sec0_trap.PRE). Re-points the loader's final jump at CPI."""
    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)
    asm = lambda src, at: bytes(ks.asm(src, at)[0])
    imm = lambda reg, v: f'movw {reg}, #{v & 0xffff}\n    movt {reg}, #{v >> 16}'
    word = lambda b, a: struct.unpack('<I', b[a:a + 4])[0]
    assert all(b == 0xff for b in L[CPI:CPI + 0x1000]), 'checkpoint area is not free filler'
    assert word(L, 0x405c) == struct.unpack('<I', asm(f'b {next_hook:#x}', 0x405c))[0], 'expected final jump → PRE'
    for site, tgt in CALLS:
        assert word(S0, site - 0x40000) == struct.unpack('<I', asm(f'bl {tgt:#x}', site))[0], hex(site)
    # blink routine at CPS: r0 = k; GREEN k times, pause, then ORANGE steady. Saves what it uses.
    blink = f'''
    push {{r0, r1, r2, r3, r12, lr}}
    {imm('r3', GPIO15)}
    {imm('r2', OFF)}
    str r2, [r3]
    {imm('r12', UNIT * 2)}
w0: subs r12, r12, #1
    bne w0
b1: {imm('r2', G_ON)}
    str r2, [r3]
    {imm('r12', UNIT)}
w1: subs r12, r12, #1
    bne w1
    {imm('r2', OFF)}
    str r2, [r3]
    {imm('r12', UNIT)}
w2: subs r12, r12, #1
    bne w2
    subs r0, r0, #1
    bne b1
    {imm('r12', UNIT * 2)}
w3: subs r12, r12, #1
    bne w3
    {imm('r2', O_ON)}
    str r2, [r3]
    pop {{r0, r1, r2, r3, r12, lr}}
    bx lr'''
    code = asm(blink, CPS)
    L[CPS:CPS + len(code)] = code
    at = CPS + ((len(code) + 15) & ~15)
    tramps = {}
    for k, (site, tgt) in enumerate(CALLS, 1):
        t = asm(f'''
    push {{r0, lr}}
    mov r0, #{k}
    bl {CPS:#x}
    pop {{r0, lr}}
    b {tgt:#x}''', at)
        L[at:at + len(t)] = t; tramps[site] = at; at += (len(t) + 15) & ~15
    assert at <= CPI + 0x1000
    sites = ''.join(f'''
    {imm('r1', site)}
    ldr r2, [r1]
    {imm('r3', word(S0, site - 0x40000))}
    cmp r2, r3
    {imm('r2', struct.unpack('<I', asm(f'bl {tramps[site]:#x}', site))[0])}
    streq r2, [r1]
    mcr p15, 0, r1, c7, c10, 1''' for site, _ in CALLS)
    cpi = asm(f'''
    push {{r1, r2, r3}}
    {sites}
    dsb
    pop {{r1, r2, r3}}
    b {next_hook:#x}''', CPI)
    assert CPI + len(cpi) <= CPS
    L[CPI:CPI + len(cpi)] = cpi
    L[0x405c:0x4060] = asm(f'b {CPI:#x}', 0x405c)
    return {'cpi': CPI, 'cp_blink': CPS}
