# Our own EXR / EXR Pro SD loader (ffboot.bin) with green-LED progress, for the X-Pro1 (firmware 3.82 GPIO layout).
#
# The boot ROM (entered with Fn + command-dial press at power-on) loads ffboot.bin and runs it. This loader:
#   1. copies its body to SRAM 0xfff00800 (ffuser.bin is loaded over DRAM address 0, where ffboot itself lives), stack
#      at 0xfff01ff8;
#   2. green LED ON;
#   3. opens "ffuser.bin" with the ROM file API (open 0x80001a74, read 0x80001b38; size at [[0xfff00000]]+0x20; the ABI
#      fujimod's EXR loader uses), checks the size, reads it in 32 KiB chunks to DRAM 0x40000000+ (= address 0),
#      checks every read count and computes CRC32; the LED TOGGLES every 16 chunks (512 KiB) = progress;
#   4. compares the CRC; success: LED OFF, invalidate I-cache, jump to 0 (the stock loader, preloaded image);
#   5. on any error: endless blink code, N pulses then a pause:
#        1 = open("ffuser.bin") failed   2 = ROM file record missing / size differs
#        3 = read failed / short read    4 = CRC mismatch
# No flash access. Recovery from any state: battery out.
#
# Library use: build(length, crc) -> bytes.  Requires keystone-engine (pip install keystone-engine).
import struct
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM

SRAM = 0xfff00800
STACK = 0xfff01ff8
ROM_OPEN, ROM_READ, ROM_FS = 0x80001a74, 0x80001b38, 0xfff00000
GPIO15 = 0xfff893c0            # port 15 register block; LED = pin 2 (active low), pin 0 = second LED (kept off)
DELAY = 0x00c00000             # busy-loop count for one blink phase (clock unknown: ~0.1-0.5 s)

STAGE0 = '''
    add r0, pc, #{body_rel}
    movw r1, #{sram_lo}
    movt r1, #{sram_hi}
    ldr r2, [pc, #{size_rel}]
copy:
    ldr r3, [r0], #4
    str r3, [r1], #4
    subs r2, r2, #4
    bne copy
    dsb sy
    isb sy
    movw r3, #{stack_lo}
    movt r3, #{stack_hi}
    mov sp, r3
    movw r0, #{sram_lo}
    movt r0, #{sram_hi}
    bx r0
'''

