"""Shooting menu: new FILM SIMULATION entries (FINDINGS.md §3, §4, §6, §6b), rows 10, 11, ...

What the entries need, all checked against the stock words first:
  blob1   film-simulation conversion table (setting 0x3d): one new row {stored value, -, MODE_FSIM} each. Row 10 is
          an empty placeholder in the stock table; with more than one entry the table is copied with the extra
          rows and its pointer 0x78ba10[0x3d] repointed (as PR #3 does).
          both FILM SIMULATION menu nodes → a copy of their row list with the new rows appended
  0x41    row-name table 0x1483c20 → a copy with the new rows (pointer movw/movt 0x147c750/54), row limit
          `cmp r4,#9` 0x147c748 → `#last row`. (The table must be copied: its word 10 is also entry 0 of the WHITE
          BALANCE name table 0x1483c48; the first Classic Chrome cards wrote the name there, 2026-11-17.)
          Row 10 names through a repointed text ID (texts.py); rows 11+ hold a pointer to an ASCII string that a
          stub draws instead of a text ID (PR #3's method: the `bl 0x1433604` at 0x147c798 goes through DRAW).
          icon tables of both FILM SIMULATION records → copies with the new rows' icon text IDs
          MODE_FSIM → menu-row byte tables (shooting-menu line): entry MODE_FSIM := row, for looks (a recipe shares
          its base's MODE_FSIM, so the line shows the base's icon for it)
"""
import struct
from classic_chrome.engine.card import Part, END

CONV, CONV_PTR = 0x78f168, 0x78ba10 + 4 * 0x3d       # setting 0x3d conversion table, rows {c0, c1, MODE_FSIM}
NODES = [(0x779ffc + 0x14, 0x779a84), (0x77a544 + 0x14, 0x77b908)]   # (list pointer, stock list)
STOCK_ROWS = [0, 1, 2, 8, 7, 6, 4, 3, 5, 9]
NAME_TAB = 0x1483c20                                # row → text ID, 10 stock entries
NAME_MOVW, NAME_MOVT = 0x147c750, 0x147c754         # movw/movt r3, #NAME_TAB
ROW_CAP = 0x147c748                                 # `cmp r4, #9`
DRAW_SITE, DRAW_FN = 0x147c798, 0x1433604           # draw the row name (r2 = text ID)
TEXT_STYLE, DRAW_STR = 0x148c0a0, 0x14328fc         # PR #3: text attributes by ID; draw an ASCII string
STYLE_ID = 819                                      # text whose attributes the drawn names use (a menu name, 'B&W')
ICON_TABS = {'A': (0x142aa4c, [0x14299fc, 0x142bd98]),   # stock icon table, record fields pointing at it
             'B': (0x1427320, [0x1429a00, 0x142bd9c])}
ROW_MAPS = [0x1474e7c, 0x1474e3c]                   # MODE_FSIM → menu row, bytes
SLOT = 24                                           # bytes per drawn name


