# Production hook for the SD chain boot: patch the firmware in RAM before it runs. Uses keystone.
#
# Boot order (X-Pro1 3.82): stock loader → `mov pc, r3` at 0x405c → section 0 entry 0x40020 (r0 = blob1 entry, from
# [0x67e4]) → section 0 main 0x40b64 calls blob1's entry once per start-up phase (`blx r4` with r0 = 0 at 0x40bac,
# then 1, 3, 2, 4). The loader starts blob1's unpacking (0x4b94) but may jump before it has finished, so blob1 can only
# be patched once section 0 is about to call it.
#
# Stage A (loader final jump, 0x405c → HOOK): if section 0's phase-0 call at 0x40bac is still `blx r4`, replace it
# with `bl STAGE_B`; clean the line, invalidate the I-cache; jump to section 0 as the loader would (`mov pc, r3`).
# Stage B (section 0, just before phase 0): for each (address, old word, new word) in the blob1 table: if *address ==
# old, write new and clean the line; invalidate the I-cache; then `bx r4` (r0 = 0, lr = 0x40bb0 from our `bl`), i.e.
# exactly the original `blx r4`. Both stages run from the loader's unused 0xff filler at 0x9000 (section 0 does not
# use it: its vectors are at 0x24-0x3c, its BSS/stack at 0x4d7a0-0x5a0e0). With diag=True both stages report on the
# LED (see patch()); decode a phone video with led_video.py.
import struct
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM

HOOK, STAGE_B, TABLE, HELP = 0x9000, 0x9100, 0x9200, 0x9300
SITE, SITE_OLD = 0x40bac, 0xe12fff34            # section 0: blx r4 (phase 0 call of blob1)
MARKER = [(0x857a98, 0xe3a03032, 0xe3a03039)]   # blob1 version string "Ver3.82" → "Ver3.89" (EXIF Software)


DIAG_UNIT = 0x00a00000      # busy-loop iterations per LED phase (~0.15-0.2 s once the loader has enabled the caches)


