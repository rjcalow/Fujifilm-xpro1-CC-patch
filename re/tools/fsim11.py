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
M44_FILE, M44_BASE, MOD44_INIT = 0x60025c, 0x15c0000, 0x15c05ec

# RAW CONVERSION menu (rawconv=True; NOTES 2026-11-14/15, logger-proven chain): setting 0x152, film code 8
RC_NODE, RC_LIST, RC_ROWS = 0x778d9c + 0x14, 0x779cf4, [0, 1, 2, 8, 7, 3, 5, 4, 6, 9]
RC_TABPTR, RC_TAB, RC_CODES = 0x78bf58, 0x78adc8, [0, 5, 3, 6, 7, 8, 9, 6, 7, 10]     # 0x78ba10[0x152]; row -> code
RC_CODE, RC_ROW = 8, 10
RC_NAME_TAB, RC_ICON_TAB, RC_ICON_FIELD = 0x14838f4, 0x142e558, 0x142ae18           # module 0x41, screen group 0x1c
RC_CAP, RC_MOVW, RC_MOVT = 0x147c61c, 0x147c624, 0x147c628                          # `cmp r4,#9`, movw/movt r3,=name tab
RC_APPLY, RC_APPLY_OLD, RC_APPLY_CONT, RC_APPLY_DONE = 0xf10ff0, 0xe3043d28, 0xf10ff8, 0xf11024   # blob2 FUN_00f10e58
RC_CUR, RC_CUR_OLD, RC_CUR_ROW0, RC_CUR_SET = 0xf1f960, 0x1a000166, 0xf1ff00, 0xf1ff3c            # blob2 FUN_00f1e248
RC_M44, RC_M44_OLD, RC_M44_CONT, RC_M44_REQ = 0x16328ac, 0xea000004, 0x1632924, 0x121b54c + 0x770 # module 0x44 FUN_016326a4
RC_FSIM = 6


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


def check_rawconv(img, b1, b2, m41):
    """Stock words of the RAW CONVERSION patch; returns module 0x44's image."""
    w = lambda b, base, a: struct.unpack_from('<I', b, a - base)[0]
    m44 = img[M44_FILE:M44_FILE + 0xe0000]
    assert w(b1, B1_BASE, RC_NODE) == RC_LIST and w(b1, B1_BASE, RC_TABPTR) == RC_TAB
    assert [w(b1, B1_BASE, RC_LIST + 4 * i) for i in range(22)] == sum(([r, 0] for r in RC_ROWS + [END]), [])
    assert [[w(b1, B1_BASE, RC_TAB + 12 * i + 4 * k) for k in range(3)] for i in range(10)] == [[END, END, c] for c in RC_CODES]
    assert w(m41, M41_BASE, RC_CAP) == 0xe3540009 and w(m41, M41_BASE, RC_MOVW) == 0xe30338f4 and w(m41, M41_BASE, RC_MOVT) == 0xe3403148
    assert w(m41, M41_BASE, RC_ICON_FIELD) == RC_ICON_TAB
    assert w(b2, B2_BASE, RC_APPLY) == RC_APPLY_OLD and w(b2, B2_BASE, RC_CUR) == RC_CUR_OLD
    assert w(m44, M44_BASE, M44_BASE) == MOD44_INIT and w(m44, M44_BASE, RC_M44) == RC_M44_OLD, 'module 0x44'
    assert w(m44, M44_BASE, RC_M44 - 4) == 0x979ff103, 'module 0x44 jump table'       # ldrls pc, [pc, r3, lsl #2]
    return m44


