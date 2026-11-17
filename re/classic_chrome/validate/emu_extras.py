# Emulator test for the four-looks additions on the SD-boot card (convert.py --four-looks / --add / --peaking):
# real firmware code after the card's own hooks have run (stage B, module hook, HOOK_B2, tuning hook).
# usage: emu_extras.py <official FPUPDATE.DAT> <ffboot.bin> <re/work dir> <flashed firmware FPUPDATE.DAT> <sims> [--peaking]
#   <sims>: the card's film simulations in row order, e.g. classic_chrome,superia,reggie,kodachrome
#   1 names: module 0x41's row-name lookup (0x147c748) + the card's DRAW stub draw each drawn row's ASCII name
#     (glyphs = 0xE100 + character, as PR #3 checks); row 10 still draws text 819.
#   2 recipes: the real shooting-message producer (blob2 0xf79410 → copy 0xf79434) and the compact capture exporter
#     (blob1 0x9b7254): with a recipe's stored value selected, the message / record = the plain one with exactly the
#     recipe's WB, R/B shifts, Color, Highlight, Shadow and Sharpness; base entries, a recipe's stored value with
#     another MODE_FSIM, and every stock row → unchanged.
#   3 looks with extras (Superia 400): FUN_00f38780 MODE_FSIM → colour mode; the real 3x3 (FUN_00f32fcc, sRGB/alt,
#     3 modes), 2x2 (FUN_00f2d404, FUN_00f30b10), chroma gain (FUN_00f2c8fc) and tone (FUN_00f321f0 /
#     FUN_00f3232c, 9 variants) for the new colour mode = those of the stock colour modes it borrows; Classic
#     Chrome (colour mode 1) and the stock colour modes unchanged by the extra stubs.
#   4 --peaking: the real tuning hook (0x857e44) writes the three focus-peaking bytes.
import os, struct, sys, zlib
from dataclasses import replace
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
HERE = os.path.dirname(os.path.abspath(__file__))
for _p in ('..', '../..', '../../tools', '../../../public'): sys.path.insert(0, os.path.normpath(os.path.join(HERE, _p)))
from classic_chrome.engine import chain as C, hooks as H, card as CARD
from classic_chrome.engine.firmware import MODULES
from classic_chrome.config.film_sims import SIMS
from classic_chrome.features import menus as M, recipes as R, peaking as PK, cc_look as K
import xpro1_cc_patch as P

dat, boot, W, flash, keys = sys.argv[1:6]
PEAKING = '--peaking' in sys.argv[6:]
from classic_chrome.config.film_sims import lineup
SIMS_ON = lineup(keys.split(','))
img = bytes(x ^ 0xff for x in open(dat, 'rb').read()); fimg = bytes(x ^ 0xff for x in open(flash, 'rb').read())
ffboot = open(boot, 'rb').read()
m = ffboot.find(struct.pack('<I', 0x4e494843)); _, po, pl, ol, crc = struct.unpack('<5I', ffboot[m - 0x14:m])
loader = zlib.decompress(ffboot[po:po + pl], -15)
b1 = open(os.path.join(W, 'blob1.bin'), 'rb').read(); b2 = open(os.path.join(W, 'blob2.bin'), 'rb').read()
u1, p1 = struct.unpack('<II', fimg[0x10025c:0x100264]); fb1 = P.lz_decode(fimg, 0x10025c + 20, 0x10025c + p1, u1)
m41f, m41b, m41n, m41i = MODULES[0x41]; m41 = img[m41f:m41f + m41n]
stock_db = img[K.DB_FILE:K.DB_FILE + K.DB_LEN]; v2 = fimg[K.DB_FILE:K.DB_FILE + K.DB_LEN]
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
st = {'ids': []}
def code(uc, a, s, u):
    if a == 0x42c88:
        uc.reg_write(UC_ARM_REG_R0, 0); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR)); return
    if a == 0x8554c4 and st.get('phase') == 'loader': st['at_blob1'] = True; uc.emu_stop(); return
    if a == 0xf28ba0 and st.get('phase') == 'pipe':
        st['curves'] = [uc.reg_read(r) for r in REGS[:3]]; uc.emu_stop(); return
    if a in (STOP, st.get('stop')): uc.emu_stop(); return
    if a == H.FN_DB and st.get('phase') == 'db':
        uc.mem_write(H.DB_RAM, st['db']); uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR)); return
    if a == 0x857be0 and st.get('phase') == 'pipe':
        i = uc.reg_read(UC_ARM_REG_R0); st['ids'].append(i)
        uc.reg_write(UC_ARM_REG_R0, st['dbimg'][i]); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR)); return
