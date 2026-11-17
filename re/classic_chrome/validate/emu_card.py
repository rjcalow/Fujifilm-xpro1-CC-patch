# Emulator test for the 11th film-simulation entry on the SD-boot card (features/menus.py, rawconv.py;
# convert.py). Runs the real firmware code around every hook.
# usage: emu_card.py <official FPUPDATE.DAT> <ffboot.bin> <re/work dir> <flash firmware FPUPDATE.DAT (v2 build)>
#   1 stage B (loader final jump → blob1 entry): blob1 changes = cchook call sites + marker + the fsim11 table
#     (row 10, two menu-list pointers, two call sites); new list = stock + row 10.
#   2 real conversion engine blob1 0x78a9ec after stage B: stored 13 → MODE_FSIM 6, menu row 10 → 13, 6 → row 10,
#     and the ten stock rows unchanged.
#   3 language hook: real blob1 0x86334c(k), 35 languages → text 819 = CLASSIC CHROME, 1215 = U+F2B9 (followed like
#     the firmware: table entry → descriptor → string), only those two descriptor words + the tail change,
#     PRO Neg. Hi text unchanged, no foreign match; failed read → nothing written.
#   4 module hook: the patched `bl` at 0x9717b8 with module 0x41 in RAM and r3 = its init → exactly the six module
#     words change, then control reaches 0x1430170 with lr = 0x9717bc and r0-r5 / sp kept; another module's init
#     → straight through, nothing changed.
#   5 blob2 hook: the patched `bl` at 0x972520 with blob2 in RAM → 0xf396b0[5] 1 → 7 only, then 0x854e48 with
#     registers kept; real blob2 FUN_00f38780(fsim 6) → colour mode 7.
import os, struct, sys, zlib
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
HERE = os.path.dirname(os.path.abspath(__file__))
for _p in ('..', '../..', '../../tools', '../../../public'): sys.path.insert(0, os.path.normpath(os.path.join(HERE, _p)))
from classic_chrome.engine import chain as C, hooks as H
from classic_chrome.features import texts as uitext
import card_map

dat, boot, W, flash = sys.argv[1:5]
# optional 5th argument: the card's film simulations in row order (convert.py: --sim + --add), default Classic Chrome
from dataclasses import replace
from classic_chrome.config.film_sims import SIMS
SIMS_ON = [replace(SIMS[k], row=10 + n) for n, k in enumerate((sys.argv[5] if len(sys.argv) > 5 else 'classic_chrome').split(','))]
MULTI = len(SIMS_ON) > 1
img = bytes(x ^ 0xff for x in open(dat, 'rb').read())
F = card_map.for_image(img)
from classic_chrome.features import menus as M
fimg = bytes(x ^ 0xff for x in open(flash, 'rb').read())
ffboot = open(boot, 'rb').read()
m = ffboot.find(struct.pack('<I', 0x4e494843)); _, po, pl, ol, crc = struct.unpack('<5I', ffboot[m - 0x14:m])
loader = zlib.decompress(ffboot[po:po + pl], -15)
b1 = open(os.path.join(W, 'blob1.bin'), 'rb').read(); b2 = open(os.path.join(W, 'blob2.bin'), 'rb').read()
m41 = img[F.M41_FILE:F.M41_FILE + 0x9a9a0]
ok = True
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(f'{"OK  " if cond else "FAIL"} {name} {detail}')
W32 = lambda b, o: struct.unpack('<I', b[o:o + 4])[0]
STOP = 0x1f00000
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5]

mu = Uc(UC_ARCH_ARM, UC_MODE_ARM); mu.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_R5)
mu.mem_map(0, 0x2000000); mu.mem_map(0x40000000, 0x4000000); mu.mem_map(0xf0000000, 0x10000000)
mu.mem_write(0, loader)
mu.mem_write(0x40000, img[0x8025c:0x8025c + 0xd7a0]); mu.mem_write(0xd0000, img[0xa025c:0xa025c + 0xd760])
mu.mem_write(0x774000, b1); mu.mem_write(C.UI_DB, img[0xc8025c:0xc8025c + C.UI_DB_LEN])
mu.mem_write(C.BOOTINFO, struct.pack('<3I', 0x0145, 2, 0xd540))
st = {}
def code(uc, a, s, u):
    if a == 0x42c88:
        uc.reg_write(UC_ARM_REG_R0, 0); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR)); return
    if a == 0x8554c4 and st.get('phase') == 'loader': st['at_blob1'] = True; uc.emu_stop(); return
    if a in (STOP, st.get('stop')): uc.emu_stop(); return
    if a == H.FN_LANG and st.get('phase') == 'lang':
        r = [uc.reg_read(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        uc.mem_write(r[2], st['blk'])
        uc.reg_write(UC_ARM_REG_R0, st['ret']); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR)); return
