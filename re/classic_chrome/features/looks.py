"""How new film simulations render (FINDINGS.md §6c). One look module per card.

The image pipeline works on colour modes: MODE_FSIM → colour mode (blob2 table 0xf396b0, index MODE_FSIM - 1) →
per-colour-mode selections. For colour modes it does not know (0/1/8/9 in the X-Pro1's chains) each selection falls
back to PROVIA in one instruction; the look turns those instructions into calls to small stubs that answer for the
new colour modes. Both looks expect the flashed firmware to be the v2 build (re/build/ptpdebug_385), whose tuning
values the hooks check before every write.

  BorrowLook  the new film simulation uses PRO Neg. Hi's colour mode 7, where the flashed v2 keeps Classic Chrome
              data (+ the v3 chroma values, config/cc_values.py). PRO Neg. Hi then looks like Classic Chrome too.
  OwnLook     Classic Chrome data of its own for colour mode 1 (cc_look.py: X-E2 matrices in free presets 17/18,
              v3 2x2 in preset 12, curve 38 through tone family 5) and PRO Neg. Hi back to stock.
              extras: further film simulations whose colour mode borrows stock selections (FilmSim.look):
              3x3 matrix index (sRGB and alt chains), 2x2 index, tone family and tone code. Superia 400:
              colour mode 8 → ASTIA's 3x3 (index 2), PROVIA's 2x2 (0), PRO Neg. Std's tone (family 3, code 0xfc).
"""
import struct
from classic_chrome.engine.card import Part
from classic_chrome.features import cc_look as cclook

FSIM2CM = 0xf396b0


def _fsim2cm(sim): return FSIM2CM + 4 * (sim.mode_fsim - 1)


class BorrowLook(Part):
    CM_NEW = 7                                       # PRO Neg. Hi's colour mode

    def __init__(self, sim, extras=()):
        assert not extras, 'extra looks need OwnLook'
        self.sim = sim

    def check(self, fw):
        fw.expect(_fsim2cm(self.sim), self.sim.colour_mode, 'MODE_FSIM → colour mode')

    def blob2_words(self):
        return [(_fsim2cm(self.sim), self.sim.colour_mode, self.CM_NEW, 0)]

    def tuning_params(self, fw):
        from classic_chrome.config.cc_values import PARAMS3
        return list(PARAMS3)                         # v3 chroma values in PRO Neg. Hi's preset

    def tuning_bytes(self, fw): return {}


# stub sites (cc_look.CODE) by role; with extras the shared 'A' stub splits into a 3x3 one and a 2x2 one
SITE_A3, SITES_A2 = 0xf333c4, (0xf30d7c, 0xf30e0c)


# Classic Chrome-only words: its relocated alt tables, alt-table selectors and the SEPIA → PROVIA tone-family move
CC_ONLY = {0xf33474, 0xf33478, 0xf30e10, 0xf30e14, 0xf30e18, 0xf3430c, 0xf34254, 0xf2deb4, 0xf34364, 0xf3443c, 0xf34074}