mu.hook_add(UC_HOOK_CODE, code)

def call(fn, regs, sp=0x1e00000, stop=STOP, lr=STOP, count=3_000_000):
    mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, sp); mu.reg_write(UC_ARM_REG_LR, lr)
    for r, v in zip(REGS, regs): mu.reg_write(r, v & 0xffffffff)
    mu.mem_write(sp - 0x100, b'\xa5' * 0x200); st['stop'] = stop
    try: mu.emu_start(fn, 0xffffffff, count=count)
    except UcError as e: return ('error', str(e), hex(mu.reg_read(UC_ARM_REG_PC)))
    if mu.reg_read(UC_ARM_REG_PC) != stop: return ('no stop', hex(mu.reg_read(UC_ARM_REG_PC)))
    return ('ok', [mu.reg_read(r) for r in REGS])
word = lambda a: struct.unpack('<I', bytes(mu.mem_read(a, 4)))[0]

# ---- boot: stage B on the official blob1, module 0x41 hook, HOOK_B2 with the flashed blob1 (curve 38), tuning hook
st['phase'] = 'loader'
mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, 0x3f00)
mu.reg_write(UC_ARM_REG_R0, 0x8554c4); mu.reg_write(UC_ARM_REG_R3, 0x40020)
try: mu.emu_start(0x405c, 0xffffffff, count=60_000_000)
except UcError as e: print('loader run error', e, hex(mu.reg_read(UC_ARM_REG_PC)))
check('boot: loader side reaches blob1 entry', st.get('at_blob1'))
L = bytes(mu.mem_read(0, 0x10000)); b1p = bytes(mu.mem_read(0x774000, len(b1)))
st['phase'] = 'mod'
mu.mem_write(m41b, m41)
r = call(CARD.SITE_INIT, [0, 0, 0, m41i, 0, 0], stop=m41i, lr=0xdead0000)
check('boot: module 0x41 hook ran', r[0] == 'ok')
# the flashed v2 has curve 38 in its curve table (HOOK_B2's guard for the tone words): copy just that table into the
# stage-B-patched blob1 (overwriting all of blob1 would also undo stage B's call to HOOK_B2)
cnt = W32(fb1, CARD.CURVE_CNT - 0x774000)
mu.mem_write(CARD.CURVE_CNT, fb1[CARD.CURVE_CNT - 0x774000:CARD.CURVE_TAB - 0x774000 + 0x48 * cnt])
mu.mem_write(0xe0ec80, b2)
r = call(CARD.SITE_B2, [0, 0, 0, 0, 0, 0], stop=CARD.START_B2, lr=0xdead0000)
b2p = bytes(mu.mem_read(0xe0ec80, len(b2)))
check('boot: HOOK_B2 ran (curve 38 present) and patched blob2', r[0] == 'ok' and b2p != b2)
st['phase'] = 'db'; st['db'] = v2
r = call(0x857e44, [0]); dbimg = bytes(mu.mem_read(H.DB_RAM, K.DB_LEN))
check('boot: tuning hook ran on the flashed tuning area', r[0] == 'ok')
st['phase'] = 'tests'

