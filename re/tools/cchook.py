# SD dual boot: Classic Chrome v3 values + menu name, applied in RAM by two run-time hooks (flash is not written).
# Used by crumbs.patch(..., cc=True) / build_sdchain.py --crumbs --cc. Test: emu_cchook.py.
#
# Why hooks and not a patch at stage B: both data sets are read from flash AFTER the firmware has started.
#   * Tuning area, two paths, both hooked: at start-up blob1 0x858394 (called once, from the start-up task at
#     0x8550d4) reads it through 0x862b24; the reload 0x857e44 = load(0x40d3b580, 0xb3700) through 0x863940 is called
#     from blob2 (0xf28578, 0xf7da88, 0xf8150c). The compiled copy in blob1 (0x812470) is not the source.
#     (The first card hooked only the reload: the 2026-11-12 conversion DSCF2759 still had the v2 values.)
#   * Language block: blob1 0x86334c(language 0..0x22) reads one block to 0x4f0000 via 0x8632a4 (callers 0x7a0290,
#     0x970d2c: start-up and language change).
# Stage B replaces the three `bl` instructions (old word checked) with calls to the hooks below. The hooks live in
# the loader's 0xff filler at 0xa400..0xbfff. That area is still 0xff in a running firmware (read over USB
# 2026-11-12), and MPU region 0 (0..256 MB, set by the loader 0x41e8) is executable.
#   HOOK_DB0/1: call 0x858394 / 0x863940, then for each (address, old u16, new u16): bytes equal old → write new.
#   HOOK_LANG: call 0x8632a4, then write a uiname.py-compatible tail at block offset 0x1f000 (free in all 35
#              blocks) and repoint each text descriptor whose pointer equals its original value. The table has
#              the 105 descriptors of all languages; an entry only matches in its own language (checked offline
#              by emu_cchook.py). `uiname.py show / restore` work on the result.
# Both keep r0 (the loader's return value) and use 24 bytes of the caller's stack.
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uiname
from build_cc3 import PARAMS3

AREA, AREA_END = 0xa400, 0xc000
DB_RAM = 0x40d3b580
DB_SITES = [(0x8550d4, 0x858394), (0x857e5c, 0x863940)]      # (call site, original target): start-up, reload
SITE_DB, FN_DB = DB_SITES[1]
SITE_LANG, FN_LANG = 0x863388, 0x8632a4
TAIL = 0x1f000                                        # block offset of the rename tail (RAM 0x50f000)
T_PLAIN, T_PRE, T_SUF = 0x20, 0x40, 0x60              # string offsets inside the tail
TAIL_LEN = 0x80


def tail_template(new=uiname.NEW):
    assert len(new) <= 14, 'name: at most 14 characters for the SD-boot hook'
    t = bytearray(TAIL_LEN)
    t[0:8] = uiname.MAGIC + struct.pack('<I', 3)
    t[8:0x20] = b'\xff' * 0x18                        # records, filled by the hook
    for off, text in ((T_PLAIN, new), (T_PRE, '' + new), (T_SUF, new + '')):
        s = text.encode('utf-16le') + b'\0\0'; t[off:off + len(s)] = s
    return bytes(t)


def lang_table(img, old=uiname.OLD):
    """[(descriptor RAM address, original pointer, new pointer)] for all language blocks of the decoded image."""
    out = []
    for k in range(uiname.NBLOCKS):
        a = uiname.FILE0 + k * uiname.BLOCK; blk = img[a:a + uiname.BLOCK]
        assert all(x == 0xff for x in blk[TAIL - 16:]), f'language block {k}: tail area in use'
        for d, ptr, text in uiname.find_recs(blk, old):
            pre, _, suf = text.partition(old)
            out.append((uiname.RAM + d, ptr, uiname.RAM + TAIL + (T_PRE if pre else T_SUF if suf else T_PLAIN)))
    return out


