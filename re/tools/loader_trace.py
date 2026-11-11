# Trace patches for the X-Pro1 stock boot loader (RAM copy used by the SD chain boot). Uses keystone.
# Checkpoints: before each start-up call the green LED blinks k times (k = 1..8); before each step inside main the
# ORANGE LED blinks k times (k = 1..7); each checkpoint also stores its number (1..8, 9..15) at CP_LAST.
# Exceptions → crash report (caches off first), repeating: MARK = both LEDs on (long), then binary words MSB first,
# one blink per bit, GREEN = 0 / ORANGE = 1: type (4 bits: 1 undef, 2 prefetch abort, 3 data abort) | last checkpoint (8)
# | asynchronous aborts absorbed (8) | exception lr (32) | DFSR/IFSR (16) | DFAR/IFAR (32). Asynchronous data aborts
# (DFSR 0x406 / 0x408) are counted at CP_LAST+4 and resumed instead of reported. Decode videos with led_video.py.
# Loader error handler 0x450c → orange blinking. Final jump to the firmware (0x405c) → green + orange on.
# No stack is used by the trampolines (stacks are not valid during mode setup): registers are saved at 0x9f00.
import struct
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM

T, SAVE, CP_LAST = 0x9000, 0x9f00, 0x9f40
RESET_CALLS = [  # (call site, original instruction, target, conditional?)
    (0x400c, 0xeb000013, 0x4060, False),   # 1 CPU modes
    (0x4010, 0xeb00002b, 0x40c4, False),   # 2 stacks
    (0x402c, 0xeb0000a2, 0x42bc, False),   # 3 after BSS clear: core id
    (0x4034, 0x0b0003c7, 0x4f58, True),    # 4 GPIO / clock / system init (core 0)
    (0x4038, 0xeb00009f, 0x42bc, False),   # 5 after GPIO init
    (0x403c, 0xeb000069, 0x41e8, False),   # 6 MPU + caches on
    (0x4040, 0xeb00009d, 0x42bc, False),   # 7 after MPU
    (0x4044, 0xeb0001d6, 0x47a4, False),   # 8 main
]
MAIN_CALLS = [
    (0x4814, None, 0x4cbc, False),          # 1 validity check
    (0x4840, None, 0x4c64, False),          # 2 init (0x5a8c)
    (0x4868, None, 0x44dc, False),          # 3 hardware-ready wait (0xfffa8000 bit 26)
    (0x486c, None, 0x4668, False),          # 4 section table from flash
    (0x4884, None, 0x4760, False),          # 5 sections from flash
    (0x48c8, None, 0x468c, False),          # 6
    (0x48dc, None, 0x4ca8, False),          # 7
]
GREEN, ORANGE = 0x00040000, 0x00010000      # masked write: pin bit in the upper half, value 0 = LED on (active low)