mu.hook_add(UC_HOOK_CODE, code)

# ---- 1 stage B
st['phase'] = 'loader'
mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, 0x3f00)
mu.reg_write(UC_ARM_REG_R0, 0x8554c4); mu.reg_write(UC_ARM_REG_R3, 0x40020)
try: mu.emu_start(0x405c, 0xffffffff, count=60_000_000)
except UcError as e: print('loader run error', e, hex(mu.reg_read(UC_ARM_REG_PC)))
check('loader side reaches blob1 entry', st.get('at_blob1'))
now = bytes(mu.mem_read(0x774000, len(b1)))
diff = sorted({(i & ~3) + 0x774000 for i in range(len(b1)) if now[i] != b1[i]})
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM
ks = Ks(KS_ARCH_ARM, KS_MODE_ARM); bl = lambda frm, to: struct.unpack('<I', bytes(ks.asm(f'bl {to:#x}', frm)[0]))[0]
L = bytes(mu.mem_read(0, 0x10000))
# locate the card's stage table in the loader filler (markers {addr, old, new}; the base part's come first:
# one entry: conversion-table row 10 (2 words) + 2 menu nodes; more entries: conversion-table pointer + 2 nodes)
node0 = L.find(struct.pack('<2I', *M.NODES[0])); tab = node0 - (12 if MULTI else 24); marks = []
while W32(L, tab): marks.append(struct.unpack('<3I', L[tab:tab + 12])); tab += 12
want = sorted([0x857a98, H.SITE_LANG] + [x for x, _ in H.DB_SITES] + [a for a, _, _ in marks])
check('stage B changed exactly: Ver3.89 marker + cchook sites + the card table', diff == want, str([hex(x) for x in diff]))
RC = any(a == F.RC_NODE for a, _, _ in marks)                          # --rawconv: list + table pointer
check('card table applied (every entry holds its new word)', all(W32(now, a - 0x774000) == new for a, _, new in marks)
      and (marks[0][0] == (M.CONV_PTR if MULTI else F.ROW10)))
LIST = marks[1 if MULTI else 2][2]
ROWS_NEW = [s.row for s in SIMS_ON]
lst = [W32(L, LIST + 4 * i) for i in range(2 * (11 + len(SIMS_ON)))]
check(f'new menu list = stock rows + rows {ROWS_NEW}', lst == sum(([r, 0] for r in F.STOCK_ROWS + ROWS_NEW + [F.END]), []))

def call(fn, regs, sp=0x1e00000, stop=STOP, lr=STOP):
    mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, sp); mu.reg_write(UC_ARM_REG_LR, lr)
    for r, v in zip(REGS, regs): mu.reg_write(r, v)
    mu.mem_write(sp - 0x100, b'\xa5' * 0x200); st['stop'] = stop
    try: mu.emu_start(fn, 0xffffffff, count=3_000_000)
    except UcError as e: return ('error', str(e), hex(mu.reg_read(UC_ARM_REG_PC)))
    if mu.reg_read(UC_ARM_REG_PC) != stop: return ('no stop', hex(mu.reg_read(UC_ARM_REG_PC)))
    above = bytes(mu.mem_read(sp, 0x100)) == b'\xa5' * 0x100
    return ('ok', [mu.reg_read(r) for r in REGS], mu.reg_read(UC_ARM_REG_SP) == sp and above, mu.reg_read(UC_ARM_REG_LR))