# ---- 1 names
drawn = [s for s in SIMS_ON if not s.name_id]
bad = []
for s in drawn:
    mu.reg_write(UC_ARM_REG_R4, s.row)
    r = call(M.ROW_CAP, [0, 0, 0, 0, s.row, 0], stop=0x147c75c)
    token = mu.reg_read(UC_ARM_REG_R4)
    mu.mem_write(0x130000 + M.STYLE_ID * 10, struct.pack('<I', 64))
    draw = word(0x147c798)                                             # the patched `bl` → DRAW
    off = draw & 0xffffff; off -= (off & 0x800000) << 1; DRAW = 0x147c798 + 8 + 4 * off
    r2 = call(DRAW, [0xffffffec, 3 + drawn.index(s), token], stop=0x1488808)
    glyphs = struct.unpack(f'<{len(s.name) + 1}H', bytes(mu.mem_read(0x12b99be, 2 * (len(s.name) + 1))))
    if r[0] != 'ok' or r2[0] != 'ok' or bytes(g - 0xe100 for g in glyphs[:-1]) != s.name.encode() or glyphs[-1]:
        bad.append((s.key, r[0], r2[0], hex(token), glyphs[:6]))
check(f'names: rows {[s.row for s in drawn]} draw {[s.name for s in drawn]} through the stock lookup + DRAW', not bad, str(bad))

# ---- 2 recipes
SOURCE, COMMAND, FRAME, PACKET = 0x9cb2fc, 0x1db0000, 0x1d00000, 0x120220c
recipes = [s for s in SIMS_ON if s.is_recipe]
def baseline(group):
    b = bytearray(0x46c)
    for off, v in ((0xd0, group), (0x130, 8), (0x110, 2), (0x3c4, 1), (0x3c8, 4), (0x218, 3), (0x12c, 2), (0xdc, -6),
                   (0xe0, 5), (0xe4, 6), (0xe8, -5), (0xec, 4), (0xf0, -3), (0x230, 0x1de8000), (0x41c, 0x9876)):
        b[off:off + 4] = struct.pack('<I', v & 0xffffffff)
    return bytes(b)
def select(stored):
    bank = call(0x792fe4, [])[1][0]
    call(0x793814, [0x3d, stored, 0, bank])
    return call(0x793048, [0x3d, 0])[1][0]
def render(mode, group, tail_patched=True):
    mu.mem_write(SOURCE, baseline(group)); call(0x77ddd8, [mode])
    src = bytes(mu.mem_read(SOURCE, 0x46c))
    mu.mem_write(COMMAND, struct.pack('<2I', SOURCE, 0))
    r = call(0xf79410, [COMMAND], stop=0xf7944c)
    packet = bytes(mu.mem_read(PACKET, 0x46c))
    compact = []
    for patched in (True, False):                                      # exporter with / without the card's tail
        mu.mem_write(R.TAIL_SITE, struct.pack('<I', W32(b1p, R.TAIL_SITE - 0x774000) if patched else R.TAIL_OLD))
        mu.mem_write(FRAME, b'\xed' * 0x218); call(0x9b7254, [FRAME, SOURCE, 0])
        compact.append(bytes(mu.mem_read(FRAME, 0x218)))
    mu.mem_write(R.TAIL_SITE, struct.pack('<I', W32(b1p, R.TAIL_SITE - 0x774000)))
    return r[0], src, packet, compact
def expect(base, recipe, off):
    b = bytearray(base)
    if recipe:
        for key in ('wb', 'red', 'blue', 'color', 'hi', 'lo', 'sharp'):
            for o in (off[key] if isinstance(off[key], tuple) else (off[key],)):
                b[o:o + 4] = struct.pack('<I', recipe[key] & 0xffffffff)
    return bytes(b)
