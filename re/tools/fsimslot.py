"""Live experiment: an 11th film-simulation menu row on the X-Pro1 (RAM only, needs the USB debug firmware).

Data model (NOTES 2026-11-12 late night): property 0x3d = film simulation. Menu rows are converted by the table
blob1 0x78f168 (rows of 3 u32: c0 = stored value, c1, c2 = MODE_FSIM); row 10 is empty in the stock firmware.
The menu nodes 0x779ffc and 0x77a544 point (+0x14) at the list of allowed rows [0,1,2,8,7,6,4,3,5,9].

  apply    also labels the row in the shooting menu: name-table entry 10 := text 819 ("B&W") and the draw
           function's row limit 9 -> 10 (one instruction in module 0x41, I-cache invalidated afterwards);
           row 10 := {13, -, 6} (stored value 13 -> hidden MODE_FSIM 6 "CHROME", colour mode 1 = PROVIA look for now);
           both nodes -> a new list with row 10 appended, written to the unused loader area 0xb800
  restore  back to stock
  status   table row, node pointers, list, and the stored film-sim value per mode (0x9cafef + 7*mode, high nibble)

Nothing is written to flash; a battery pull also restores everything. The *setting* 13 can end up in the camera's
saved settings if the new row is selected: choose another film simulation before `restore` / switching off.
usage: ~/.venvs/xpro1-re/bin/python re/tools/fsimslot.py apply [--own]|restore|status
  --own: leave fsim 6 on colour mode 1, for cclook.py's own Classic Chrome data (default: borrow PRO Neg. Hi's mode 7)
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpdebug

END = 0x7ffffffe
TABLE = 0x78f168                      # conversion table of property 0x3d
ROW10 = TABLE + 10 * 12
NODES = {0x779ffc: 0x779a84, 0x77a544: 0x77b908}      # node -> stock value list
STOCK_ROWS = [0, 1, 2, 8, 7, 6, 4, 3, 5, 9]
NEWLIST = 0xb800                      # loader filler, 0xff in the running firmware
C0_NEW, FSIM_NEW = 13, 6
# label for row 10 in the shooting menu (module 0x41, FINDINGS §6): name table entry 10 + row limit in 0x147c5dc
NAME_ENTRY, NAME_ID = 0x1483c20 + 40, 819          # 819 = the unused string "B&W", as a recognisable test label
LIMIT, LIMIT_OLD, LIMIT_NEW = 0x147c748, 0xe3540009, 0xe354000a      # cmp r4, #9 -> cmp r4, #10
FSIM2CM = 0xf396b0 + 4 * (FSIM_NEW - 1)             # blob2 fsim -> colour mode table; stock 1 (PROVIA data)
CM_STOCK, CM_CC = 1, 7                             # 7 = PRO Neg. Hi's colour mode, which holds Classic Chrome in v2/v3
# icon tables of the shooting-menu FILM SIMULATION item (module 0x41 records {item, text, gfx, flag, A, B}):
# A = icon (803 group), B = small icon (802 group); 10 entries each, packed, so copied with an 11th entry
ICON_TABLES = {0x142aa4c: 0xb900, 0x1427320: 0xb940}             # stock -> copy in the loader filler
ICON_REFS = {0x14299fc: 0x142aa4c, 0x142bd98: 0x142aa4c, 0x1429a00: 0x1427320, 0x142bd9c: 0x1427320}
ICON_ID = 1215                                     # unused copy of the SEPIA icon; uitextmark makes it U+F2B9
# main-menu value: MODE_FSIM -> menu row byte tables (module 0x41 0x1474e7c item 8, 0x1474e3c), fsim 6 -> 0 on
# stock; byte 6 sits in the word at +4: [5, 9, 0, 5] -> [5, 9, 10, 5]
ROWMAP = {0x1474e80: (0x05000905, 0x050a0905), 0x1474e40: (0x05000905, 0x050a0905)}
ICACHE_INVALIDATE = 0x8a5d70                       # blob1: mov r0,#0; mcr p15,0,r0,c7,c5,0; bx lr


def code_poke(p, a, v):
    """Write an instruction: poke, push the data-cache line out by reading 2 MB elsewhere, drop the I-cache."""
    poke(p, a, v)
    p.peek(0x40000000 + 0x2000000, 0x200000)
    r, _, _ = p.op(ptpdebug.CALL, ICACHE_INVALIDATE, 0)
    if r != 0x2001: sys.exit('cache invalidate call failed')


def words(p, a, n): return list(struct.unpack(f'<{n}I', p.peek(a, 4 * n)))


def poke(p, a, v):
    r, _, _ = p.op(ptpdebug.POKE, a, v)
    if r != 0x2001 or words(p, a, 1)[0] != v: sys.exit(f'POKE {a:#x} failed')


def read_list(p, a):
    out = []
    for _ in range(32):
        v, z = words(p, a, 2)
        if v == END: return out
        out.append(v); a += 8
    return out + ['...']


def status(p):
    print('table row 10      :', [x if x != END else '-' for x in words(p, ROW10, 3)])
    for n in NODES:
        ptr = words(p, n + 0x14, 1)[0]
        print(f'node {n:#x} list : {ptr:#x} {read_list(p, ptr)}')
    print('row-10 name entry :', words(p, NAME_ENTRY, 1)[0], ' row limit insn:', hex(words(p, LIMIT, 1)[0]))
    print('fsim 6 colour mode:', words(p, FSIM2CM, 1)[0], ' active MODE_FSIM:', words(p, 0x9cb890, 1)[0])
    print('fsim->row maps    :', [hex(words(p, a, 1)[0]) for a in ROWMAP])
    print('icon refs         :', [hex(words(p, r, 1)[0]) for r in ICON_REFS])
    st = p.peek(0x9cafec, 0x40)
    print('stored value/mode :', [st[3 + 7 * m] >> 4 for m in range(8)], '(13 = new row)')


def main(a):
    own = '--own' in a; a = [x for x in a if x != '--own']          # --own: keep colour mode 1 (cclook.py look)
    if not a or a[0] not in ('apply', 'restore', 'status'): sys.exit(__doc__)
    p = ptpdebug.PTP(); p.open()
    if a[0] == 'apply':
        for n, lst in NODES.items():                      # only from a known state
            assert words(p, n + 0x14, 1)[0] in (lst, NEWLIST), 'unexpected node pointer'
            assert read_list(p, lst) == STOCK_ROWS, 'unexpected stock list'
        assert words(p, ROW10, 3) in ([END] * 3, [C0_NEW, END, FSIM_NEW]), 'row 10 not empty'
        cur = words(p, NEWLIST, 24)
        assert all(w == 0xffffffff for w in cur) or read_list(p, NEWLIST) == STOCK_ROWS + [10], 'area 0xb800 in use'
        for i, v in enumerate(STOCK_ROWS + [10, END]):
            poke(p, NEWLIST + 8 * i, v); poke(p, NEWLIST + 8 * i + 4, 0)
        poke(p, ROW10, C0_NEW); poke(p, ROW10 + 8, FSIM_NEW)
        for n in NODES: poke(p, n + 0x14, NEWLIST)
        assert words(p, NAME_ENTRY, 1)[0] in (0, NAME_ID) and words(p, LIMIT, 1)[0] in (LIMIT_OLD, LIMIT_NEW)
        poke(p, NAME_ENTRY, NAME_ID); code_poke(p, LIMIT, LIMIT_NEW)
        assert words(p, FSIM2CM, 1)[0] in (CM_STOCK, CM_CC)
        poke(p, FSIM2CM, CM_STOCK if own else CM_CC)
        for ref, tab in ICON_REFS.items(): assert words(p, ref, 1)[0] in (tab, ICON_TABLES[tab]), 'icon record'
        for tab, cp in ICON_TABLES.items():
            for i, v in enumerate(words(p, tab, 10) + [ICON_ID]): poke(p, cp + 4 * i, v)
        for ref, tab in ICON_REFS.items(): poke(p, ref, ICON_TABLES[tab])
        for a, (old, new) in ROWMAP.items():
            assert words(p, a, 1)[0] in (old, new), 'row map'; poke(p, a, new)
    elif a[0] == 'restore':
        if words(p, FSIM2CM, 1)[0] == CM_CC: poke(p, FSIM2CM, CM_STOCK)
        for ref, tab in ICON_REFS.items(): poke(p, ref, tab)
        for a, (old, new) in ROWMAP.items():
            if words(p, a, 1)[0] == new: poke(p, a, old)
        for cp in ICON_TABLES.values():
            for i in range(11): poke(p, cp + 4 * i, 0xffffffff)
        if words(p, LIMIT, 1)[0] == LIMIT_NEW: code_poke(p, LIMIT, LIMIT_OLD)
        if words(p, NAME_ENTRY, 1)[0] == NAME_ID: poke(p, NAME_ENTRY, 0)
        for n, lst in NODES.items(): poke(p, n + 0x14, lst)
        poke(p, ROW10, END); poke(p, ROW10 + 8, END)
        for i in range(24): poke(p, NEWLIST + 4 * i, 0xffffffff)
    status(p)
    p.op(0x1003)


if __name__ == '__main__':
    main(sys.argv[1:])