# ---- 2 real conversion engine
conv = lambda v, frm, to: call(0x78a9ec, [0x3d, v, frm, to])[1][0]
check('stored 13 → MODE_FSIM 6', conv(13, 1, 3) == 6)
check('menu row 10 → stored 13; MODE_FSIM 6 → row 10', conv(10, 0, 1) == 13 and conv(6, 3, 0) == 10)
check('ten stock rows unchanged', [conv(r, 0, 3) for r in range(10)] == [0, 3, 1, 8, 9, 10, 7, 11, 12, 5]
      and [conv(r, 0, 1) for r in range(10)] == [0, 2, 1, 3, 4, 5, 6, 11, 12, 7])
if MULTI:
    check('rows 11+: row → stored → MODE_FSIM, and back to the row for looks',
          all(conv(s.row, 0, 1) == s.stored and conv(s.stored, 1, 3) == s.mode_fsim and conv(s.stored, 1, 0) == s.row
              and (s.is_recipe or conv(s.mode_fsim, 3, 0) == s.row) for s in SIMS_ON),
          str([(s.key, conv(s.row, 0, 1), conv(s.stored, 1, 3)) for s in SIMS_ON]))

# ---- 3 language hook
st['phase'] = 'lang'; bad = []
entries, _ = F.lang(img)
def text_of(blk, tid):
    d = W32(blk, uitext.base_of(blk) + 8 * tid + 4) - uitext.RAM; s = W32(blk, d)
    if not s: return ''
    s -= uitext.RAM; e = s
    while blk[e:e + 2] != b'\0\0': e += 2
    return blk[s:e].decode('utf-16le')
for k in range(35):
    a = uitext.FILE0 + k * uitext.BLOCK; org = fimg[a:a + uitext.BLOCK]
    if org != img[a:a + uitext.BLOCK]: bad.append((k, 'flash language block differs from the official one')); continue
    st['blk'] = org; st['ret'] = 0x55 if k == 1 else 0
    r = call(0x86334c, [k])
    got = bytes(mu.mem_read(uitext.RAM, uitext.BLOCK))
    if r[0] != 'ok' or r[1][0] != st['ret'] or not r[2]: bad.append((k, r[:3])); continue
    ch = sorted({i & ~3 for i in range(uitext.BLOCK) if got[i] != org[i]})
    b = uitext.base_of(org)
    descs = sorted(W32(org, b + 8 * t + 4) - uitext.RAM for t in (F.NAME_ID, F.ICON_ID))
    if [c for c in ch if c < H.TAIL] != descs or any(c >= H.TAIL + H.TAIL_LEN for c in ch): bad.append((k, 'changed set')); continue
    if text_of(got, F.NAME_ID) != 'CLASSIC CHROME' or text_of(got, F.ICON_ID) != '': bad.append((k, 'texts')); continue
    if any(text_of(got, t) != text_of(org, t) for t in (655, 813, 1204, 4018 % 1693)): bad.append((k, 'other text changed'))
    foreign = [e for e in entries if W32(org, e[0] - uitext.RAM) == e[1] and (e[0] - uitext.RAM) not in descs]
    if foreign: bad.append((k, 'foreign match', foreign))
check('language hook: 35 blocks → 819 CLASSIC CHROME, 1215 U+F2B9, only 2 descriptors + tail, r0/stack kept', not bad, str(bad[:3]))
st['blk'] = b'\xff' * uitext.BLOCK; st['ret'] = 0xffffffe2
r = call(0x86334c, [1]); got = bytes(mu.mem_read(uitext.RAM, uitext.BLOCK))
check('language hook: failed read → no descriptor written, error kept', r[0] == 'ok' and r[1][0] == 0xffffffe2 and got[:H.TAIL] == b'\xff' * H.TAIL)

# ---- 4 module 0x41 hook
st['phase'] = 'mod'
mu.mem_write(F.M41_BASE, m41)
regs = [0x11, 0x22, 0x33, F.MOD41_INIT, 0x1420000, 0x55]
r = call(F.SITE_INIT, regs, stop=F.MOD41_INIT, lr=0xdead0000)
got = bytes(mu.mem_read(F.M41_BASE, len(m41)))
ch = sorted({(i & ~3) + F.M41_BASE for i in range(len(m41)) if got[i] != m41[i]})
check('module hook: reaches the module init with lr = 0x9717bc, r0-r5 and sp kept',
      r[0] == 'ok' and r[1] == regs and r[2] and r[3] == F.SITE_INIT + 4, str(r[:1] + r[3:]))
