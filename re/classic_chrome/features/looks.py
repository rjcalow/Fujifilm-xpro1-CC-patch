"""How the new film simulation renders (FINDINGS.md §6c). One look per card.

The image pipeline works on colour modes: MODE_FSIM → colour mode (blob2 table 0xf396b0, index MODE_FSIM - 1) →
per-colour-mode parameter tables in the tuning area. Both looks expect the flashed firmware to be the v2 build
(re/build/ptpdebug_385), whose tuning values the hooks check before every write.

  BorrowLook  the new film simulation uses PRO Neg. Hi's colour mode 7, where the flashed v2 keeps Classic Chrome
              data (+ the v3 chroma values, config/cc_values.py). PRO Neg. Hi then looks like Classic Chrome too.
  OwnLook     Classic Chrome data of its own for colour mode 1 (cc_look.py: X-E2 matrices in free presets
              17/18, v3 2x2 in preset 12, curve 38 through tone family 5) and PRO Neg. Hi back to stock.
              Data and stubs are Classic Chrome's: another film simulation needs its own look module.
"""
from classic_chrome.engine.card import Part
from classic_chrome.features import cc_look as cclook

FSIM2CM = 0xf396b0


class BorrowLook(Part):
    CM_NEW = 7                                       # PRO Neg. Hi's colour mode

    def __init__(self, sim): self.sim = sim

    def check(self, fw):
        fw.expect(self.addr, self.sim.colour_mode, 'MODE_FSIM → colour mode')

    addr = property(lambda s: FSIM2CM + 4 * (s.sim.mode_fsim - 1))

    def blob2_words(self):
        return [(self.addr, self.sim.colour_mode, self.CM_NEW, 0)]

    def tuning(self, fw):
        from classic_chrome.config.cc_values import PARAMS3
        return PARAMS3                               # v3 chroma values in PRO Neg. Hi's preset


class OwnLook(Part):
    def __init__(self, sim):
        assert sim.key == 'classic_chrome' and sim.colour_mode == 1, 'OwnLook holds Classic Chrome data for colour mode 1'
        self.sim = sim

    def check(self, fw):
        fw.expect(FSIM2CM + 4 * (self.sim.mode_fsim - 1), self.sim.colour_mode, 'MODE_FSIM → colour mode')
        for a, o, _ in cclook.CODE + cclook.TONE: fw.expect(a, o, 'look site')

    def allocate(self, alloc):
        self.lay = cclook.layout(alloc(0x100, 16))

    def write(self, L, asm, bl):
        for ad, blob in cclook.blobs(self.lay, asm).items(): L[ad:ad + len(blob)] = blob

    def blob2_words(self):
        tone = {t[0] for t in cclook.TONE}
        return [(a, o, n, 1 if a in tone else 0) for a, o, n in cclook.words(self.lay, self.asm)]

    def tuning(self, fw):
        return cclook.db_params(cclook.db_bytes(fw.tuning, fw.flash_tuning), fw.flash_tuning)


LOOKS = {'own': OwnLook, 'borrow': BorrowLook}