class OwnLook(Part):
    """sim: Classic Chrome (its data for colour mode 1) or None; extras: borrowed looks (FilmSim.look)."""
    def __init__(self, sim, extras=()):
        assert sim is None or sim.own_data and sim.colour_mode == 1, 'OwnLook holds Classic Chrome data for colour mode 1'
        self.sim, self.extras = sim, list(extras)
        assert sim or self.extras
        for e in self.extras: assert e.look and e.colour_mode not in (0, 1, 2, 3, 4, 5, 6, 7), e.key
        # colour mode → (3x3 index, 2x2 index, tone family, tone code); Classic Chrome: its own index 7, family 5
        self.map = ([(1, 7, 7, 5, 0xff)] if sim else []) + [(e.colour_mode, e.look['idx3'], e.look['idx2'],
                                                             e.look['family'], e.look['code']) for e in self.extras]
        self.generic = bool(self.extras) or not sim      # False: the camera-tested Classic Chrome-only stubs

    def check(self, fw):
        if self.sim: fw.expect(_fsim2cm(self.sim), self.sim.colour_mode, 'MODE_FSIM → colour mode')
        self.cm_old = {e.key: fw.word(_fsim2cm(e)) for e in self.extras}
        for e in self.extras: assert self.cm_old[e.key] in (0, 1, 2), (e.key, self.cm_old[e.key])
        for a, o, _ in cclook.CODE + cclook.TONE: fw.expect(a, o, 'look site')

    # ---- stubs
    def _stubs(self):
        if not self.generic: return dict(cclook.STUBS)  # byte-identical to the Classic Chrome-only card
        def select(rin, rout, col):
            out = []
            for cm, *v in self.map:
                out += [f'cmp {rin}, #{cm}', f'moveq {rout}, #{v[col]}', 'bxeq lr']
            return '\n '.join(out + [f'mov {rout}, #0', 'bx lr'])
        t1 = []
        for cm, *v in self.map:
            t1 += [f'cmn r3, #1' if cm == 1 else f'cmp r3, #{cm - 2}', f'moveq r2, #{v[2]}', 'beq t1_done']
        t1 = '\n '.join(t1 + ['mov r2, #0', 't1_done:', 'cmp r3, #5', 'bx lr'])
        t2, tail = [], []
        for k, (cm, *v) in enumerate(self.map):
            t2 += [f'cmn r3, #1' if cm == 1 else f'cmp r3, #{cm - 2}', f'beq t2_{k}']
            tail += [f't2_{k}:', f'mov r3, #{v[3]}', 'cmp r3, #5', 'bx lr']
        t2 = '\n '.join(t2 + ['cmp r3, #5', 'movhi r3, #0xf9', 'bx lr'] + tail)
        return {'A3': select('r2', 'r2', 0), 'A2': select('r2', 'r2', 1), 'B': select('r3', 'r1', 0),
                'C': select('r2', 'r3', 1), 'T1': t1, 'T2': t2}

    def allocate(self, alloc):
        if not self.generic:
            self.lay = cclook.layout(alloc(0x100, 16)); return
        n = len(self.map)
        self.lay = {k: alloc(0x10 + 0xc * n, 16) for k in ('A3', 'A2', 'B', 'C')}
        self.lay['T1'] = alloc(0x18 + 0xc * n, 16); self.lay['T2'] = alloc(0x18 + 0x18 * n, 16)
        if self.sim: self.lay['ALT3'] = alloc(0x10, 16); self.lay['ALT2'] = alloc(0x80, 16)

    def write(self, L, asm, bl):
        if not self.generic:
            for ad, blob in cclook.blobs(self.lay, asm).items(): L[ad:ad + len(blob)] = blob
            return
        stubs = self._stubs()
        for k, src in stubs.items():
            code = asm(src, self.lay[k]); L[self.lay[k]:self.lay[k] + len(code)] = code
        if not self.sim: return
        alt3 = struct.pack('<8H', *cclook.ALT3_SRC, cclook.SEL_ALT3)
        alt2 = b''.join(struct.pack('<8I', *row, cclook.SEL_ALT2) for row in cclook.ALT2_ROWS)
        L[self.lay['ALT3']:self.lay['ALT3'] + 16] = alt3; L[self.lay['ALT2']:self.lay['ALT2'] + 0x80] = alt2

    def blob2_words(self):
        # tone words are guarded by curve 38 (Classic Chrome's curve in the flashed v2); without Classic Chrome the tone
        # stubs only serve the borrowed looks and need no guard
        tone = {t[0] for t in cclook.TONE} if self.sim else set()
        if not self.generic:
            words = cclook.words(self.lay, self.asm)
        else:
            code = []
            for a, o, n in cclook.CODE + cclook.TONE:
                if not self.sim and a in CC_ONLY: continue
                if a == SITE_A3: n = ('blne', 'A3')
                elif a in SITES_A2: n = ('blne', 'A2')
                code.append((a, o, n))
            words = [(a, o, self._enc(a, n) if isinstance(n, tuple) else n) for a, o, n in code]
        out = [(a, o, n, 1 if a in tone else 0) for a, o, n in words]
        return out + [(_fsim2cm(e), self.cm_old[e.key], e.colour_mode, 0) for e in self.extras]

    def _enc(self, a, sym):                          # as cc_look.words(): branch / movw / movt to a stub or table
        kind, tgt = sym
        if kind in ('bl', 'blne'): return struct.unpack('<I', self.asm(f'{kind} #{self.lay[tgt]:#x}', a))[0]
        v = self.lay[tgt]; op, reg = kind.split(); imm = v & 0xffff if op.startswith('movw') else v >> 16
        return struct.unpack('<I', self.asm(f'{op} {reg}, #{imm:#x}', a))[0]

    def tuning_bytes(self, fw):
        return cclook.db_bytes(fw.tuning, fw.flash_tuning) if self.sim else {}

    def tuning_params(self, fw): return []


LOOKS = {'own': OwnLook, 'borrow': BorrowLook}