G = lambda a: W32(got, a - F.M41_BASE)
looks_on = [s for s in SIMS_ON if not s.is_recipe]
rowmap_words = sorted({(t + s.mode_fsim) & ~3 for t in M.ROW_MAPS for s in looks_on})
mod41 = [M.NAME_MOVW, M.NAME_MOVT, M.ROW_CAP] + [f for _, fl in M.ICON_TABS.values() for f in fl] + rowmap_words \
    + ([M.DRAW_SITE] if MULTI else []) + ([F.RC_CAP, F.RC_MOVW, F.RC_MOVT, F.RC_ICON_FIELD] if RC else [])
check(f'module hook: exactly the {len(mod41)} module words changed (WHITE BALANCE names 0x1483c48 untouched)',
      ch == sorted(mod41) and 0x1483c48 not in ch, str([hex(x) for x in ch]))
dec = lambda w: ((w >> 4) & 0xf000) | (w & 0xfff)
NT = dec(G(M.NAME_MOVW)) | dec(G(M.NAME_MOVT)) << 16
names = [W32(L, NT + 4 * i) for i in range(10 + len(SIMS_ON))]
drawn_ok = all(L[names[s.row]:names[s.row] + len(s.name) + 1] == s.name.encode() + b'\0' for s in SIMS_ON if s.row > 10)
check(f'module hook: name table copied (10 stock + 819{" + drawn names" if MULTI else ""}), row limit cmp r4,#{ROWS_NEW[-1]}',
      names[:10] == [W32(m41, M.NAME_TAB - F.M41_BASE + 4 * i) for i in range(10)] and names[10] == F.NAME_ID
      and drawn_ok and G(M.ROW_CAP) == 0xe3540000 | ROWS_NEW[-1], str(names[10:]))
iA, iB = G(0x14299fc), G(0x1429a00)
n = 10 + len(SIMS_ON)
tA = [W32(L, iA + 4 * i) for i in range(n)]; tB = [W32(L, iB + 4 * i) for i in range(n)]
check(f'module hook: both FILM SIMULATION records → {n}-entry icon tables (stock + new rows\' icons)',
      G(0x142bd98) == iA and G(0x142bd9c) == iB
      and tA == [W32(m41, 0x142aa4c - F.M41_BASE + 4 * i) for i in range(10)] + [s.icon_ab[0] for s in SIMS_ON]
      and tB == [W32(m41, 0x1427320 - F.M41_BASE + 4 * i) for i in range(10)] + [s.icon_ab[1] for s in SIMS_ON])
exp_map = [0, 2, 0, 1, 5, 9, 10, 5, 7, 6, 8, 4, 3]
for s in looks_on: exp_map[s.mode_fsim] = s.row
check('module hook: MODE_FSIM → row maps give the new looks\' rows, stock rows otherwise',
      all(list(got[t - F.M41_BASE:t - F.M41_BASE + 13]) == exp_map for t in M.ROW_MAPS), str(exp_map))
if MULTI:
    check('module hook: name draw call → the card\'s DRAW stub', G(M.DRAW_SITE) != W32(m41, M.DRAW_SITE - F.M41_BASE))
mu.mem_write(F.M41_BASE, m41)
r = call(F.SITE_INIT, [1, 2, 3, 0x14c0040, 5, 6], stop=0x14c0040)
check('module hook: other init → straight through, nothing changed',
      r[0] == 'ok' and r[3] == F.SITE_INIT + 4 and bytes(mu.mem_read(F.M41_BASE, len(m41))) == m41)

# ---- 5 blob2 hook
mu.mem_write(F.B2_BASE, b2)
regs = [0x77, 0x88, 0x99, 3, 4, 5]
r = call(F.SITE_B2, regs, stop=F.START_B2, lr=0xdead0000)
got = bytes(mu.mem_read(F.B2_BASE, len(b2)))
ch = sorted({(i & ~3) + F.B2_BASE for i in range(len(b2)) if got[i] != b2[i]})
tab = L.find(struct.pack('<2I', F.FSIM2CM, F.CM_OLD))                 # the card's blob2 patch table (HOOK_B2)
if tab < 0: tab = L.find(struct.pack('<2I', 0xf333c4, 0x13a02000))
ent = []
while True:
    a, o, n, fl = struct.unpack('<4I', L[tab:tab + 16])
    if a == 0: break
    ent.append((a, o, n, fl)); tab += 16
