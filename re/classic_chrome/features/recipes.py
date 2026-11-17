"""Recipe entries (PR #3's REGGIE'S PORTRA and KODACHROME II): a menu entry that renders with a base film simulation
and, for the picture only, overrides white balance (AUTO + R/B shift), Color, Highlight, Shadow and Sharpness.
The saved settings are not touched, so switching back to the base entry gives the user's own settings again.

Where (PR #3, emulator-checked there against setting the same values by hand):
  blob2 0xf79434  `bl 0x966f88`: copies the 0x46c-byte shooting settings into the outgoing settings message
                  → COPY: the copy, then CAPTURE on the message (WB 0xd0, R/B shifts 0xdc/0xe0, 0xe4/0xe8, 0xec/0xf0,
                  Color 0x130, Highlight 0x3c4, Shadow 0x3c8, Sharpness 0x110, MODE_FSIM 0x128)
  blob1 0x9b7610  `pop {r4,r5,fp,pc}` at the end of the compact capture-settings exporter (output r5)
                  → TAIL: PROJECT on the compact record (WB 0xec, R 0xf0, B 0xf4, Color 0xfc, Highlight 0x1e8,
                  Shadow 0x1ec, Sharpness 0xf8, MODE_FSIM 0x100), then the original return
Which recipe: PR #3 gives each recipe its own MODE_FSIM. Here the X-Pro1's spare MODE_FSIMs are kept for looks, so a
recipe shares its base's MODE_FSIM and is recognised by the stored menu value: settings getter blob1 0x793048(0x3d, 0)
(a plain read of the settings bank, safe in any task). As a guard the record's MODE_FSIM must be the base's.
"""
import struct
from classic_chrome.engine.card import Part

COPY_SITE, MEMCPY = 0xf79434, 0x966f88
TAIL_SITE, TAIL_OLD = 0x9b7610, 0xe8bd8830          # pop {r4, r5, fp, pc}
GETTER, SETTING = 0x793048, 0x3d
CAPTURE_OFF = dict(fsim=0x128, wb=0xd0, red=(0xdc, 0xe4, 0xec), blue=(0xe0, 0xe8, 0xf0),
                   color=0x130, hi=0x3c4, lo=0x3c8, sharp=0x110)
COMPACT_OFF = dict(fsim=0x100, wb=0xec, red=(0xf0,), blue=(0xf4,), color=0xfc, hi=0x1e8, lo=0x1ec, sharp=0xf8)


def _load(n):
    return f'mov r2, #{n}' if n >= 0 else f'mvn r2, #{~n}'


class Recipes(Part):
    def __init__(self, sims):
        self.sims = [s for s in sims if s.is_recipe]
        assert self.sims

    def check(self, fw):
        fw.expect(COPY_SITE, self._bl_word(COPY_SITE, MEMCPY), 'settings-message copy')
        fw.expect(COPY_SITE - 4, 0xe300246c, 'movw r2, #0x46c before the copy')
        fw.expect(TAIL_SITE, TAIL_OLD, 'capture-settings exporter return')

    @staticmethod
    def _bl_word(frm, to):
        return 0xeb000000 | (((to - frm - 8) >> 2) & 0xffffff)

    def allocate(self, alloc):
        n = len(self.sims)
        self.COPY = alloc(0x20, 4)
        self.TAIL = alloc(0x14, 4)
        self.CAPTURE = alloc(0x30 + n * 0x70, 4)
        self.PROJECT = alloc(0x30 + n * 0x50, 4)

    def _profile(self, at, off):
        code = ['push {r4, lr}', 'mov r4, r0', f'mov r0, #{SETTING}', 'mov r1, #0', f'bl {GETTER:#x}']
        code += [f'cmp r0, #{s.stored}\n    beq rcp{k}' for k, s in enumerate(self.sims)]
        code += ['pop {r4, pc}']
        for k, s in enumerate(self.sims):
            r = s.recipe
            code += [f'rcp{k}:', f'ldr r1, [r4, #{off["fsim"]}]', f'cmp r1, #{s.mode_fsim}', 'popne {r4, pc}']
            for key in ('wb', 'red', 'blue', 'color', 'hi', 'lo', 'sharp'):
                code.append(_load(r[key]))
                for o in (off[key] if isinstance(off[key], tuple) else (off[key],)): code.append(f'str r2, [r4, #{o}]')
            code.append('pop {r4, pc}')
        return self.asm('\n    '.join(code), at)

    def write(self, L, asm, bl):
        put = lambda at, b, n: (L.__setitem__(slice(at, at + len(b)), b), len(b) <= n or (_ for _ in ()).throw(AssertionError((at, len(b)))))
        put(self.COPY, asm(f'''
    push {{r4, lr}}
    mov r4, r0
    bl {MEMCPY:#x}
    push {{r0, r1, r2, r3, ip, lr}}
    mov r0, r4
    bl {self.CAPTURE:#x}
    pop {{r0, r1, r2, r3, ip, lr}}
    pop {{r4, pc}}''', self.COPY), 0x20)
        put(self.TAIL, asm(f'''
    push {{r0, lr}}
    mov r0, r5
    bl {self.PROJECT:#x}
    pop {{r0, lr}}
    pop {{r4, r5, fp, pc}}''', self.TAIL), 0x14)
        put(self.CAPTURE, self._profile(self.CAPTURE, CAPTURE_OFF), 0x30 + len(self.sims) * 0x70)
        put(self.PROJECT, self._profile(self.PROJECT, COMPACT_OFF), 0x30 + len(self.sims) * 0x50)

    def markers(self):
        return [(TAIL_SITE, TAIL_OLD, struct.unpack('<I', self.asm(f'b {self.TAIL:#x}', TAIL_SITE))[0])]

    def blob2_words(self):
        return [(COPY_SITE, self._bl_word(COPY_SITE, MEMCPY), self.bl(COPY_SITE, self.COPY), 0)]
