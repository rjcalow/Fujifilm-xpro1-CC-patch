# SD chain boot "breadcrumbs": progress, hardware snapshots and exception records written to DRAM instead of the
# LED, read back over USB after the shutter-triggered flash boot (re/tools/sdcrumbs.py). Uses keystone.
#
# Block at CRUMB = 0x43f00000 (DRAM untouched by a normal boot: still the power-up 00/ff pattern after boot + shots,
# mapped 2026-11-11). All addresses ≥ 0x40000000 are non-cacheable under both the ROM's and the loader's MPU;
# every record ends with dsb, so it reaches DRAM even if the next instruction stalls the bus.
#   0x000 'SDCR'  0x004 layout 1  0x010 last progress code  0x014 progress bitmap (bit = CODES index)
#   0x020..0x0ff  written by the stub (re/sdchain/main.c, -DCRUMBS): boot-ROM state at stub entry, drained abort
#   0x100..0x11b  exception record (type, lr, spsr, fsr, far, progress at trap, sctlr); 0x1f0 heartbeat counter
#   0x200..0x2ef  hand-over snapshot at the loader's final jump (same registers as the stub's, after the loader)
#   0x2f0, 0x2f4  GPIO port 0 / port 2 snapshot words as the loader took them (before the power-on key fix)
# Loader image patches (0xff filler 0x9000..0xbfff; nothing writes there before the firmware runs):
#   loader final jump 0x405c → PRE: snapshot, progress 0x10, section 0's fatal vectors → traps, section 0 call sites →
#   checkpoint trampolines, phase-0 call 0x40bac → STAGE_B, then I-cache invalidate and the original `mov pc, r3`.
#   STAGE_B: progress 0x20, puts section 0's svc/reserved/irq/fiq literals back (fatal ones stay trapped), applies the
#   Ver3.89 marker in blob1 (old word checked), then `bx r4` like the original `blx r4`. With cc_img (the decoded
#   update image) it also redirects two blob1 calls to the Classic Chrome hooks at 0xa400 (cchook.py).
#   Traps (undef / prefetch / data abort): if section 0's "resume after exception" flag [0x4004d7a0] is set, chain to
#   section 0's own handler; otherwise write the exception record and count forever at 0x1f0 (no stack, no LED).
import struct
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM

CRUMB = 0x43f00000
MAGIC = 0x52434453                                   # 'SDCR'
CODES = [(0x01, 'stub entry'), (0x02, 'stub: loader inflated + CRC ok'), (0x03, 'stub: abort drained, hand-over'),
         (0x10, 'loader done (final jump)'), (0x11, 'section 0 call 1: 0x40460 handler table'),
         (0x12, 'section 0 call 2: 0x42810(0)'), (0x13, 'section 0 call 3: 0x43db4'),
         (0x14, 'section 0 call 4: 0x43fc0 interrupt-controller init'), (0x15, 'section 0 call 5: 0x40d40 irq 0x5a'),
         (0x20, 'stage B: blob1 phase 0 about to run'), (0x21, 'blob1 phase 1'), (0x22, 'blob1 phase 3'),
         (0x23, 'blob1 phase 2'), (0x24, 'OS start 0x41588')]
BIT = {c: i for i, (c, _) in enumerate(CODES)}
SNAP_REGS = ([0xfff98000, 0xfff98008, 0xfff88084] + [0xfff44000 + o for o in (0x24, 0x28, 0x2c, 0x30, 0x34, 0x38)] +
             [0xfffb3000 + o for o in (0x000, 0x004, 0x008, 0x00c, 0x080, 0x084, 0x088, 0x08c, 0x100, 0x104, 0x108, 0x10c)])
SNAP_NAMES = (['boot ctrl 0xfff98000', 'boot ctrl 0xfff98008', 'power hold 0xfff88084'] +
              [f'SDHCI0 +{o:#04x}' for o in (0x24, 0x28, 0x2c, 0x30, 0x34, 0x38)] +
              [f'intc 0xfffb3{o:03x}' for o in (0x000, 0x004, 0x008, 0x00c, 0x080, 0x084, 0x088, 0x08c, 0x100, 0x104, 0x108, 0x10c)])