own = F.FSIM2CM not in [a for a, *_ in ent]
exp = sorted(a for a, o, n, fl in ent if not fl)                        # stock blob1 here: no curve 38 -> tone entries skipped
check(f'blob2 hook: {"own look: 14 matrix words" if own else "only 0xf396b0[5] 1 → 7"}, nothing else',
      ch == exp and all(W32(got, a - F.B2_BASE) == n for a, o, n, fl in ent if not fl), str([hex(x) for x in ch]))
check('blob2 hook: reaches 0x854e48 with lr = 0x972524 and r0-r5, sp kept',
      r[0] == 'ok' and r[1] == regs and r[2] and r[3] == F.SITE_B2 + 4, str(r[:1] + r[3:]))
r = call(0xf38780, [0x1e00800, 6]); cm = W32(bytes(mu.mem_read(0x1e00800, 4)), 0)
check(f'real blob2 FUN_00f38780: MODE_FSIM 6 → colour mode {1 if own else 7}, 12 (PRO Neg. Hi) → 7, 1 (ASTIA) → 5',
      cm == (1 if own else 7) and (call(0xf38780, [0x1e00800, 12]), W32(bytes(mu.mem_read(0x1e00800, 4)), 0))[1] == 7
      and (call(0xf38780, [0x1e00800, 1]), W32(bytes(mu.mem_read(0x1e00800, 4)), 0))[1] == 5)
mu.mem_write(F.B2_BASE, b2); mu.mem_write(ent[0][0], struct.pack('<I', 0x12345678))
call(F.SITE_B2, regs, stop=F.START_B2, lr=0xdead0000)
check('blob2 hook: unexpected old value → unchanged', W32(bytes(mu.mem_read(ent[0][0], 4)), 0) == 0x12345678)