stock_rows = [(0, 0), (2, 3), (1, 1), (3, 8), (4, 9), (5, 10), (6, 7), (11, 11), (12, 12), (7, 5)]   # (stored, MODE_FSIM)
cases = [(s.stored, s.mode_fsim, s.recipe, s.key) for s in SIMS_ON] + [(st_, md, None, f'stock {st_}') for st_, md in stock_rows]
cases += [(s.stored, 0, None, f'{s.key} stored, MODE_FSIM 0 (guard)') for s in recipes]
bad = []
for stored, mode, recipe, label in cases:
    if select(stored) != stored: bad.append((label, 'select')); continue
    for group in (0, 8, 9):
        rc, src, packet, (comp, comp_stock) = render(mode, group)
        if rc != 'ok': bad.append((label, group, 'run')); continue
        if packet != expect(src, recipe, R.CAPTURE_OFF): bad.append((label, group, 'message',
            [hex(i) for i in range(0x46c) if packet[i] != expect(src, recipe, R.CAPTURE_OFF)[i]][:8]))
        if comp != expect(comp_stock, recipe, R.COMPACT_OFF): bad.append((label, group, 'compact',
            [hex(i) for i in range(0x218) if comp[i] != expect(comp_stock, recipe, R.COMPACT_OFF)[i]][:8]))
check(f'recipes: shooting message + compact record carry exactly {[s.name for s in recipes]}\'s settings; '
      f'{len(cases) - len(recipes) * 2} other selections unchanged; 3 WB modes', not bad, str(bad[:3]))

# ---- 3 looks with extras
extras = [s for s in SIMS_ON if not s.is_recipe and not s.own_data]   # borrowed looks
st['phase'] = 'pipe'
REC = 0x1e10000
def recctl(cm, alt=0, mode=0, flag180=0, e4=0, f154=0, b8=0, f118=3, f124=0):
    mu.mem_write(REC, bytes(0x300))
    for off, v in ((0xc4, cm), (0xc8, alt), (0x104, mode), (0x180, flag180), (0xe4, e4), (0x154, f154), (0xb8, b8),
                   (0x118, f118), (0x124, f124), (0xa8, 0), (0xd0, 0), (0xfc, 0), (0x164, 0)):
        mu.mem_write(REC + off, struct.pack('<I', v))
def run(blob2, dbimage, fn, regs, out_len=0, stop=STOP):
    mu.mem_write(0xe0ec80, blob2); st['dbimg'] = dbimage; st['ids'] = []; st['curves'] = None
    mu.mem_write(0x1e20000, bytes(0x100))
    r = call(fn, regs, stop=stop)
    assert r[0] == 'ok', (hex(fn), r)
    return bytes(mu.mem_read(0x1e20000, out_len)) if out_len else st['curves']
m3x3 = lambda bl, db, cm, alt, mode: (recctl(cm, alt, mode), run(bl, db, 0xf32fcc, [0x1e20000, REC], 18))[1]
m2x2 = lambda bl, db, cm, alt: run(bl, db, 0xf2d404, [0x1e20000, 0, cm, alt, 0], 16)
def m2x2b(bl, db, cm, alt, p6, p7):
    mu.mem_write(0x1e00000, struct.pack('<2I', p6, p7)); return run(bl, db, 0xf30b10, [0x1e20000, 0, cm, alt, 0, p6], 16)
gain = lambda bl, db, cm: run(bl, db, 0xf2c8fc, [0x1e20000, 3, 0, cm], 4)
tone = lambda bl, db, fn, cm, **kw: (recctl(cm, **kw), run(bl, db, fn, [REC, 0x1e20080, 0x1e200c0, 0x1e20100], stop=0xf28ba0)[:2])[1]
TONES = ((0xf321f0, {}), (0xf321f0, {'flag180': 1}), (0xf321f0, {'mode': 4}), (0xf321f0, {'e4': 7, 'mode': 4}),
         (0xf3232c, {}), (0xf3232c, {'f154': 2}), (0xf3232c, {'f154': 2, 'b8': 4}), (0xf3232c, {'mode': 5, 'f124': 3, 'f118': 7}),
         (0xf3232c, {'mode': 5}))
