# Section-0 exception reporter for the SD chain boot (diagnostic; one camera question). Uses keystone.
#
# Question: what stops section 0 between its entry (0x40020) and its first call into blob1 (0x40bac)?
# Static analysis + emulation (2026-11-08) show that path never polls hardware and keeps IRQ/FIQ masked; its only
# device accesses are the interrupt controller at 0xfffb3xxx. Every exception taken there goes to 0x40dd0, which logs
# and then spins forever (flag 0x4004d7a0 is still 0), i.e. a silent hang. This build replaces section 0's exception
# handlers with an LED reporter until stage B is reached, so a hang caused by an exception becomes readable.
#
# Layout (loader 0xff filler, which nothing touches before 0x40bac; loader_hook uses 0x9000-0x93ff):
#   PRE  0xa000  at the loader's final jump (0x405c → PRE): save CPU state the boot ROM may have left (SCTLR, MPU
#                region count + enabled regions, BTCM/ATCM region registers, ACTLR) at SAVE; point section 0's vector
#                literal pool (0x400e0..0x400f8, copied by its entry to 0x24..0x3c) at our traps; continue with
#                loader_hook stage A (0x9000; ORANGE flash), which jumps to section 0.
#   RESTORE      called by loader_hook stage B: puts section 0's own handlers back into 0x24..0x3c, progress = 2.
#   TRAPS        one per vector: type 1 undef, 2 svc, 3 prefetch abort, 4 data abort, 5 reserved, 6 IRQ, 7 FIQ.
#   REPORT       no stack; caches off; repeats forever: MARK (both LEDs long), then words MSB first, one blink per bit
#                (GREEN 0 / ORANGE 1): progress<<4|type (8) | exception lr (32) | spsr low half (16) | fault status
#                (DFSR, IFSR for prefetch aborts) (16) | fault address (32) | SCTLR (32) | MPU regions (8) |
#                enabled-region bitmap (16) | BTCM region register (32) | stub: ROM aborts drained (8) | their DFSR (16).
# Decode with: led_video.py <video> --layout sec0
import struct
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM

PRE, RESTORE, TRAPS, REPORT, SAVE = 0xa000, 0xa400, 0xa500, 0xa600, 0xaf00
# SAVE + 0 SCTLR, 4 MPUIR, 8 enabled-region bitmap, 12 BTCM, 16 ATCM, 20 ACTLR, 24 progress (1 = PRE ran,
# 2 = stage B reached; | 8 = pool check failed, traps not installed)
POOL = 0x400e0                      # section 0 literals → vector slots 0x24..0x3c (core 0)
POOL_OLD = [0x40100, 0x401a8, 0x4011c, 0x4013c, 0x4015c, 0x40228, 0x40178]
SLOTS = list(range(0x24, 0x40, 4))  # undef, svc, pabt, dabt, reserved, irq, fiq
STUB_ABSORBED = 0x41f60004          # stub .bss: absorbed[0] count, absorbed[1] DFSR (re/sdchain, chain_quiet.bin)
TYPES = {1: 'undefined instruction', 2: 'svc', 3: 'prefetch abort', 4: 'data abort', 5: 'reserved vector',
         6: 'IRQ', 7: 'FIQ'}
FIELDS = [('progress_type', 8), ('lr', 32), ('spsr', 16), ('fsr', 16), ('far', 32), ('sctlr', 32),
          ('mpu_regions', 8), ('mpu_enabled', 16), ('btcm', 32), ('rom_aborts', 8), ('rom_abort_dfsr', 16)]
BIT_DELAY = 0x001b0000 // 2         # same unit as loader_trace.py (~0.14 s per phase with caches off)