# ---- 6 RAW CONVERSION menu (--rawconv)
if RC:
    conv = lambda v, frm, to: call(0x78a9ec, [0x152, v, frm, to])[1][0]
    check('rawconv: real conversion engine, setting 0x152: row 10 → code 8, ten stock rows unchanged',
          conv(10, 0, 3) == 8 and [conv(r, 0, 3) for r in range(10)] == F.RC_CODES, str((conv(10, 0, 3), [conv(r, 0, 3) for r in range(10)])))
    def run_mid(fn, regs):                      # enter a chain mid-function: the frame it pops returns to STOP
        sp = 0x1e00000
        mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, sp); mu.reg_write(UC_ARM_REG_LR, STOP)
        mu.mem_write(sp, struct.pack('<8I', *([STOP] * 8)))
        for r, v in regs.items(): mu.reg_write(r, v)
        st['stop'] = STOP
        try: mu.emu_start(fn, 0xffffffff, count=100_000)
        except UcError as e: return 'error'
        return 'ok' if mu.reg_read(UC_ARM_REG_PC) == STOP else 'no stop'
    lst2 = W32(now, F.RC_NODE - 0x774000)
    check('rawconv: setting 0x152 list = stock rows + row 10', [W32(L, lst2 + 4 * i) for i in range(24)] == sum(([r, 0] for r in F.RC_ROWS + [10, F.END]), []))
    # blob2 apply chain (r6 = row) and cursor chain, after HOOK_B2 (blob2 already patched above)
    def apply_row(row):
        mu.mem_write(0x9d4d28, bytes(0x40))
        r = run_mid(0xf10ee0, {UC_ARM_REG_R6: row}); blk = bytes(mu.mem_read(0x9d4d28, 0x40))
        return r, W32(blk, 8), W32(blk, 0x1c)
    check('rawconv: real apply chain: row 10 → film code 8 / COLOR 0; row 1 → 5; row 3 → COLOR 6; row 11 → 0/0',
          apply_row(10) == ('ok', 8, 0) and apply_row(1) == ('ok', 5, 0) and apply_row(3) == ('ok', 0, 6) and apply_row(11) == ('ok', 0, 0),
          str([apply_row(r) for r in (10, 1, 3, 11)]))
    def cursor(code, colour):
        mu.mem_write(0x9d4d28, bytes(0x40)); mu.mem_write(0x9d4d30, struct.pack('<I', code)); mu.mem_write(0x9d4d44, struct.pack('<I', colour))
        r = run_mid(0xf1f8f8, {UC_ARM_REG_R4: 0x7777}); return r, mu.reg_read(UC_ARM_REG_R0)
    check('rawconv: real cursor chain: code 8 → row 10; 7 → 8; 0 → 0; COLOR 10 → 9',
          cursor(8, 0) == ('ok', 10) and cursor(7, 0) == ('ok', 8) and cursor(0, 0) == ('ok', 0) and cursor(0, 10) == ('ok', 9),
          str([cursor(*a) for a in ((8, 0), (7, 0), (0, 0), (0, 10))]))
    # module 0x41 words
    nt = (W32(got, F.RC_MOVW - F.M41_BASE) & 0xfff) | ((W32(got, F.RC_MOVW - F.M41_BASE) >> 4) & 0xf000) if False else None
    g41 = got
    mu.mem_write(F.M41_BASE, m41); call(F.SITE_INIT, [0] * 3 + [F.MOD41_INIT, 0, 0], stop=F.MOD41_INIT); g41 = bytes(mu.mem_read(F.M41_BASE, len(m41)))
    mw, mt = W32(g41, F.RC_MOVW - F.M41_BASE), W32(g41, F.RC_MOVT - F.M41_BASE)
    dec = lambda w: ((w >> 4) & 0xf000) | (w & 0xfff)
    name_tab = dec(mw) | (dec(mt) << 16); icon_tab = W32(g41, F.RC_ICON_FIELD - F.M41_BASE)
    check('rawconv: module 0x41: row cap 10, name table (stock 10 + 819) and icon table (stock 10 + 1215) repointed',
          W32(g41, F.RC_CAP - F.M41_BASE) == 0xe354000a
          and [W32(L, name_tab + 4 * i) for i in range(11)] == [W32(m41, F.RC_NAME_TAB - F.M41_BASE + 4 * i) for i in range(10)] + [F.NAME_ID]
          and [W32(L, icon_tab + 4 * i) for i in range(11)] == [W32(m41, F.RC_ICON_TAB - F.M41_BASE + 4 * i) for i in range(10)] + [F.ICON_ID])
    # module 0x44 hook + the real request builder switch (r4 = RAW-convert block)
    m44 = img[F.M44_FILE:F.M44_FILE + 0xe0000]
    mu.mem_write(F.M44_BASE, m44)
    r = call(F.SITE_INIT, [0x11, 0x22, 0x33, F.MOD44_INIT, 0x44, 0x55], stop=F.MOD44_INIT, lr=0xdead0000)
    g44 = bytes(mu.mem_read(F.M44_BASE, len(m44)))
    ch44 = sorted({(i & ~3) + F.M44_BASE for i in range(len(m44)) if g44[i] != m44[i]})
    check('rawconv: module 0x44 hook: only the switch default branch changed, init reached with registers kept',
          ch44 == [F.RC_M44] and r[0] == 'ok' and r[1] == [0x11, 0x22, 0x33, F.MOD44_INIT, 0x44, 0x55] and r[2] and r[3] == F.SITE_INIT + 4, str([hex(x) for x in ch44]))
    def m44_switch(code):
        mu.mem_write(0x9d4d28, bytes(0x40)); mu.mem_write(0x9d4d30, struct.pack('<I', code)); mu.mem_write(F.RC_M44_REQ, b'\xee' * 4)
        r = call(0x163289c, [0, 0, 0, 0, 0x9d4d28, 0], stop=F.RC_M44_CONT)
        return r[0], W32(bytes(mu.mem_read(F.RC_M44_REQ, 4)), 0)
    check('rawconv: real module 0x44 switch: code 8 → film sim 6; 3 → 1, 5 → 3, 6 → 11, 7 → 12, 0 → 0, 9 → 0',
          [m44_switch(c) for c in (8, 3, 5, 6, 7, 0, 9)] == [('ok', v) for v in (6, 1, 3, 11, 12, 0, 0)], str([m44_switch(c) for c in (8, 3, 9)]))
print('\nRESULT:', 'ALL OK' if ok else 'FAILED'); sys.exit(0 if ok else 1)
