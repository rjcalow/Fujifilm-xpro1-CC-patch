"""Playback RAW CONVERSION menu: every line-up entry as an extra FILM SIMULATION row (FINDINGS.md §6d, §11).

The screen is its own setting (0x152) and stores a film code, not a MODE_FSIM; module 0x44 turns the code into the
film simulation the developer uses (found live with tools/fsimlog.py). One new row needs:
  blob1   setting 0x152's row list and conversion table → copies with the new row (row → film code)
  blob2   apply chain FUN_00f10e58: its "unknown row" branch → stub: new row → film code (else stock path)
          cursor chain FUN_00f1e248: its "unknown code" branch → stub: new code → new row (else stock row 0)
  0x41    the screen's row-name and icon tables → copies with the new IDs, row limit `cmp r4,#9` → `#row`
  0x44    request builder FUN_016326a4: its switch default → stub: new code → MODE_FSIM (else 0 = PROVIA)
Every entry gets its own film code (config.lineup); module 0x44 maps it to the entry's MODE_FSIM, so a recipe
converts with its base look (its overrides apply when shooting, not in RAW conversion). Names: text IDs where the
entry has them, else the shooting menu's drawn strings (the RAW screen draws through the same call 0x147c798, and
menus.py's DRAW stub handles both); icons as in the shooting menu (FilmSim.icons).
"""
import struct
from classic_chrome.engine.card import Part, END

NODE, LIST, ROWS = 0x778d9c + 0x14, 0x779cf4, [0, 1, 2, 8, 7, 3, 5, 4, 6, 9]
TABPTR, TAB, CODES = 0x78bf58, 0x78adc8, [0, 5, 3, 6, 7, 8, 9, 6, 7, 10]       # 0x78ba10[0x152]; row → code
NAME_TAB, ICON_TAB, ICON_FIELD = 0x14838f4, 0x142e558, 0x142ae18
CAP, MOVW, MOVT = 0x147c61c, 0x147c624, 0x147c628                           # `cmp r4,#9`; movw/movt r3, =NAME_TAB
APPLY, APPLY_OLD, APPLY_CONT, APPLY_DONE = 0xf10ff0, 0xe3043d28, 0xf10ff8, 0xf11024
CUR, CUR_OLD, CUR_ROW0, CUR_SET = 0xf1f960, 0x1a000166, 0xf1ff00, 0xf1ff3c
M44, M44_OLD, M44_JT, M44_CONT, M44_REQ = 0x16328ac, 0xea000004, 0x979ff103, 0x1632924, 0x121b54c + 0x770
BLOCK = 0x9d4d28                                    # RAW-convert block: +8 film code, +0x1c COLOR code