def install(L, img, asm, bl):
    """Write hooks + tables into the loader image L. Returns the blob1 patches for stage B: [(addr, old, new)]."""
    assert all(b == 0xff for b in L[AREA:AREA_END]), 'hook area is not free filler'
    imm = lambda r, v: f'movw {r}, #{v & 0xffff}\n    movt {r}, #{v >> 16}'
    db = b''.join(struct.pack('<IHH', DB_RAM + pid, *struct.unpack('<HH', bytes.fromhex(old + new)))
                  for pid, old, new in PARAMS3) + bytes(8)
    lt = lang_table(img); lang = b''.join(struct.pack('<3I', *e) for e in lt) + bytes(12)
    tmpl = tail_template()
    HOOK_DB = [AREA, AREA + 0x80]; HOOK_LANG = AREA + 0x100; DATA = AREA + 0x1c0
    DB_TAB = DATA; TMPL = DB_TAB + len(db); LANG_TAB = TMPL + len(tmpl)
    assert LANG_TAB + len(lang) <= AREA_END
    db_hook = lambda fn, at: asm(f'''
    push {{r4, r5, r6, r7, r8, lr}}
    bl {fn:#x}
    mov r4, r0
    {imm('r5', DB_TAB)}
db_loop:
    ldr r1, [r5], #4
    cmp r1, #0
    beq db_done
    ldrh r2, [r5], #2
    ldrh r3, [r5], #2
    ldrb r6, [r1]
    ldrb r7, [r1, #1]
    orr r6, r6, r7, lsl #8
    cmp r6, r2
    bne db_loop
    strb r3, [r1]
    lsr r3, r3, #8
    strb r3, [r1, #1]
    b db_loop
db_done:
    mov r0, r4
    pop {{r4, r5, r6, r7, r8, pc}}''', at)
    code_db = [db_hook(fn, at) for (_, fn), at in zip(DB_SITES, HOOK_DB)]
    code_lang = asm(f'''
    push {{r4, r5, r6, r7, r8, lr}}
    bl {FN_LANG:#x}
    mov r4, r0
    {imm('r5', TMPL)}
    {imm('r6', uiname.RAM + TAIL)}
    mov r7, #{TAIL_LEN // 4}
tl_copy:
    ldr r1, [r5], #4
    str r1, [r6], #4
    subs r7, r7, #1
    bne tl_copy
    {imm('r6', uiname.RAM + TAIL + 8)}
    {imm('r5', LANG_TAB)}
    {imm('r8', 0x00640064)}
ln_loop:
    ldr r1, [r5], #4
    cmp r1, #0
    beq ln_done
    ldr r2, [r5], #4
    ldr r3, [r5], #4
    ldr r7, [r1]
    cmp r7, r2
    bne ln_loop
    ldr r7, [r1, #4]
    cmp r7, r8
    bne ln_loop
    str r3, [r1]
    sub r1, r1, #{uiname.RAM:#x}
    str r1, [r6], #4
    str r2, [r6], #4
    b ln_loop
ln_done:
    mov r0, r4
    pop {{r4, r5, r6, r7, r8, pc}}''', HOOK_LANG)
    assert all(len(c) <= 0x80 for c in code_db) and len(code_lang) <= 0xc0
    for c, at in zip(code_db, HOOK_DB): L[at:at + len(c)] = c
    L[HOOK_LANG:HOOK_LANG + len(code_lang)] = code_lang
    L[DATA:DATA + len(db) + len(tmpl) + len(lang)] = db + tmpl + lang
    sites = [(site, bl(site, fn), bl(site, at)) for (site, fn), at in zip(DB_SITES, HOOK_DB)]
    return sites + [(SITE_LANG, bl(SITE_LANG, FN_LANG), bl(SITE_LANG, HOOK_LANG))], \
           {'hook_db': HOOK_DB, 'hook_lang': HOOK_LANG, 'db_tab': DB_TAB, 'tmpl': TMPL, 'lang_tab': LANG_TAB,
            'lang_entries': len(lt), 'end': LANG_TAB + len(lang)}