def install(L, asm, bl, img, start, look='borrow', rawconv=False):
    """crumbs.patch(extra=...) body: write LIST, icon tables and both hooks into the loader filler from `start`.
    Returns (stage-B markers, info). rawconv=True adds the RAW CONVERSION menu entry (film code 8)."""
    b1, b2, m41 = check(img)
    imm = lambda r, v: f'movw {r}, #{v & 0xffff}\n    movt {r}, #{v >> 16}'
    word = lambda s: struct.unpack('<I', asm(s, 0))[0]
    at = (start + 0x3f) & ~0x3f
    LIST = at; at += 0x60
    ICON = {}
    for k, src in ICON_SRC.items():
        ICON[k] = at; at += 0x30
    mod41 = list(MOD41); mod44 = []; rc = {}
    if rawconv:
        m44 = check_rawconv(img, b1, b2, m41)
        rc['list'] = at; at += 0x60
        rc['tab'] = at; at += 12 * 11 + 4
        rc['name'] = at; at += 0x30
        rc['icon'] = at; at += 0x30
        rc['stub_apply'] = at; at += 0x30
        rc['stub_cur'] = at; at += 0x20
        rc['stub_m44'] = at; at += 0x20
        mod41 += [(RC_CAP, 0xe3540009, 0xe354000a),
                  (RC_MOVW, 0xe30338f4, word(f'movw r3, #{rc["name"] & 0xffff}')),
                  (RC_MOVT, 0xe3403148, word(f'movt r3, #{rc["name"] >> 16}')),
                  (RC_ICON_FIELD, RC_ICON_TAB, rc['icon'])]
        mod44 = [(RC_M44, RC_M44_OLD, bl(RC_M44, rc['stub_m44']) & ~0x01000000)]       # b, not bl
    MTAB = at; at += 12 * len(mod41) + 4
    MTAB44 = at; at += 12 * len(mod44) + 4
    HOOK_INIT = (at + 0x1f) & ~0x1f; at = HOOK_INIT + 0xa0
    HOOK_B2 = at; at += 0xa0
    STAGE_TAB = at; at += 12 * 8 + 4
    APPLY = (at + 0x1f) & ~0x1f; at = APPLY + 0x60
    if look == 'own':                                   # cclook.py: own presets for colour mode 1, PRO Neg. Hi stock
        import cclook
        lay = cclook.layout(at); at = lay['end']
        b2 = [(a, o, n, 1 if any(a == t[0] for t in cclook.TONE) else 0) for a, o, n in cclook.words(lay, asm)]
    else:
        b2 = [(FSIM2CM, CM_OLD, CM_NEW, 0)]
    if rawconv:
        b2 += [(RC_APPLY, RC_APPLY_OLD, bl(RC_APPLY, rc['stub_apply']) & ~0x01000000, 0),
               (RC_CUR, RC_CUR_OLD, (bl(RC_CUR, rc['stub_cur']) & 0x00ffffff) | 0x1a000000, 0)]   # bne
    B2TAB = at; at += 16 * len(b2) + 4
    assert at <= 0xc000, f'filler full ({at:#x})'
    assert all(x == 0xff for x in L[LIST:at]), 'filler not free'
    lst = b''.join(struct.pack('<II', r, 0) for r in STOCK_ROWS + [10]) + struct.pack('<II', END, 0)
    L[LIST:LIST + len(lst)] = lst
    for k, src in ICON_SRC.items():
        t = [struct.unpack_from('<I', m41, src - M41_BASE + 4 * i)[0] for i in range(10)] + [ICON_ID]
        L[ICON[k]:ICON[k] + 44] = struct.pack('<11I', *t)
    if rawconv:
        lst = b''.join(struct.pack('<II', r, 0) for r in RC_ROWS + [RC_ROW]) + struct.pack('<II', END, 0)
        L[rc['list']:rc['list'] + len(lst)] = lst
        tab = b''.join(struct.pack('<3I', END, END, c) for c in RC_CODES + [RC_CODE]) + bytes(4)
        L[rc['tab']:rc['tab'] + len(tab)] = tab
        t = [struct.unpack_from('<I', m41, RC_NAME_TAB - M41_BASE + 4 * i)[0] for i in range(10)] + [NAME_ID]
        L[rc['name']:rc['name'] + 44] = struct.pack('<11I', *t)
        t = [struct.unpack_from('<I', m41, RC_ICON_TAB - M41_BASE + 4 * i)[0] for i in range(10)] + [ICON_ID]
        L[rc['icon']:rc['icon'] + 44] = struct.pack('<11I', *t)
        # apply (blob2, r6 = menu row): row 10 -> block +8 = film code 8; other rows -> stock default path
        code = asm(f'''
    cmp r6, #{RC_ROW}
    {imm('r3', 0x9d4d28)}
    moveq r2, #{RC_CODE}
    streq r2, [r3, #8]
    beq {RC_APPLY_DONE:#x}
    b {RC_APPLY_CONT:#x}''', rc['stub_apply']); assert len(code) <= 0x30
        L[rc['stub_apply']:rc['stub_apply'] + len(code)] = code
        # cursor (blob2, r3 = film code, r4 = row out): code 8 -> row 10; else stock "row 0"
        code = asm(f'''
    cmp r3, #{RC_CODE}
    moveq r4, #{RC_ROW}
    beq {RC_CUR_SET:#x}
    b {RC_CUR_ROW0:#x}''', rc['stub_cur']); assert len(code) <= 0x20
        L[rc['stub_cur']:rc['stub_cur'] + len(code)] = code
        # module 0x44 request builder (r3 = film code - 3): code 8 -> MODE_FSIM 6, else 0 (stock default)
        code = asm(f'''
    cmp r3, #{RC_CODE - 3}
    {imm('r3', RC_M44_REQ)}
    moveq r2, #{RC_FSIM}
    movne r2, #0
    str r2, [r3]
    b {RC_M44_CONT:#x}''', rc['stub_m44']); assert len(code) <= 0x20
        L[rc['stub_m44']:rc['stub_m44'] + len(code)] = code
    mt = b''.join(struct.pack('<3I', a, old, ICON[new] if isinstance(new, str) else new) for a, old, new in mod41)
    L[MTAB:MTAB + len(mt) + 4] = mt + bytes(4)
    mt = b''.join(struct.pack('<3I', *e) for e in mod44)
    L[MTAB44:MTAB44 + len(mt) + 4] = mt + bytes(4)
    code = asm(f'''
    push {{r0, r1, r2, r4, r5, lr}}
    {imm('r12', MOD41_INIT)}
    cmp r3, r12
    {imm('r4', MTAB)}
    beq m_loop
    {imm('r12', MOD44_INIT)}
    cmp r3, r12
    {imm('r4', MTAB44)}
    bne m_done
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
    if rawconv:
        markers += [(RC_NODE, RC_LIST, rc['list']), (RC_TABPTR, RC_TAB, rc['tab'])]
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
    return APPLY, {'list': LIST, 'icon': ICON, 'mtab': MTAB, 'mtab44': MTAB44, 'hook_init': HOOK_INIT, 'hook_b2': HOOK_B2,
                   'b2tab': B2TAB, 'stage_tab': STAGE_TAB, 'apply': APPLY, 'markers': markers, 'look': look,
                   'rawconv': rc, 'mod41': mod41, 'mod44': mod44, 'b2': b2, 'end': at}