class FilmSimMenu(Part):
    def __init__(self, sims):
        self.sims = sorted(sims, key=lambda s: s.row)
        assert [s.row for s in self.sims] == list(range(10, 10 + len(self.sims))), 'rows 10, 11, ... (config.lineup)'
        self.drawn = [s for s in self.sims if not s.name_id]          # names drawn from ASCII (no text ID)

    last = property(lambda s: s.sims[-1].row)

    def check(self, fw):
        assert fw.words(CONV + 120, 3) == [END] * 3, 'conversion-table row 10 not empty'
        assert fw.words(CONV + 132, 3) == [0xffff] * 3, 'conversion-table terminator'
        fw.expect(CONV_PTR, CONV, '0x78ba10[0x3d]')
        self.conv_rows = [fw.words(CONV + 12 * r, 3) for r in range(10)]
        for ptr, lst in NODES:
            fw.expect(ptr, lst, 'FILM SIMULATION menu node')
            assert fw.words(lst, 22) == sum(([r, 0] for r in STOCK_ROWS + [END]), []), f'menu list {lst:#x}'
        self.names = fw.words(NAME_TAB, 10)
        self.name_movw, self.name_movt = fw.word(NAME_MOVW), fw.word(NAME_MOVT)
        fw.expect(ROW_CAP, 0xe3540009, 'row limit')
        self.draw_old = fw.word(DRAW_SITE)
        off = self.draw_old & 0xffffff
        off -= (off & 0x800000) << 1
        assert self.draw_old >> 24 == 0xeb and DRAW_SITE + 8 + 4 * off == DRAW_FN, 'name draw call'
        for src, fields in ICON_TABS.values():
            for f in fields: fw.expect(f, src, 'icon-table pointer')
        self.icon_src = {k: fw.words(src, 10) for k, (src, _) in ICON_TABS.items()}
        raw = fw.words(0x142e558, 10)                                  # RAW CONVERSION icons (for FilmSim.icons)
        self.icons = {s.key: s.icons(self.icon_src['A'], self.icon_src['B'], raw) for s in self.sims}
        self.row_maps = []
        for t in ROW_MAPS:
            new = {}                                         # word address → value with the new rows' bytes
            for s in self.sims:
                if s.is_recipe: continue
                a, k = (t + s.mode_fsim) & ~3, (t + s.mode_fsim) & 3
                v = new.get(a, fw.word(a))
                new[a] = v & ~(0xff << 8 * k) | s.row << 8 * k
            self.row_maps += [(a, fw.word(a), v) for a, v in new.items()]

    def allocate(self, alloc):
        n = len(self.sims)
        if n > 1: self.CONV = alloc(12 * (10 + n) + 12)
        self.LIST = alloc(0x60 if n == 1 else 8 * (10 + n) + 8)
        self.ICON = {k: alloc(0x30 if n == 1 else 4 * (10 + n)) for k in ICON_TABS}
        self.NAMES = alloc(4 * (10 + n))
        if self.drawn:
            self.STRINGS = alloc(SLOT * len(self.drawn))
            self.DRAW = alloc(0x60, 4)

    def write(self, L, asm, bl):
        put = lambda at, b: L.__setitem__(slice(at, at + len(b)), b)
        put(self.LIST, b''.join(struct.pack('<II', r, 0) for r in STOCK_ROWS + [s.row for s in self.sims])
            + struct.pack('<II', END, 0))
        for k, t in self.icon_src.items():
            put(self.ICON[k], struct.pack(f'<{10 + len(self.sims)}I', *t, *(self.icons[s.key]['AB'.index(k)] for s in self.sims)))
        if len(self.sims) > 1:
            rows = [struct.pack('<3I', *r) for r in self.conv_rows]
            rows += [struct.pack('<3I', s.stored, END, s.mode_fsim) for s in self.sims]
            put(self.CONV, b''.join(rows) + struct.pack('<3I', 0xffff, 0xffff, 0xffff))
        names = list(self.names)
        for s in self.sims:
            names.append(s.name_id if s.name_id else self.STRINGS + SLOT * self.drawn.index(s))
        put(self.NAMES, struct.pack(f'<{len(names)}I', *names))
        if self.drawn:
            put(self.STRINGS, b''.join(s.name.encode('ascii').ljust(SLOT, b'\0') for s in self.drawn))
            imm = lambda r, v: f'movw {r}, #{v & 0xffff}\n    movt {r}, #{v >> 16}'
            # r2 = the table entry: a text ID (< 0x69f) or, for rows 11+, the address of one of our strings
            code = asm(f'''
    {imm('ip', self.STRINGS)}
    sub ip, r2, ip
    cmp ip, #{SLOT * len(self.drawn)}
    bhs {DRAW_FN:#x}
    push {{r4, r5, r6, lr}}
    mov r4, r2
    mov r5, r1
    movw r0, #{STYLE_ID}
    bl {TEXT_STYLE:#x}
    mov r1, r0
    sub r2, r5, #1
    add r2, r2, r2, lsl #1
    lsl r2, r2, #3
    mov r0, r4
    movw r3, #0xffff
    sub sp, sp, #8
    str r3, [sp]
    bl {DRAW_STR:#x}
    add sp, sp, #8
    pop {{r4, r5, r6, pc}}''', self.DRAW)
            assert len(code) <= 0x60, len(code)
            put(self.DRAW, code)

    def markers(self):
        if len(self.sims) == 1:
            s, row = self.sims[0], CONV + 12 * self.sims[0].row
            conv = [(row, END, s.stored), (row + 8, END, s.mode_fsim)]
        else:
            conv = [(CONV_PTR, CONV, self.CONV)]
        return conv + [(p, lst, self.LIST) for p, lst in NODES]

    def module_words(self):
        word = lambda src: struct.unpack('<I', self.asm(src, 0))[0]
        s0 = self.sims[0]
        w = [(NAME_MOVW, self.name_movw, word(f'movw r3, #{self.NAMES & 0xffff}')),
             (NAME_MOVT, self.name_movt, word(f'movt r3, #{self.NAMES >> 16}')),
             (ROW_CAP, 0xe3540009, 0xe3540000 | self.last)]
        for k, (src, fields) in ICON_TABS.items(): w += [(f, src, self.ICON[k]) for f in fields]
        if self.drawn: w.append((DRAW_SITE, self.draw_old, self.bl(DRAW_SITE, self.DRAW)))
        return {0x41: w + self.row_maps}

    def texts(self):
        out = {}
        for s in self.sims:
            if s.name_id: out.update({s.name_id: s.name, s.icon_id: s.icon})
        return out
