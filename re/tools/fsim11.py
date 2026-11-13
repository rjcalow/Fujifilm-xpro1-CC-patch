"""SD dual boot: Classic Chrome as its own (11th) film-simulation menu entry, applied in RAM (flash is not written).

Camera-proven live over USB on 2026-11-13 (tools/fsimslot.py, uitextmark.py; FINDINGS.md §4, §6). This module puts
the same changes on the SD-boot card, at the points where each piece of data is in RAM:

  stage B (blob1 data, crumbs.py markers, old word checked):
    * film-sim conversion table 0x78f168, empty row 10 := {stored value 13, -, MODE_FSIM 6}
    * menu nodes 0x779ffc / 0x77a544 (+0x14) -> 11-entry row list LIST (stock list + row 10)
    * blob1 0x9717b8 `blx r3` (module init loop) -> `bl HOOK_INIT`
    * blob1 0x972520 `bl 0x854e48` (start blob2) -> `bl HOOK_B2`
  HOOK_INIT (module 0x41 has just been streamed in; runs before its init 0x1430170, tail-calls r3):
    * name table 0x1483c20[10] := text 819; row limit 0x147c748 `cmp r4,#9` -> `#10`
    * menu records 0x14299ec / 0x142bd88 (FILM SIMULATION): icon tables -> ICON_A / ICON_B (stock + text 1215)
    * MODE_FSIM -> menu-row tables 0x1474e7c / 0x1474e3c: entry 6 := 10 (main-menu value shows the new icon)
    * D-cache clean per write, then I-cache invalidate (one instruction changed)
  HOOK_B2 (blob2 is in RAM, not started): table of blob2 word patches (old word checked), with a guard flag for
    entries that need curve 38 in blob1's tone-curve table. look='borrow': fsim -> colour-mode table 0xf396b0[5]
    (MODE_FSIM 6): 1 -> 7, i.e. PRO Neg. Hi's colour mode holding the X-E2 Classic Chrome data of the flashed v2.
    look='own' (cclook.py): colour mode 1 gets its own presets and PRO Neg. Hi goes back to stock.
  language block (cchook.py HOOK_LANG with lang=...): descriptors of text 819 ("B&W", unused) and 1215 (unused
    copy of the SEPIA icon) -> "CLASSIC CHROME" and U+F2B9 in all 35 languages. U+F2B9 is the X-E2's Classic
    Chrome icon; the X-Pro1 font already holds the identical glyph (unused), so the font is not changed.
Use together with cchook (v3 values): crumbs.patch(..., cc_img=img, cc_lang=lang(img), extra=install).
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uitext, cchook

END = 0x7ffffffe
ROW10 = 0x78f168 + 10 * 12
NODES = [(0x779ffc + 0x14, 0x779a84), (0x77a544 + 0x14, 0x77b908)]
STOCK_ROWS = [0, 1, 2, 8, 7, 6, 4, 3, 5, 9]
SITE_INIT, BLX_R3, MOD41_INIT = 0x9717b8, 0xe12fff33, 0x1430170
SITE_B2, START_B2 = 0x972520, 0x854e48
NAME_ID, ICON_ID = 819, 1215
MOD41 = [  # (address, stock word, new word or a key filled in by install)
    (0x1483c20 + 40, 0, NAME_ID),
    (0x147c748, 0xe3540009, 0xe354000a),
    (0x14299fc, 0x142aa4c, 'A'), (0x142bd98, 0x142aa4c, 'A'),
    (0x1429a00, 0x1427320, 'B'), (0x142bd9c, 0x1427320, 'B'),
    # main-menu value: MODE_FSIM -> menu-row byte tables (item 8: 0x1474e7c; 0x1474e3c), entry 6 (byte 2 of the
    # word at +4) 0 -> 10; without it the FILM SIMULATION line shows PROVIA's STD badge for Classic Chrome
    (0x1474e80, 0x05000905, 0x050a0905), (0x1474e40, 0x05000905, 0x050a0905)]
ICON_SRC = {'A': 0x142aa4c, 'B': 0x1427320}
FSIM2CM, CM_OLD, CM_NEW = 0xf396b0 + 4 * 5, 1, 7
CURVE_CNT, CURVE_TAB, CURVE_NEW = 0x80b6f8, 0x80b700, 38   # blob1 tone-curve table: guard for the tone patches
TEXTS = {NAME_ID: 'CLASSIC CHROME', ICON_ID: ''}
B1_BASE, B2_BASE, M41_FILE, M41_BASE = 0x774000, 0xe0ec80, 0x46025c, 0x1420000


def lang(img):
    """(entries, tail template) for cchook.install(lang=...): text 819 / 1215 descriptors of all 35 languages."""
    t = bytearray(cchook.TAIL_LEN)
    t[0:8] = b'UINM' + struct.pack('<I', 2); t[8:0x20] = b'\xff' * 0x18
    offs = {NAME_ID: cchook.T_PLAIN, ICON_ID: cchook.T_PRE}
    for tid, off in offs.items():
        s = TEXTS[tid].encode('utf-16le') + b'\0\0'; assert len(s) <= 0x20; t[off:off + len(s)] = s
    out = []
    for k in range(35):
        a = uitext.FILE0 + k * uitext.BLOCK; blk = img[a:a + uitext.BLOCK]
        assert all(x == 0xff for x in blk[cchook.TAIL - 16:]), f'language block {k}: tail in use'
        b = uitext.base_of(blk)
        for tid, off in offs.items():
            d = struct.unpack_from('<I', blk, b + 8 * tid + 4)[0]
            users = [i for i in range(uitext.N) if struct.unpack_from('<I', blk, b + 8 * i + 4)[0] == d]
            assert users == [tid] and blk[d - uitext.RAM + 4:d - uitext.RAM + 8] == b'd\0d\0', (k, tid)
            out.append((d, struct.unpack_from('<I', blk, d - uitext.RAM)[0], uitext.RAM + cchook.TAIL + off))
    return out, bytes(t)


def check(img):
    """The stock words every patch expects, checked in the decoded update image (blob1, blob2, module 0x41)."""
    import xpro1_cc_patch as P
    w = lambda b, base, a: struct.unpack_from('<I', b, a - base)[0]
    u1, p1 = struct.unpack('<II', img[0x10025c:0x100264]); b1 = P.lz_decode(img, 0x10025c + 20, 0x10025c + p1, u1)
    u2, p2 = struct.unpack('<II', img[0x24025c:0x240264]); b2 = P.lz_decode(img, 0x24025c + 20, 0x24025c + p2, u2)
    m41 = img[M41_FILE:M41_FILE + 0x9a9a0]
    assert [w(b1, B1_BASE, ROW10 + 4 * i) for i in range(3)] == [END] * 3, 'row 10 not empty'
    for a, lst in NODES:
        assert w(b1, B1_BASE, a) == lst
        assert [w(b1, B1_BASE, lst + 4 * i) for i in range(22)] == sum(([r, 0] for r in STOCK_ROWS + [END]), [])
    assert w(b1, B1_BASE, SITE_INIT) == BLX_R3
    assert w(m41, M41_BASE, M41_BASE) == MOD41_INIT and w(m41, M41_BASE, M41_BASE + 4) == 0, 'module 0x41 init list'
    for a, old, _ in MOD41: assert w(m41, M41_BASE, a) == old, hex(a)
    assert w(b2, B2_BASE, FSIM2CM) == CM_OLD
    return b1, b2, m41


def install(L, asm, bl, img, start, look='borrow'):
    """crumbs.patch(extra=...) body: write LIST, icon tables and both hooks into the loader filler from `start`.
    Returns (stage-B markers, info)."""
    b1, b2, m41 = check(img)
    imm = lambda r, v: f'movw {r}, #{v & 0xffff}\n    movt {r}, #{v >> 16}'
    at = (start + 0x3f) & ~0x3f
    LIST = at; at += 0x60
    ICON = {}
    for k, src in ICON_SRC.items():
        ICON[k] = at; at += 0x30
    MTAB = at; at += 12 * len(MOD41) + 4
    HOOK_INIT = (at + 0x1f) & ~0x1f; at = HOOK_INIT + 0x80
    HOOK_B2 = at; at += 0xa0
    STAGE_TAB = at; at += 12 * 6 + 4
    APPLY = (at + 0x1f) & ~0x1f; at = APPLY + 0x60
    if look == 'own':                                   # cclook.py: own presets for colour mode 1, PRO Neg. Hi stock
        import cclook
        lay = cclook.layout(at); at = lay['end']
        b2 = [(a, o, n, 1 if any(a == t[0] for t in cclook.TONE) else 0) for a, o, n in cclook.words(lay, asm)]
    else:
        b2 = [(FSIM2CM, CM_OLD, CM_NEW, 0)]
    B2TAB = at; at += 16 * len(b2) + 4
    assert at <= 0xc000, f'filler full ({at:#x})'
    assert all(x == 0xff for x in L[LIST:at]), 'filler not free'
    lst = b''.join(struct.pack('<II', r, 0) for r in STOCK_ROWS + [10]) + struct.pack('<II', END, 0)
    L[LIST:LIST + len(lst)] = lst
    for k, src in ICON_SRC.items():
        t = [struct.unpack_from('<I', m41, src - M41_BASE + 4 * i)[0] for i in range(10)] + [ICON_ID]
        L[ICON[k]:ICON[k] + 44] = struct.pack('<11I', *t)
    mt = b''.join(struct.pack('<3I', a, old, ICON[new] if isinstance(new, str) else new) for a, old, new in MOD41)
    L[MTAB:MTAB + len(mt) + 4] = mt + bytes(4)
    code = asm(f'''
    {imm('r12', MOD41_INIT)}
    cmp r3, r12
    bxne r3
    push {{r0, r1, r2, r4, r5, lr}}
    {imm('r4', MTAB)}
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
    assert len(code) <= 0x80
    L[HOOK_INIT:HOOK_INIT + len(code)] = code
    if look == 'own':
        for ad, blob in cclook.blobs(lay, asm).items(): L[ad:ad + len(blob)] = blob
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
    markers = [(ROW10, END, 13), (ROW10 + 8, END, 6)] + [(a, lst_, LIST) for a, lst_ in NODES] + [
        (SITE_INIT, BLX_R3, bl(SITE_INIT, HOOK_INIT)),
        (SITE_B2, bl(SITE_B2, START_B2), bl(SITE_B2, HOOK_B2))]
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
    return APPLY, {'list': LIST, 'icon': ICON, 'mtab': MTAB, 'hook_init': HOOK_INIT, 'hook_b2': HOOK_B2, 'b2tab': B2TAB,
                   'stage_tab': STAGE_TAB, 'apply': APPLY, 'markers': markers, 'look': look, 'end': at}