class RawConversion(Part):
    def __init__(self, sims, menu):
        self.sims = sorted(sims, key=lambda s: s.row)
        assert [s.row for s in self.sims] == list(range(10, 10 + len(self.sims)))
        assert len({s.rawconv_code for s in self.sims}) == len(self.sims) and all(s.rawconv_code >= 8 for s in self.sims)
        self.menu = menu                                # the shooting menu part: drawn names + icons

    def check(self, fw):
        fw.expect(NODE, LIST, 'setting 0x152 node'); fw.expect(TABPTR, TAB, '0x78ba10[0x152]')
        assert fw.words(LIST, 22) == sum(([r, 0] for r in ROWS + [END]), []), 'setting 0x152 list'
        assert [fw.words(TAB + 12 * i, 3) for i in range(10)] == [[END, END, c] for c in CODES], 'setting 0x152 table'
        for a, o in ((CAP, 0xe3540009), (MOVW, 0xe30338f4), (MOVT, 0xe3403148), (ICON_FIELD, ICON_TAB),
                     (APPLY, APPLY_OLD), (CUR, CUR_OLD), (M44, M44_OLD), (M44 - 4, M44_JT)):
            fw.expect(a, o)
        self.names, self.icons = fw.words(NAME_TAB, 10), fw.words(ICON_TAB, 10)

    def allocate(self, alloc):
        n = len(self.sims)
        if n == 1:                                        # the camera-tested single-row layout
            sizes = (('list', 0x60), ('tab', 12 * 11 + 4), ('name', 0x30), ('icon', 0x30),
                     ('stub_apply', 0x30), ('stub_cur', 0x20), ('stub_m44', 0x20))
        else:
            sizes = (('list', 8 * (10 + n) + 8), ('tab', 12 * (10 + n) + 4), ('name', 4 * (10 + n)), ('icon', 4 * (10 + n)),
                     ('stub_apply', 0x18 + 0xc * n), ('stub_cur', 0x8 + 0xc * n), ('stub_m44', 0x18 + 0x8 * n))
        self.a = {k: alloc(size) for k, size in sizes}

    def _name(self, s):
        return s.name_id if s.name_id else self.menu.STRINGS + 24 * self.menu.drawn.index(s)

    def write(self, L, asm, bl):
        a, n = self.a, len(self.sims)
        put = lambda at, b, room: (L.__setitem__(slice(at, at + len(b)), b), len(b) <= room or (_ for _ in ()).throw(AssertionError((at, len(b), room))))
        put(a['list'], b''.join(struct.pack('<II', r, 0) for r in ROWS + [s.row for s in self.sims]) + struct.pack('<II', END, 0), 1 << 16)
        put(a['tab'], b''.join(struct.pack('<3I', END, END, c) for c in CODES + [s.rawconv_code for s in self.sims]) + bytes(4), 1 << 16)
        put(a['name'], struct.pack(f'<{10 + n}I', *self.names, *(self._name(s) for s in self.sims)), 1 << 16)
        put(a['icon'], struct.pack(f'<{10 + n}I', *self.icons, *(self.menu.icons[s.key][2] for s in self.sims)), 1 << 16)
        imm = lambda r, v: f'movw {r}, #{v & 0xffff}\n    movt {r}, #{v >> 16}'
        if n == 1:                                        # the camera-tested single-row stubs, unchanged
            s = self.sims[0]
            apply = f'''
    cmp r6, #{s.row}
    {imm('r3', BLOCK)}
    moveq r2, #{s.rawconv_code}
    streq r2, [r3, #8]
    beq {APPLY_DONE:#x}
    b {APPLY_CONT:#x}'''
            cur = f'''
    cmp r3, #{s.rawconv_code}
    moveq r4, #{s.row}
    beq {CUR_SET:#x}
    b {CUR_ROW0:#x}'''
            m44 = f'''
    cmp r3, #{s.rawconv_code - 3}
    {imm('r3', M44_REQ)}
    moveq r2, #{s.mode_fsim}
    movne r2, #0
    str r2, [r3]
    b {M44_CONT:#x}'''
        else:
            # apply (blob2, r6 = row): a new row → block +8 = its film code; other rows → stock default path
            apply = '\n    '.join([f'cmp r6, #{s.row}\n    moveq r2, #{s.rawconv_code}\n    beq ap_set' for s in self.sims]
                                  + [f'b {APPLY_CONT:#x}', 'ap_set:', imm('r3', BLOCK), 'str r2, [r3, #8]', f'b {APPLY_DONE:#x}'])
            # cursor (blob2, r3 = film code, r4 = row out): a new code → its row; else stock "row 0"
            cur = '\n    '.join([f'cmp r3, #{s.rawconv_code}\n    moveq r4, #{s.row}\n    beq {CUR_SET:#x}' for s in self.sims]
                                + [f'b {CUR_ROW0:#x}'])
            # module 0x44 request builder (r3 = film code - 3): a new code → its MODE_FSIM, else 0 (stock default)
            m44 = '\n    '.join(['mov r2, #0'] + [f'cmp r3, #{s.rawconv_code - 3}\n    moveq r2, #{s.mode_fsim}' for s in self.sims]
                                + [imm('r3', M44_REQ), 'str r2, [r3]', f'b {M44_CONT:#x}'])
        for key, src in (('stub_apply', apply), ('stub_cur', cur), ('stub_m44', m44)):
            code = asm(src, a[key])
            room = dict(stub_apply=0x30, stub_cur=0x20, stub_m44=0x20)[key] if n == 1 else \
                dict(stub_apply=0x18 + 0xc * n, stub_cur=0x8 + 0xc * n, stub_m44=0x18 + 0x8 * n)[key]
            put(a[key], code, room)

    def markers(self):
        return [(NODE, LIST, self.a['list']), (TABPTR, TAB, self.a['tab'])]

    def module_words(self):
        n = self.a['name']
        word = lambda src: struct.unpack('<I', self.asm(src, 0))[0]
        return {0x41: [(CAP, 0xe3540009, 0xe3540000 | self.sims[-1].row),
                       (MOVW, 0xe30338f4, word(f'movw r3, #{n & 0xffff}')),
                       (MOVT, 0xe3403148, word(f'movt r3, #{n >> 16}')),
                       (ICON_FIELD, ICON_TAB, self.a['icon'])],
                0x44: [(M44, M44_OLD, self.bl(M44, self.a['stub_m44']) & ~0x01000000)]}          # b, not bl

    def blob2_words(self):
        bl, a = self.bl, self.a
        return [(APPLY, APPLY_OLD, bl(APPLY, a['stub_apply']) & ~0x01000000, 0),                  # b
                (CUR, CUR_OLD, (bl(CUR, a['stub_cur']) & 0x00ffffff) | 0x1a000000, 0)]           # bne