# snapshot layout (both the stub's at 0x020 and PRE's at 0x200): +0 cpsr, +4 sctlr, +8 mpuir, +0xc enabled-region
# bitmap, +0x10 drained aborts (stub only), +0x14 drained DFSR (stub only), +0x18.. SNAP_REGS
SNAP_STUB, SNAP_PRE, EXC, HEARTBEAT = 0x020, 0x200, 0x100, 0x1f0
POOL, POOL_OLD = 0x400e0, [0x40100, 0x401a8, 0x4011c, 0x4013c, 0x4015c, 0x40228, 0x40178]
SLOTS = list(range(0x24, 0x40, 4))                   # undef svc pabt dabt reserved irq fiq
FATAL = {0: 1, 2: 3, 3: 4}                           # pool index → trap type (1 undef, 3 prefetch abort, 4 data abort)
RESUME_FLAG = 0x4004d7a0
CALLS = [(0x40b90, 0x40460, 0x11), (0x40b98, 0x42810, 0x12), (0x40b9c, 0x43db4, 0x13), (0x40ba0, 0x43fc0, 0x14),
         (0x40ba4, 0x40d40, 0x15), (0x40c54, 0x41588, 0x24)]           # bl sites
PHASES = [(0x40be4, 0x21), (0x40bec, 0x22), (0x40c1c, 0x23)]           # blx r4 sites (after phase 0)
SITE_B, BLX_R4 = 0x40bac, 0xe12fff34
MARKER = [(0x857a98, 0xe3a03032, 0xe3a03039)]        # blob1: EXIF "Ver3.82" → "Ver3.89"
PRE, REC, TRAPS, TRAP_COMMON, STAGE_B, TRAMPS = 0x9000, 0x9600, 0x9700, 0x9800, 0x9a00, 0x9c00
# Power-on key snapshot fix (2026-11-11). The loader copies the GPIO inputs to BOOTINFO (0x4f58); blob1's start-up
# task 0x85505c decides the power-on cause from snapshot port 2 bit 11 + the live POWER switch / port 0 bit 2 and
# POWERS THE CAMERA OFF (0x7a65fc clears power hold 0xfff88084) when the cause is not valid. Port 2 bit 11 is 1 only
# shortly after power-on (snapshot 0xdd40 vs live 0xd540 in a flash boot); the SD chain reaches the loader seconds
# later. PRE therefore sets it in the snapshot, marks Fn / dial press (port 0 bits 10, 11, active low) as released,
# and keeps the values the loader really saw at CRUMB + KEYS_SEEN (port 0, port 2).
BOOTINFO, KEYS_SEEN, KEYS_P0_SET, KEYS_P2_SET = 0x400a0000, 0x2f0, 0xc00, 0x800
# UI colour swap (2026-11-11, `uiswap=True`): every colour record in the UI resource DB (RAM 0x130000, `00 1b 00 00` +
# RGBA float32, all four ≤ 1.0) gets red and green exchanged, so the red menu accent / info overlays become green.
# Same result as `uicolor.py swaprg`, tested live on the camera. Scans from the end down, because 7 record pairs
# overlap (tag inside the previous record's floats); a backwards scan reproduces the from-the-file plan exactly.
UI_DB, UI_DB_LEN, UI_TAG, UISWAP = 0x130000, 0x215a54, 0x1b00, 0xa000


