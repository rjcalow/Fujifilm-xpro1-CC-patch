"""Patch engine for the SD-boot card: collects what the feature modules want changed and writes the run-time
tables and hooks that apply it in RAM at every boot. Flash is never written.

A feature is a `Part`. It plans its changes against the stock firmware (`check`), reserves room in the loader's
free filler for its own data and stubs (`allocate`, `write`), and hands the engine word changes by where they live:

  markers()       blob1 words (tables, menu lists, pointers): applied at stage B, before blob1 runs
  module_words()  {module: words} for the menu modules 0x41 / 0x44: applied when the module's first init is about to
                  run (the modules are streamed in after boot, so earlier writes would be lost)
  blob2_words()   (addr, old, new, flag) blob2 code / tables: applied when blob2 is in RAM, before it starts;
                  flag 1 = only if blob1's tone-curve table holds curve 38 (the flashed v2 has it)
  texts()         {text ID: string}: repointed in all 35 language blocks by the language hook (cchook.py)
  tuning(fw)      (look only) tuning-area entries for the tuning hooks (cchook.py)

Every change carries the stock word; the run-time code writes only where it still finds that word.

Layout in the filler (kept identical to the camera-tested card `build/sdchain_cc11rc_green`): the base part's data,
the extensions' data, one patch table per module, HOOK_INIT, HOOK_B2, the stage-B table and its routine, the look's
stubs, the blob2 table. Stage-B order: base markers, the two hook call sites, extension markers.
"""
import struct
from classic_chrome.engine.firmware import MODULES

END = 0x7ffffffe
FILLER_END = 0xc000
SITE_INIT, BLX_R3 = 0x9717b8, 0xe12fff33         # blob1 module-init loop `blx r3`
SITE_B2, START_B2 = 0x972520, 0x854e48           # blob1 `bl` that starts blob2
CURVE_CNT, CURVE_TAB, CURVE_NEW = 0x80b6f8, 0x80b700, 38


class Part:
    """Base class of a feature. All methods are optional. The engine sets self.asm(src, at) -> bytes and
    self.bl(frm, to) -> word before allocate()."""
    def bind(self, asm, bl): self.asm, self.bl = asm, bl
    def check(self, fw): pass
    def allocate(self, alloc): pass
    def write(self, L, asm, bl): pass
    def markers(self): return []
    def module_words(self): return {}
    def blob2_words(self): return []
    def texts(self): return {}
    def tuning_bytes(self, fw): return {}           # {parameter ID: (old byte, new byte)}, old = the flashed value
    def tuning_params(self, fw): return []          # ready u16 entries (id, old hex, new hex)