BODY = '''
main:
    sub sp, sp, #16
    bl led_init
{probe_pre_open}    adr r6, config
    adr r0, name
    ldr r3, [r6]
    blx r3
    cmp r0, #0
    movne r0, #1
    bne fail
{probe_post_open}    ldr r3, [r6, #8]
    ldr r3, [r3]
    cmp r3, #0
    moveq r0, #2
    beq fail
    ldr r2, [r3, #0x20]
    ldr r3, [r6, #12]
    cmp r2, r3
    movne r0, #2
    bne fail
    mov r5, #0
    mvn r4, #0
    mov r9, #0
    movw r10, #0x8320
    movt r10, #0xedb8
chunk:
    ldr r3, [r6, #12]
    cmp r5, r3
    bhs loaded
    sub r8, r3, r5
    cmp r8, #0x8000
    movhs r8, #0x8000
    add r7, r5, #0x40000000
    mov r3, #0
    strh r3, [sp]
    mov r0, r7
    mov r1, r8
    mov r2, sp
    ldr r12, [r6, #4]
    blx r12
    cmp r0, #0
    movne r0, #3
    bne fail
    ldrh r3, [sp]
    cmp r3, r8
    movne r0, #3
    bne fail
    mov r0, #0
crcbyte:
    ldrb r2, [r7, r0]
    eor r4, r4, r2
    mov r2, #8
crcbit:
    tst r4, #1
    lsr r4, r4, #1
    eorne r4, r4, r10
    subs r2, r2, #1
    bne crcbit
    add r0, r0, #1
    cmp r0, r3
    blo crcbyte
    add r5, r5, r3
    add r9, r9, #1
    tst r9, #{toggle_mask}
    bne chunk
    bl led_toggle
    b chunk
loaded:
    mvn r4, r4
    ldr r3, [r6, #16]
    cmp r4, r3
    movne r0, #4
    bne fail
    bl led_off
    mov r0, #0
    mcr p15, #0, r0, c7, c5, #0
    dsb sy
    isb sy
    bx r0

fail:
    mov r4, r0
failloop:
    mov r5, r4
pulse:
    bl led_on
    bl delay
    bl led_off
    bl delay
    subs r5, r5, #1
    bne pulse
    bl delay
    bl delay
    bl delay
    bl delay
    b failloop

led_init:
    movw r1, #0x93c0
    movt r1, #0xfff8
    ldr r2, [r1, #0x18]
    bic r2, r2, #0x33
    str r2, [r1, #0x18]
    mov r2, #0x00330000
    str r2, [r1, #0x0c]
    movw r2, #0x0005
    movt r2, #0x0005
    str r2, [r1, #0x08]
    movw r2, #0x0001
    movt r2, #0x0005
    str r2, [r1]
    movw r2, #0x0005
    movt r2, #0x0005
    str r2, [r1, #0x04]
    mov r11, #1
    bx lr

led_on:
    movw r1, #0x93c0
    movt r1, #0xfff8
    mov r2, #0x00040000
    str r2, [r1]
    mov r11, #1
    bx lr

led_off:
    movw r1, #0x93c0
    movt r1, #0xfff8
    movw r2, #0x0004
    movt r2, #0x0004
    str r2, [r1]
    mov r11, #0
    bx lr

led_toggle:
    cmp r11, #0
    beq led_on
    b led_off

delay:
    movw r2, #{delay_lo}
    movt r2, #{delay_hi}
dl:
    subs r2, r2, #1
    bne dl
    bx lr

    .align 2
config:
    .word {rom_open}, {rom_read}, {rom_fs}, {length}, {crc}
name:
    .byte 0x66,0x66,0x75,0x73,0x65,0x72,0x2e,0x62,0x69,0x6e,0x00,0x00
'''


def _asm(src, base):
    code, _ = Ks(KS_ARCH_ARM, KS_MODE_ARM).asm(src, base)
    return bytes(code)


DRAM_BODY, DRAM_STACK = 0x41f00000, 0x41f80000   # high DRAM, above the image (0x40000000-0x416a0000); SRAM untouched


def build(length, crc, probe=False, place='sram'):
    """probe=True: LED on, ~1 phase later OFF just before open(), ON when open() returns, then TOGGLE on every
    32 KiB read (instead of every 512 KiB). Stuck off = open() hangs; stuck on after the off/on = first read hangs."""
    lo, hi = lambda v: v & 0xffff, lambda v: v >> 16
    base, stack = (SRAM, STACK) if place == 'sram' else (DRAM_BODY, DRAM_STACK)
    body = _asm(BODY.format(rom_open=ROM_OPEN, rom_read=ROM_READ, rom_fs=ROM_FS, length=length, crc=crc,
                            delay_lo=lo(DELAY), delay_hi=hi(DELAY), toggle_mask=0 if probe else 15,
                            probe_pre_open='    bl delay\n    bl led_off\n' if probe else '',
                            probe_post_open='    bl led_on\n' if probe else ''), base)
    assert len(body) % 4 == 0 and (place != 'sram' or SRAM + len(body) <= 0xfff01000), 'body exceeds the SRAM window'
    # stage0: 16 instructions (64 bytes), then the size word at 64, body at 68
    s0 = _asm(STAGE0.format(body_rel=68 - 8, size_rel=64 - (12 + 8), sram_lo=lo(base), sram_hi=hi(base),
                            stack_lo=lo(stack), stack_hi=hi(stack)), 0)
    assert len(s0) == 64, len(s0)
    out = s0 + struct.pack('<I', len(body)) + body
    assert len(out) < 0x10000
    return out


if __name__ == '__main__':
    import sys
    b = build(int(sys.argv[1], 0), int(sys.argv[2], 0)); open(sys.argv[3], 'wb').write(b)
    print(len(b), 'bytes')
