/* SD chain loader entry. The boot ROM loads ffboot.bin at address 0 and jumps to 0.
   Position-independent: copy the whole image (stub + payload) to LINK_BASE in high DRAM, set the stack, jump to main.
   Config block at a fixed offset (0x40) is filled in by build_sdchain.py. */
    .section .text.start, "ax"
    .arm
    .global _start
_start:
    adr     r0, _start              /* where the ROM put us (0) */
    ldr     r1, =_start             /* link address (LINK_BASE) */
    ldr     r2, cfg_image_size
1:  ldr     r3, [r0], #4
    str     r3, [r1], #4
    subs    r2, r2, #4
    bgt     1b
    ldr     r0, =__bss_start        /* zero .bss (separate area, not part of the copied image) */
    ldr     r1, =__bss_end
    mov     r2, #0
2:  cmp     r0, r1
    strlo   r2, [r0], #4
    blo     2b
    dsb
    isb
    ldr     sp, =__stack_top
    ldr     r0, =main
    bx      r0
    .ltorg
    .balign 64
    .global cfg
cfg:                                /* offset 0x40 */
cfg_image_size:   .word 0           /* bytes of ffboot.bin to relocate */
cfg_payload_off:  .word 0           /* offset of the deflate payload inside ffboot.bin */
cfg_payload_len:  .word 0
cfg_out_len:      .word 0           /* decompressed size (0x40000) */
cfg_out_crc:      .word 0           /* CRC32 of the decompressed loader */
cfg_magic:        .word 0x4e494843  /* 'CHIN' */

/* Data-abort handler used only while draining an asynchronous abort the boot ROM left pending (see main.c).
   Runs in abort mode with a stack set up by main.c; records the count and DFSR, returns to the next instruction. */
    .text
    .arm
    .global absorb_dabt
absorb_dabt:
    push    {r0, r1}
    ldr     r0, =absorbed
    ldr     r1, [r0]
    add     r1, r1, #1
    str     r1, [r0]
    mrc     p15, 0, r1, c5, c0, 0
    str     r1, [r0, #4]
    pop     {r0, r1}
    subs    pc, lr, #8
    .ltorg