class Card:
    def __init__(self, base, extensions=(), look=None):
        self.base, self.extensions, self.look = base, list(extensions), look
        self.parts = [base] + self.extensions

    def check(self, fw):
        for p in self.parts + ([self.look] if self.look else []): p.check(fw)
        fw.expect(SITE_INIT, BLX_R3, 'module-init loop')
        for m, (_, base, _, init) in MODULES.items():
            fw.expect(base, init, f'module {m:#x}: first init (its table is applied just before it runs)')

    def texts(self):
        out = {}
        for p in self.parts: out.update(p.texts())
        return out

    def tuning(self, fw):
        """Tuning-hook entries of every part (None: the hooks' default, cc_values.PARAMS3)."""
        from classic_chrome.features import cc_look
        everyone = self.parts + ([self.look] if self.look else [])
        params = [e for p in everyone for e in p.tuning_params(fw)]
        taken = {pid + k for pid, *_ in params for k in (0, 1)}
        merged = {}
        for p in everyone:
            for i, v in p.tuning_bytes(fw).items():
                assert i not in merged and i not in taken, f'tuning ID {i:#x} changed by two features'
                merged[i] = v
        if merged: params += cc_look.db_params(merged, fw.flash_tuning)
        return params or None

    # ---- the installer crumbs.patch calls (extra=...): returns (stage-B routine address, info)
    def install(self, L, asm, bl, start):
        imm = lambda r, v: f'movw {r}, #{v & 0xffff}\n    movt {r}, #{v >> 16}'
        pos = [(start + 0x3f) & ~0x3f]; first = pos[0]

        def alloc(size, align=1):
            pos[0] = (pos[0] + align - 1) & ~(align - 1); at = pos[0]; pos[0] += size
            return at

        everyone = self.parts + ([self.look] if self.look else [])
        for p in everyone: p.bind(asm, bl)
        for p in self.parts: p.allocate(alloc)
        mods = {m: [] for m in MODULES}
        for p in self.parts:
            for m, ws in p.module_words().items(): mods[m] += ws
        mtab = {m: alloc(12 * len(ws) + 4) for m, ws in mods.items()}
        HOOK_INIT = alloc(0xa0, 0x20)
        HOOK_B2 = alloc(0xa0)
        n_markers = sum(len(p.markers()) for p in self.parts) + 2
        STAGE_TAB = alloc(12 * max(8, n_markers) + 4)
        APPLY = alloc(0x60, 0x20)
        if self.look: self.look.allocate(alloc)
        b2 = (self.look.blob2_words() if self.look else []) + [e for p in self.parts for e in p.blob2_words()]
        B2TAB = alloc(16 * len(b2) + 4)
        at = pos[0]
        assert at <= FILLER_END, f'filler full ({at:#x})'
        assert all(x == 0xff for x in L[first:at]), 'filler not free'

        for p in everyone: p.write(L, asm, bl)
        for m, ws in mods.items():
            t = b''.join(struct.pack('<3I', *w) for w in ws) + bytes(4)
            L[mtab[m]:mtab[m] + len(t)] = t

        # HOOK_INIT: replaces `blx r3` in the module-init loop; r3 = the init about to run. Matching module →
        # apply its table (old word checked), clean D-cache lines, invalidate the I-cache; then run the init.
        sel = []
        mlist = list(mods)
        for i, m in enumerate(mlist):
            last = i == len(mlist) - 1
            sel.append(f'''
    {imm('r12', MODULES[m][3])}
    cmp r3, r12
    {imm('r4', mtab[m])}
    {'bne m_done' if last else 'beq m_loop'}''')
        code = asm(f'''
    push {{r0, r1, r2, r4, r5, lr}}
    {''.join(sel)}
m_loop:
    ldr r0, [r4], #4
    cmp r0, #0
    beq m_done
    ldr r1, [r4], #4
    ldr r2, [r4], #4
    ldr r5, [r0]
    cmp r5, r1
    streq r2, [r0]
    mcreq p15, 0, r0, c7, c10, 1
    b m_loop
m_done:
    dsb
    mov r0, #0
    mcr p15, 0, r0, c7, c5, 0
    dsb
    isb
    pop {{r0, r1, r2, r4, r5, lr}}
    bx r3''', HOOK_INIT)
        assert len(code) <= 0xa0, len(code)
        L[HOOK_INIT:HOOK_INIT + len(code)] = code

        # HOOK_B2: replaces the `bl` that starts blob2. Applies the blob2 table; flagged entries only when blob1's
        # tone-curve table holds curve 38.
        L[B2TAB:B2TAB + 16 * len(b2) + 4] = b''.join(struct.pack('<4I', *e) for e in b2) + bytes(4)
        code = asm(f'''
    push {{r0, r1, r2, r3, r4, r5, lr}}
    {imm('r4', CURVE_CNT)}
    ldr r4, [r4]
    {imm('r5', CURVE_TAB)}
    mov r0, #0
g_loop:
    cmp r4, #0
    beq g_done
    ldr r1, [r5]
    cmp r1, #{CURVE_NEW}
    moveq r0, #1
    add r5, r5, #0x48
    sub r4, r4, #1
    b g_loop
g_done:
    {imm('r4', B2TAB)}
b_loop:
    ldr r1, [r4], #4
    cmp r1, #0
    beq b_done
    ldr r2, [r4], #4
    ldr r3, [r4], #4
    ldr r5, [r4], #4
    tst r5, #1
    beq b_do
    cmp r0, #0
    beq b_loop
b_do:
    ldr r5, [r1]
    cmp r5, r2
    streq r3, [r1]
    mcreq p15, 0, r1, c7, c10, 1
    b b_loop
b_done:
    dsb
    mov r1, #0
    mcr p15, 0, r1, c7, c5, 0
    dsb
    isb
    pop {{r0, r1, r2, r3, r4, r5, lr}}
    b {START_B2:#x}''', HOOK_B2)
        assert len(code) <= 0xa0, len(code)
        L[HOOK_B2:HOOK_B2 + len(code)] = code

        # stage B: blob1 words, called from crumbs.py's stage-B routine
        markers = self.base.markers() + [(SITE_INIT, BLX_R3, bl(SITE_INIT, HOOK_INIT)),
                                         (SITE_B2, bl(SITE_B2, START_B2), bl(SITE_B2, HOOK_B2))]
        for p in self.extensions: markers += p.markers()
        st = b''.join(struct.pack('<3I', *m) for m in markers)
        L[STAGE_TAB:STAGE_TAB + len(st) + 4] = st + bytes(4)
        code = asm(f'''
    push {{r0, r1, r2, r4, r5, lr}}
    {imm('r4', STAGE_TAB)}
s_loop:
    ldr r0, [r4], #4
    cmp r0, #0
    beq s_done
    ldr r1, [r4], #4
    ldr r2, [r4], #4
    ldr r5, [r0]
    cmp r5, r1
    streq r2, [r0]
    mcreq p15, 0, r0, c7, c10, 1
    b s_loop
s_done:
    pop {{r0, r1, r2, r4, r5, pc}}''', APPLY)
        assert len(code) <= 0x60
        L[APPLY:APPLY + len(code)] = code
        return APPLY, {'markers': len(markers), 'module_words': {f'{m:#x}': len(w) for m, w in mods.items()},
                       'blob2_words': len(b2), 'hook_init': HOOK_INIT, 'hook_b2': HOOK_B2, 'apply': APPLY,
                       'filler': (first, at)}