def patch(L, words=MARKER, diag=True, stage_b_call=None):
    """diag: LED feedback for video decoding. Stage A OK → ORANGE short flash; stage B all patches applied → GREEN
    long flash. A failed check sends the word actually found: MARK (both LEDs long) + 32 bits MSB first, one blink per
    bit (GREEN 0 / ORANGE 1). The boot continues either way.
    stage_b_call: optional address that stage B calls (bl) first, after saving its registers (may use r0-r3, r12)."""
    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)
    asm = lambda src, at: bytes(ks.asm(src, at)[0])
    imm = lambda reg, v: f'movw {reg}, #{v & 0xffff}\n    movt {reg}, #{v >> 16}'
    assert struct.unpack('<I', L[0x405c:0x4060])[0] == 0xe1a0f003, 'unexpected loader final jump'
    assert all(b == 0xff for b in L[0x8000:0x10000]), 'hook area is not free filler'
    u = DIAG_UNIT
    # helpers (stack available at both call sites): d_flash(r0 = on value, r1 = units on), d_send(r0 = word)
    helpers = asm(f'''
d_flash:
    push {{r0, r1, r2, r3, r12, lr}}
    {imm('r3', 0xfff893c0)}
    str r0, [r3]
f1: {imm('r12', u)}
f2: subs r12, r12, #1
    bne f2
    subs r1, r1, #1
    bne f1
    {imm('r2', 0x00050005)}
    str r2, [r3]
    {imm('r12', u * 2)}
f3: subs r12, r12, #1
    bne f3
    pop {{r0, r1, r2, r3, r12, lr}}
    bx lr
d_send:
    push {{r0, r1, r2, r3, r4, r12, lr}}
    mov r4, r0
    {imm('r3', 0xfff893c0)}
    {imm('r2', 0x00050000)}
    str r2, [r3]
    {imm('r12', u * 4)}
s1: subs r12, r12, #1
    bne s1
    {imm('r2', 0x00050005)}
    str r2, [r3]
    {imm('r12', u * 2)}
s2: subs r12, r12, #1
    bne s2
    mov r1, #32
s3: sub r1, r1, #1
    lsr r2, r4, r1
    tst r2, #1
    movw r2, #0x0001
    movwne r2, #0x0004
    movt r2, #0x0005
    str r2, [r3]
    {imm('r12', u)}
s4: subs r12, r12, #1
    bne s4
    {imm('r2', 0x00050005)}
    str r2, [r3]
    {imm('r12', u)}
s5: subs r12, r12, #1
    bne s5
    cmp r1, #0
    bne s3
    {imm('r12', u * 4)}
s6: subs r12, r12, #1
    bne s6
    pop {{r0, r1, r2, r3, r4, r12, lr}}
    bx lr''', HELP)
    flash_at, send_at = HELP, HELP + helpers.index(bytes(asm('push {r0, r1, r2, r3, r4, r12, lr}', 0)))
    bl_word = struct.unpack('<I', asm(f'bl {STAGE_B:#x}', SITE))[0]
    signal_a_ok = f'''
    {imm('r0', 0x00050004)}
    mov r1, #2
    bl {flash_at:#x}''' if diag else ''
    signal_a_bad = f'''
    mov r0, r2
    bl {send_at:#x}''' if diag else ''
    stage_a = asm(f'''
    push {{r0, r1, r2, r12, lr}}
    {imm('r1', SITE)}
    ldr r2, [r1]
    {imm('r12', SITE_OLD)}
    cmp r2, r12
    bne a_bad
    {imm('r2', bl_word)}
    str r2, [r1]
    mcr p15, 0, r1, c7, c10, 1
    {signal_a_ok}
    b a_done
a_bad:
    {signal_a_bad}
a_done:
    dsb
    mov r1, #0
    mcr p15, 0, r1, c7, c5, 0
    dsb
    isb
    pop {{r0, r1, r2, r12, lr}}
    mov pc, r3''', HOOK)
    signal_b_ok = f'''
    {imm('r0', 0x00050001)}
    mov r1, #5
    bl {flash_at:#x}''' if diag else ''
    signal_b_bad = f'''
    mov r0, r7
    bl {send_at:#x}''' if diag else ''
    extra_b = f'bl {stage_b_call:#x}' if stage_b_call is not None else ''
    stage_b = asm(f'''
    push {{r0, r1, r2, r3, r5, r6, r7, r8, lr}}
    {extra_b}
    {imm('r3', TABLE)}
    mov r5, #{len(words)}
    mov r8, #0
next:
    ldm r3!, {{r1, r2, r6}}
    ldr r12, [r1]
    cmp r12, r2
    movne r7, r12
    addne r8, r8, #1
    bne skip
    str r6, [r1]
    mcr p15, 0, r1, c7, c10, 1
skip:
    subs r5, r5, #1
    bne next
    cmp r8, #0
    bne b_bad
    {signal_b_ok}
    b b_done
b_bad:
    {signal_b_bad}
b_done:
    dsb
    mov r1, #0
    mcr p15, 0, r1, c7, c5, 0
    dsb
    isb
    pop {{r0, r1, r2, r3, r5, r6, r7, r8, lr}}
    bx r4''', STAGE_B)
    assert HOOK + len(stage_a) <= STAGE_B and STAGE_B + len(stage_b) <= TABLE and TABLE + 12 * len(words) <= HELP
    L[HOOK:HOOK + len(stage_a)] = stage_a
    L[STAGE_B:STAGE_B + len(stage_b)] = stage_b
    L[HELP:HELP + len(helpers)] = helpers
    for i, (a, old, new) in enumerate(words):
        L[TABLE + 12 * i:TABLE + 12 * i + 12] = struct.pack('<3I', a, old, new)
    L[0x405c:0x4060] = asm(f'b {HOOK:#x}', 0x405c)
    return {'hook': HOOK, 'stage_b': STAGE_B, 'table': TABLE, 'flash': flash_at, 'send': send_at, 'words': len(words)}
