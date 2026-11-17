"""Shooting menu: a new FILM SIMULATION entry (FINDINGS.md §3, §4, §6, §6b).

What one new entry needs, all checked against the stock words first:
  blob1   film-simulation conversion table (setting 0x3d) row `row` := {stored value, -, MODE_FSIM}
          both FILM SIMULATION menu nodes → a copy of their row list with the new row appended
  0x41    row-name table entry `row` := name text ID, and the screen's row limit `cmp r4,#9` → `#row`
          icon tables of both FILM SIMULATION records → copies with the icon text ID appended
          MODE_FSIM → menu-row byte tables (shooting-menu line): entry MODE_FSIM := row
  texts   name and icon text IDs → the new strings (texts.py)

Row 10 is an empty placeholder in the stock conversion table, so one new entry fits without moving the table. A
second one (row 11) needs the table copied to free space and its pointer 0x78ba10[0x3d] changed; not built yet.
"""
import struct
from classic_chrome.engine.card import Part, END

CONV = 0x78f168                                     # setting 0x3d conversion table, rows {c0, c1, MODE_FSIM}
NODES = [(0x779ffc + 0x14, 0x779a84), (0x77a544 + 0x14, 0x77b908)]   # (list pointer, stock list)
STOCK_ROWS = [0, 1, 2, 8, 7, 6, 4, 3, 5, 9]
NAME_TAB = 0x1483c20                                # row → text ID (stock entry 10 = 0)
ROW_CAP = 0x147c748                                 # `cmp r4, #9`
ICON_TABS = {'A': (0x142aa4c, [0x14299fc, 0x142bd98]),   # stock icon table, record fields pointing at it
             'B': (0x1427320, [0x1429a00, 0x142bd9c])}
ROW_MAPS = [0x1474e7c, 0x1474e3c]                   # MODE_FSIM → menu row, bytes


class FilmSimMenu(Part):
    def __init__(self, sims):
        assert len(sims) == 1, 'one new FILM SIMULATION entry for now: a second needs the conversion table moved'
        self.sim = sims[0]
        assert self.sim.row == 10, 'row 10 is the only free row in the stock table'

    def check(self, fw):
        s = self.sim; self.fw = fw
        assert fw.words(CONV + 12 * s.row, 3) == [END] * 3, 'conversion-table row not empty'
        for ptr, lst in NODES:
            fw.expect(ptr, lst, 'FILM SIMULATION menu node')
            assert fw.words(lst, 22) == sum(([r, 0] for r in STOCK_ROWS + [END]), []), f'menu list {lst:#x}'
        fw.expect(NAME_TAB + 4 * s.row, 0, 'row-name entry')
        fw.expect(ROW_CAP, 0xe3540009, 'row limit')
        for src, fields in ICON_TABS.values():
            for f in fields: fw.expect(f, src, 'icon-table pointer')
        self.icon_src = {k: fw.words(src, 10) for k, (src, _) in ICON_TABS.items()}
        self.row_maps = []
        for t in ROW_MAPS:
            a = (t + s.mode_fsim) & ~3; old = fw.word(a); k = (t + s.mode_fsim) & 3
            new = old & ~(0xff << 8 * k) | s.row << 8 * k
            self.row_maps.append((a, old, new))

    def allocate(self, alloc):
        self.LIST = alloc(0x60)
        self.ICON = {k: alloc(0x30) for k in ICON_TABS}

    def write(self, L, asm, bl):
        lst = b''.join(struct.pack('<II', r, 0) for r in STOCK_ROWS + [self.sim.row]) + struct.pack('<II', END, 0)
        L[self.LIST:self.LIST + len(lst)] = lst
        for k, t in self.icon_src.items():
            L[self.ICON[k]:self.ICON[k] + 44] = struct.pack('<11I', *t, self.sim.icon_id)

    def markers(self):
        s, row = self.sim, CONV + 12 * self.sim.row
        return [(row, END, s.stored), (row + 8, END, s.mode_fsim)] + [(p, lst, self.LIST) for p, lst in NODES]

    def module_words(self):
        s = self.sim
        w = [(NAME_TAB + 4 * s.row, 0, s.name_id), (ROW_CAP, 0xe3540009, 0xe3540000 | s.row)]
        for k, (src, fields) in ICON_TABS.items(): w += [(f, src, self.ICON[k]) for f in fields]
        return {0x41: w + self.row_maps}

    def texts(self):
        return {self.sim.name_id: self.sim.name, self.sim.icon_id: self.sim.icon}