def patch(L, fast_delay=0x001b0000, slow_delay=0x00d80000):
    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)
    asm = lambda src, at: bytes(ks.asm(src, at)[0])
    word = lambda a: struct.unpack('<I', L[a:a + 4])[0]
    assert all(b == 0xff for b in L[0x8000:0x10000]), 'trampoline area is not free filler'
    for site, old, tgt, cond in MAIN_CALLS:
        w = word(site); assert (w & 0x0f000000) == 0x0b000000, hex(site)
        off = (w & 0xffffff) << 2; off = off - (1 << 26) if off & (1 << 25) else off
        assert site + 8 + off == tgt, (hex(site), hex(site + 8 + off), hex(tgt))
    for site, old, tgt, cond in RESET_CALLS: assert word(site) == old, hex(site)
    assert word(0x405c) == 0xe1a0f003 and word(0x450c) == 0xe92d4800
    assert [word(v) for v in (0x24, 0x2c, 0x30)] == [0x54, 0x58, 0x60], 'unexpected vector literals'
    L[CP_LAST:CP_LAST + 8] = bytes(8)          # last checkpoint, async aborts absorbed
    cur = [T]; at = {}
    def emit(name, src):
        code = asm(src, cur[0]); at[name] = cur[0]; L[cur[0]:cur[0] + len(code)] = code
        cur[0] += (len(code) + 15) & ~15
        assert cur[0] < SAVE, 'trampolines overlap the save area'
    imm = lambda reg, v: f'movw {reg}, #{v & 0xffff}\n    movt {reg}, #{v >> 16}'
    def blink(pin, delay):                  # checkpoint blink: r0 = count; clobbers r1, r2, r3, r12; no stack
        return f'''
    mov r3, lr
    {imm('r1', 0xfff893c0)}
n:  {imm('r2', pin)}
    str r2, [r1]
    {imm('r12', delay)}
d1: subs r12, r12, #1
    bne d1
    {imm('r2', pin | (pin >> 16))}
    str r2, [r1]
    {imm('r12', delay)}
d2: subs r12, r12, #1
    bne d2
    subs r0, r0, #1
    bne n
    {imm('r12', delay * 4)}
p:  subs r12, r12, #1
    bne p
    bx r3'''
    emit('blink_green', blink(GREEN, fast_delay))
    emit('blink_orange', blink(ORANGE, slow_delay))
    emit('t_final', f'''
    push {{r1, r2}}
    {imm('r1', 0xfff893c0)}
    mov r2, #0x00050000
    str r2, [r1]
    pop {{r1, r2}}
    mov pc, r3''')
    emit('t_err', f'''
    {imm('r1', 0xfff893c0)}
l:  {imm('r2', 0x00050004)}
    str r2, [r1]
    {imm('r3', slow_delay)}
d1: subs r3, r3, #1
    bne d1
    {imm('r2', 0x00050005)}
    str r2, [r1]
    {imm('r3', slow_delay)}
d2: subs r3, r3, #1
    bne d2
    b l''')
    # ---- crash reporter: binary dump on the LED (no stack; r11 = GPIO15 data register) ----
    # cycle: MARK (both on 4u, off 2u), then words MSB first, one blink per bit (GREEN = 0, ORANGE = 1, 1u on / 1u off),
    # 3u gap after each word: type (4 bits) | last checkpoint (8) | async aborts absorbed (8) | exception lr (32) |
    # fault status DFSR/IFSR (16) | fault address DFAR/IFAR (32); then 6u pause. u = bit_delay loop iterations.
    bit_delay = fast_delay // 2
    emit('r_send', f'''
s:  sub r1, r1, #1
    lsr r2, r0, r1
    tst r2, #1
    movw r3, #0x0001
    movwne r3, #0x0004
    movt r3, #0x0005
    str r3, [r11]
    {imm('r12', bit_delay)}
d1: subs r12, r12, #1
    bne d1
    {imm('r3', 0x00050005)}
    str r3, [r11]
    {imm('r12', bit_delay)}
d2: subs r12, r12, #1
    bne d2
    cmp r1, #0
    bne s
    {imm('r12', bit_delay * 3)}
d3: subs r12, r12, #1
    bne d3
    bx lr''')
    emit('r_mark', f'''
    {imm('r3', 0x00050000)}
    str r3, [r11]
    {imm('r12', bit_delay * 4)}
d1: subs r12, r12, #1
    bne d1
    {imm('r3', 0x00050005)}
    str r3, [r11]
    {imm('r12', bit_delay * 2)}
d2: subs r12, r12, #1
    bne d2
    bx lr''')
    emit('t_report', f'''
    mov r9, lr
    {imm('r1', CP_LAST)}
    ldr r6, [r1]
    ldr r10, [r1, #4]
    mov r7, #0
    mov r8, #0
    cmp r4, #3
    mrceq p15, 0, r7, c5, c0, 0
    mrceq p15, 0, r8, c6, c0, 0
    cmp r4, #2
    mrceq p15, 0, r7, c5, c0, 1
    mrceq p15, 0, r8, c6, c0, 2
    mrc p15, 0, r1, c1, c0, 0
    bic r1, r1, #0x4
    bic r1, r1, #0x1000
    mcr p15, 0, r1, c1, c0, 0
    isb
    {imm('r11', 0xfff893c0)}
rloop:
    bl {{mark}}
    mov r0, r4
    mov r1, #4
    bl {{send}}
    mov r0, r6
    mov r1, #8
    bl {{send}}
    mov r0, r10
    mov r1, #8
    bl {{send}}
    mov r0, r9
    mov r1, #32
    bl {{send}}
    mov r0, r7
    mov r1, #16
    bl {{send}}
    mov r0, r8
    mov r1, #32
    bl {{send}}
    {imm('r12', bit_delay * 6)}
p:  subs r12, r12, #1
    bne p
    b rloop'''.replace('{mark}', f"{at['r_mark']:#x}").replace('{send}', f"{at['r_send']:#x}"))
    for name, kind in (('t_undef', 1), ('t_pabt', 2)):
        emit(name, f'''
    mov r4, #{kind}
    b {at['t_report']:#x}''')
    # data abort: absorb asynchronous (imprecise) aborts and count them; report precise ones
    emit('t_dabt', f'''
    push {{r0, r1, r12}}
    mrc p15, 0, r0, c5, c0, 0
    movw r1, #0x40f
    and r1, r0, r1
    movw r12, #0x406
    cmp r1, r12
    movwne r12, #0x408
    cmpne r1, r12
    bne precise
    {imm('r0', CP_LAST + 4)}
    ldr r1, [r0]
    add r1, r1, #1
    str r1, [r0]
    pop {{r0, r1, r12}}
    subs pc, lr, #8
precise:
    pop {{r0, r1, r12}}
    mov r4, #3
    b {at['t_report']:#x}''')
    for kind, calls, routine, base in (('cpg', RESET_CALLS, 'blink_green', 0), ('cpo', MAIN_CALLS, 'blink_orange', 8)):
        for i, (site, old, tgt, cond) in enumerate(calls, 1):
            emit(f'{kind}{i}', f'''
    movw r12, #{SAVE:#x}
    stm r12, {{r0, r1, r2, r3, lr}}
    movw r1, #{CP_LAST:#x}
    mov r0, #{base + i}
    str r0, [r1]
    mov r0, #{i}
    bl {at[routine]:#x}
    movw r12, #{SAVE:#x}
    ldm r12, {{r0, r1, r2, r3, lr}}
    b {tgt:#x}''')
            L[site:site + 4] = asm(f'{"bleq" if cond else "bl"} {at[f"{kind}{i}"]:#x}', site)
    L[0x405c:0x4060] = asm(f'b {at["t_final"]:#x}', 0x405c)
    L[0x450c:0x4510] = asm(f'b {at["t_err"]:#x}', 0x450c)
    for v, name in ((0x24, 't_undef'), (0x2c, 't_pabt'), (0x30, 't_dabt')):
        L[v:v + 4] = struct.pack('<I', at[name])
    return at