def patch(L, S0):
    """L: loader image (bytearray, already patched by loader_hook.patch with stage_b_call=RESTORE).
    S0: section 0 image as loaded at 0x40000 (only checked here; the pool is patched at run time, in RAM)."""
    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)
    asm = lambda src, at: bytes(ks.asm(src, at)[0])
    imm = lambda reg, v: f'movw {reg}, #{v & 0xffff}\n    movt {reg}, #{v >> 16}'
    word = lambda b, a: struct.unpack('<I', b[a:a + 4])[0]
    assert all(b == 0xff for b in L[0xa000:0xb000]), 'trap area is not free filler'
    assert [word(S0, POOL - 0x40000 + 4 * i) for i in range(7)] == POOL_OLD, 'section 0 vector pool differs'
    assert word(L, 0x405c) == 0xea000000 | (((0x9000 - 0x405c - 8) >> 2) & 0xffffff), 'loader_hook stage A not installed'
    at = {}
    pool_patch = ''.join(f'''
    {imm('r1', POOL + 4 * i)}
    ldr r2, [r1]
    {imm('r3', POOL_OLD[i])}
    cmp r2, r3
    orrne r6, r6, #8''' for i in range(7))
    pool_write = ''.join(f'''
    {imm('r1', POOL + 4 * i)}
    {imm('r2', TRAPS + 8 * i)}
    str r2, [r1]
    mcr p15, 0, r1, c7, c10, 1''' for i in range(7))
    pre = asm(f'''
    push {{r0, r1, r2, r3, r4, r5, r6, r12, lr}}
    {imm('r12', SAVE)}
    mrc p15, 0, r0, c1, c0, 0
    str r0, [r12]
    mrc p15, 0, r1, c0, c0, 4
    str r1, [r12, #4]
    ubfx r2, r1, #8, #8
    cmp r2, #16
    movhi r2, #16
    mov r3, #0
    mov r4, #0
rg: cmp r3, r2
    bhs rd
    mcr p15, 0, r3, c6, c2, 0
    isb
    mrc p15, 0, r5, c6, c1, 2
    and r5, r5, #1
    orr r4, r4, r5, lsl r3
    add r3, r3, #1
    b rg
rd: str r4, [r12, #8]
    mrc p15, 0, r0, c9, c1, 0
    str r0, [r12, #12]
    mrc p15, 0, r0, c9, c1, 1
    str r0, [r12, #16]
    mrc p15, 0, r0, c1, c0, 1
    str r0, [r12, #20]
    mov r6, #1
    {pool_patch}
    tst r6, #8
    bne pd
    {pool_write}
pd: str r6, [r12, #24]
    dsb
    pop {{r0, r1, r2, r3, r4, r5, r6, r12, lr}}
    b 0x9000''', PRE)
    assert PRE + len(pre) <= RESTORE, len(pre)
    L[PRE:PRE + len(pre)] = pre
    restore = asm(''.join(f'''
    {imm('r1', SLOTS[i])}
    {imm('r2', POOL_OLD[i])}
    str r2, [r1]''' for i in range(7)) + f'''
    {imm('r1', SAVE)}
    ldr r2, [r1, #24]
    bic r2, r2, #7
    orr r2, r2, #2
    str r2, [r1, #24]
    dsb
    bx lr''', RESTORE)
    assert RESTORE + len(restore) <= TRAPS, len(restore)
    L[RESTORE:RESTORE + len(restore)] = restore
    traps = b''.join(asm(f'mov r4, #{k}\n    b {REPORT:#x}', TRAPS + 8 * (k - 1)) for k in range(1, 8))
    L[TRAPS:TRAPS + len(traps)] = traps
    u = BIT_DELAY
    send = f'''
r_send:
    sub r1, r1, #1
    lsr r2, r0, r1
    tst r2, #1
    movw r3, #0x0001
    movwne r3, #0x0004
    movt r3, #0x0005
    str r3, [r11]
    {imm('r12', u)}
s1: subs r12, r12, #1
    bne s1
    {imm('r3', 0x00050005)}
    str r3, [r11]
    {imm('r12', u)}
s2: subs r12, r12, #1
    bne s2
    cmp r1, #0
    bne r_send
    {imm('r12', u * 3)}
s3: subs r12, r12, #1
    bne s3
    bx lr
r_mark:
    {imm('r3', 0x00050000)}
    str r3, [r11]
    {imm('r12', u * 4)}
m1: subs r12, r12, #1
    bne m1
    {imm('r3', 0x00050005)}
    str r3, [r11]
    {imm('r12', u * 2)}
m2: subs r12, r12, #1
    bne m2
    bx lr'''
    def sw(src, bits):                     # send a word: src = register or SAVE offset expression
        return f'''
    {src}
    mov r1, #{bits}
    bl r_send'''
    report = asm(f'''
    mov r9, lr
    mrs r10, spsr
    mrc p15, 0, r7, c5, c0, 0
    mrc p15, 0, r8, c6, c0, 0
    cmp r4, #3
    mrceq p15, 0, r7, c5, c0, 1
    mrceq p15, 0, r8, c6, c0, 2
    mrc p15, 0, r1, c1, c0, 0
    bic r1, r1, #0x4
    bic r1, r1, #0x1000
    mcr p15, 0, r1, c1, c0, 0
    isb
    {imm('r11', 0xfff893c0)}
    {imm('r6', SAVE)}
loop:
    bl r_mark
    {sw('ldr r0, [r6, #24]' + chr(10) + '    and r0, r0, #15' + chr(10) + '    orr r0, r4, r0, lsl #4', 8)}
    {sw('mov r0, r9', 32)}
    {sw('mov r0, r10', 16)}
    {sw('mov r0, r7', 16)}
    {sw('mov r0, r8', 32)}
    {sw('ldr r0, [r6]', 32)}
    {sw('ldr r0, [r6, #4]' + chr(10) + '    ubfx r0, r0, #8, #8', 8)}
    {sw('ldr r0, [r6, #8]', 16)}
    {sw('ldr r0, [r6, #12]', 32)}
    {sw(imm('r0', STUB_ABSORBED) + chr(10) + '    ldr r0, [r0]', 8)}
    {sw(imm('r0', STUB_ABSORBED) + chr(10) + '    ldr r0, [r0, #4]', 16)}
    {imm('r12', u * 6)}
p:  subs r12, r12, #1
    bne p
    b loop
{send}''', REPORT)
    assert REPORT + len(report) <= SAVE, len(report)
    L[REPORT:REPORT + len(report)] = report
    L[SAVE:SAVE + 0x20] = bytes(0x20)
    L[0x405c:0x4060] = asm(f'b {PRE:#x}', 0x405c)
    return {'pre': PRE, 'restore': RESTORE, 'traps': TRAPS, 'report': REPORT, 'save': SAVE}


def decode(words):
    """words: list of ints in FIELDS order → dict with readable fields."""
    d = dict(zip([n for n, _ in FIELDS], words))
    d['type'] = TYPES.get(d['progress_type'] & 15, d['progress_type'] & 15)
    d['progress'] = {1: 'section 0 started (stage B not reached)', 2: 'after stage B'}.get(d['progress_type'] >> 4 & 7,
                                                                                         d['progress_type'] >> 4)
    return d