def patch(L, S0, uiswap=False, cc_img=None):
    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)
    asm = lambda src, at: bytes(ks.asm(src, at)[0])
    imm = lambda r, v: f'movw {r}, #{v & 0xffff}\n    movt {r}, #{v >> 16}'
    w = lambda b, a: struct.unpack('<I', b[a:a + 4])[0]
    s0 = lambda a: w(S0, a - 0x40000)
    bl = lambda frm, to: struct.unpack('<I', asm(f'bl {to:#x}', frm))[0]
    assert all(b == 0xff for b in L[0x9000:0xc000]), 'hook area is not free filler'
    assert w(L, 0x405c) == 0xe1a0f003, 'unexpected loader final jump'
    assert [s0(POOL + 4 * i) for i in range(7)] == POOL_OLD, 'section 0 vector pool differs'
    for site, tgt, _ in CALLS: assert s0(site) == bl(site, tgt), hex(site)
    for site, _ in PHASES + [(SITE_B, 0)]: assert s0(site) == BLX_R4, hex(site)
    put = lambda at, code, limit: (L.__setitem__(slice(at, at + len(code)), code), (at + len(code) <= limit) or
                                   (_ for _ in ()).throw(AssertionError(f'{at:#x} block too large ({len(code)})')))

    # --- REC: r0 = progress code, r1 = bitmap bit; keeps everything else (stack valid at all call sites)
    rec = asm(f'''
    push {{r2, r3, r12}}
    {imm('r2', CRUMB)}
    str r0, [r2, #0x10]
    ldr r3, [r2, #0x14]
    mov r12, #1
    orr r3, r3, r12, lsl r1
    str r3, [r2, #0x14]
    dsb
    pop {{r2, r3, r12}}
    bx lr''', REC)
    put(REC, rec, TRAPS)

    # --- snapshot macro into CRUMB+off (uses r0-r5; r12 = CRUMB+off)
    def snapshot(off):
        regs = ''.join(f'''
    {imm('r1', a)}
    ldr r1, [r1]
    str r1, [r12, #{0x18 + 4 * i}]''' for i, a in enumerate(SNAP_REGS))
        return f'''
    {imm('r12', CRUMB + off)}
    mrs r1, cpsr
    str r1, [r12]
    mrc p15, 0, r1, c1, c0, 0
    str r1, [r12, #4]
    mrc p15, 0, r1, c0, c0, 4
    str r1, [r12, #8]
    ubfx r2, r1, #8, #8
    cmp r2, #16
    movhi r2, #16
    mov r3, #0
    mov r4, #0
sn_loop:
    cmp r3, r2
    bhs sn_done
    mcr p15, 0, r3, c6, c2, 0
    isb
    mrc p15, 0, r5, c6, c1, 2
    and r5, r5, #1
    orr r4, r4, r5, lsl r3
    add r3, r3, #1
    b sn_loop
sn_done:
    str r4, [r12, #0xc]
    {regs}
    dsb'''

    # --- traps: chain to section 0 if its resume flag is set, else record + heartbeat
    traps = b''; trap_at = {}
    for idx, typ in FATAL.items():
        at = TRAPS + len(traps); trap_at[idx] = at
        code = asm(f'''
    push {{r0}}
    {imm('r0', RESUME_FLAG)}
    ldr r0, [r0]
    cmp r0, #0
    pop {{r0}}
    ldrne pc, orig
    mov r4, #{typ}
    b {TRAP_COMMON:#x}
orig: .word {POOL_OLD[idx]:#x}''', at)
        traps += code + bytes(-len(code) % 16)
    put(TRAPS, traps, TRAP_COMMON)
    common = asm(f'''
    mov r9, lr
    mrs r10, spsr
    mrc p15, 0, r7, c5, c0, 0
    mrc p15, 0, r8, c6, c0, 0
    cmp r4, #3
    mrceq p15, 0, r7, c5, c0, 1
    mrceq p15, 0, r8, c6, c0, 2
    {imm('r12', CRUMB)}
    ldr r6, [r12, #0x10]
    str r4, [r12, #{EXC}]
    str r9, [r12, #{EXC + 4}]
    str r10, [r12, #{EXC + 8}]
    str r7, [r12, #{EXC + 12}]
    str r8, [r12, #{EXC + 16}]
    str r6, [r12, #{EXC + 20}]
    mrc p15, 0, r1, c1, c0, 0
    str r1, [r12, #{EXC + 24}]
    dsb
beat:
    ldr r1, [r12, #{HEARTBEAT}]
    add r1, r1, #1
    str r1, [r12, #{HEARTBEAT}]
    dsb
    b beat''', TRAP_COMMON)
    put(TRAP_COMMON, common, STAGE_B)

    # --- trampolines for the checkpointed call sites
    tramps = b''; tramp_at = {}
    for site, tgt, code_ in CALLS:
        at = TRAMPS + len(tramps); tramp_at[site] = at
        t = asm(f'''
    push {{r0, r1, lr}}
    mov r0, #{code_}
    mov r1, #{BIT[code_]}
    bl {REC:#x}
    pop {{r0, r1, lr}}
    b {tgt:#x}''', at)
        tramps += t + bytes(-len(t) % 16)
    for site, code_ in PHASES:
        at = TRAMPS + len(tramps); tramp_at[site] = at
        t = asm(f'''
    push {{r0, r1, lr}}
    mov r0, #{code_}
    mov r1, #{BIT[code_]}
    bl {REC:#x}
    pop {{r0, r1, lr}}
    bx r4''', at)
        tramps += t + bytes(-len(t) % 16)
    put(TRAMPS, tramps, 0xc000)

    # --- STAGE_B (from the patched 0x40bac `bl`): progress 0x20, restore non-fatal literals, marker, bx r4
    restore = ''.join(f'''
    {imm('r1', SLOTS[i])}
    {imm('r2', POOL_OLD[i])}
    str r2, [r1]''' for i in range(7) if i not in FATAL)
    markers = list(MARKER); cc_info = None
    if cc_img is not None:                             # Classic Chrome v3 values + menu name: run-time hooks (cchook.py)
        import cchook
        extra, cc_info = cchook.install(L, cc_img, asm, bl); markers += extra
    marker = ''.join(f'''
    {imm('r1', a)}
    ldr r2, [r1]
    {imm('r3', old)}
    cmp r2, r3
    {imm('r3', new)}
    streq r3, [r1]
    mcreq p15, 0, r1, c7, c10, 1''' for a, old, new in markers)
    if uiswap:
        swap = asm(f'''
    push {{r1, r2, r3, r4, r5, r6, r7, r8, lr}}
    {imm('r2', UI_DB)}
    {imm('r1', UI_DB + (UI_DB_LEN - 20) // 4 * 4)}
    {imm('r8', 0x3f800000)}
sw_loop:
    ldr r3, [r1]
    cmp r3, #{UI_TAG}
    bne sw_next
    ldr r4, [r1, #4]
    ldr r5, [r1, #8]
    ldr r6, [r1, #12]
    ldr r7, [r1, #16]
    cmp r4, r8
    cmpls r5, r8
    cmpls r6, r8
    cmpls r7, r8
    bhi sw_next
    str r5, [r1, #4]
    str r4, [r1, #8]
    add r3, r1, #4
    mcr p15, 0, r3, c7, c10, 1
    add r3, r1, #8
    mcr p15, 0, r3, c7, c10, 1
sw_next:
    sub r1, r1, #4
    cmp r1, r2
    bhs sw_loop
    dsb
    pop {{r1, r2, r3, r4, r5, r6, r7, r8, pc}}''', UISWAP)
        put(UISWAP, swap, 0xa400)
    stage_b = asm(f'''
    push {{r0, r1, r2, r3, lr}}
    mov r0, #0x20
    mov r1, #{BIT[0x20]}
    bl {REC:#x}
    {f'bl {UISWAP:#x}' if uiswap else ''}
    {restore}
    {marker}
    dsb
    mov r1, #0
    mcr p15, 0, r1, c7, c5, 0
    dsb
    isb
    pop {{r0, r1, r2, r3, lr}}
    bx r4''', STAGE_B)
    put(STAGE_B, stage_b, TRAMPS)

    # --- PRE at the loader's final jump (SVC, loader stack valid; r0 = blob1 entry, r3 = section 0 entry)
    site_patches = [(site, s0(site), bl(site, tramp_at[site])) for site, _, _ in CALLS]
    site_patches += [(site, BLX_R4, bl(site, tramp_at[site])) for site, _ in PHASES]
    site_patches += [(SITE_B, BLX_R4, bl(SITE_B, STAGE_B))]
    pool = [(POOL + 4 * idx, POOL_OLD[idx], trap_at[idx]) for idx in FATAL]
    writes = ''.join(f'''
    {imm('r1', a)}
    ldr r2, [r1]
    {imm('r12', old)}
    cmp r2, r12
    {imm('r12', new)}
    streq r12, [r1]
    mcreq p15, 0, r1, c7, c10, 1''' for a, old, new in site_patches + pool)
    pre = asm(f'''
    push {{r0, r1, r2, r3, r4, r5, r12, lr}}
    {snapshot(SNAP_PRE)}
    mov r0, #0x10
    mov r1, #{BIT[0x10]}
    bl {REC:#x}
    {imm('r1', BOOTINFO)}
    {imm('r12', CRUMB + KEYS_SEEN)}
    ldr r2, [r1]
    str r2, [r12]
    orr r2, r2, #{KEYS_P0_SET}
    str r2, [r1]
    ldr r2, [r1, #8]
    str r2, [r12, #4]
    orr r2, r2, #{KEYS_P2_SET}
    str r2, [r1, #8]
    {writes}
    dsb
    mov r1, #0
    mcr p15, 0, r1, c7, c5, 0
    dsb
    isb
    pop {{r0, r1, r2, r3, r4, r5, r12, lr}}
    mov pc, r3''', PRE)
    put(PRE, pre, REC)
    L[0x405c:0x4060] = asm(f'b {PRE:#x}', 0x405c)
    return {'pre': PRE, 'rec': REC, 'traps': trap_at, 'stage_b': STAGE_B, 'tramps': TRAMPS, 'uiswap': uiswap, 'cc': cc_info}