for s in extras:
    lk, cm = s.look, s.colour_mode
    ref3 = {2: 5}[lk['idx3']]; ref2 = {0: 0}[lk['idx2']]; reft = {3: 6}[lk['family']]   # ASTIA / PROVIA / PRO Neg. Std
    st['phase'] = 'tests'; mu.mem_write(0xe0ec80, b2p)
    mu.mem_write(0x1e30000, bytes(4)); r = call(0xf38780, [0x1e30000, s.mode_fsim])
    check(f'{s.key}: real FUN_00f38780: MODE_FSIM {s.mode_fsim} → colour mode {cm}', r[0] == 'ok' and word(0x1e30000) == cm, hex(word(0x1e30000)))
    st['phase'] = 'pipe'
    bad = [(m_, a) for m_ in (0, 4, 5) for a in (0, 1) if m3x3(b2p, dbimg, cm, a, m_) != m3x3(b2p, dbimg, ref3, a, m_)]
    check(f'{s.key}: 3x3 (sRGB/alt × 3 modes) = colour mode {ref3}', not bad, str(bad))
    bad = [a for a in (0, 1) if m2x2(b2p, dbimg, cm, a) != m2x2(b2p, dbimg, ref2, a)]
    bad += [(a, p6, p7) for a in (0, 1) for p6, p7 in ((0, 0), (1, 0), (0, 4), (0, 8))
            if m2x2b(b2p, dbimg, cm, a, p6, p7) != m2x2b(b2p, dbimg, ref2, a, p6, p7)]
    check(f'{s.key}: 2x2 (both consumers, 4 mode rows) = colour mode {ref2}', not bad, str(bad))
    check(f'{s.key}: chroma gain = colour mode 0', gain(b2p, dbimg, cm) == gain(b2p, dbimg, 0))
    bad = [(hex(fn), kw) for fn, kw in TONES if tone(b2p, dbimg, fn, cm, **kw) != tone(b2p, dbimg, fn, reft, **kw)]
    check(f'{s.key}: tone (9 variants) = colour mode {reft}', not bad, str(bad[:3]))
if extras:
    # the stock colour modes render as before the card: with Classic Chrome's look as on stock firmware (it puts PRO
    # Neg. Hi back to stock; SEPIA's tone runs through PROVIA's family, same curves), without it as the flashed
    # firmware's tuning area says (the v2 build keeps Classic Chrome data in PRO Neg. Hi)
    ref_db = stock_db if any(s.own_data for s in SIMS_ON) else v2
    bad = []
    for cmx in (0, 2, 3, 4, 5, 6, 7):
        for a in (0, 1):
            for m_ in (0, 4, 5):
                if m3x3(b2p, dbimg, cmx, a, m_) != m3x3(b2, ref_db, cmx, a, m_): bad.append(('3x3', cmx, a, m_))
            if m2x2(b2p, dbimg, cmx, a) != m2x2(b2, ref_db, cmx, a): bad.append(('2x2', cmx, a))
        for fn, kw in TONES:
            if tone(b2p, dbimg, fn, cmx, **kw) != tone(b2, ref_db, fn, cmx, **kw): bad.append(('tone', cmx, hex(fn), kw))
        if gain(b2p, dbimg, cmx) != gain(b2, ref_db, cmx): bad.append(('gain', cmx))
    check('stock colour modes 0, 2-7 render as before the card (3x3 × 3 modes, 2x2, chroma gain, tone × 9)', not bad, str(bad[:3]))
    cc = [tone(b2p, dbimg, fn, 1, **kw) for fn, kw in TONES]
    if any(s.own_data for s in SIMS_ON): check('Classic Chrome (colour mode 1): tone still curve 38 (16 in the fixed-curve mode)',
          all(c == [38, 38] or ('e4' in kw and c == [16, 16]) for c, (fn, kw) in zip(cc, TONES)), str(cc))

# ---- 4 peaking
if PEAKING:
    check('peaking: tuning hook wrote ' + ', '.join(f'{i:#x}={n}' for i, (o, n) in PK.BYTES.items()),
          all(dbimg[i] == n for i, (o, n) in PK.BYTES.items()), str([dbimg[i] for i in PK.BYTES]))
print('\nRESULT:', 'ALL OK' if ok else 'FAILED'); sys.exit(0 if ok else 1)
