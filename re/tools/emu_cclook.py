# Emulator test for Classic Chrome's own look data on the SD-boot card (cclook.py; build_sdchain.py --crumbs --cc
# --fsim11 --cclook). Runs the real firmware code: the hooks on the card, then the pipeline's selection functions.
# usage: emu_cclook.py <official FPUPDATE.DAT> <ffboot.bin> <re/work dir> <flashed firmware FPUPDATE.DAT (v2 build)>
#   1 tuning hook (real blob1 0x857e44, read simulated with the flashed area): result = flashed area + the planned
#     byte changes, exactly; official 3.82 area -> only the entries whose old value is stock apply (new presets,
#     selectors, family-5 curves), PRO Neg. Hi untouched.
#   2 HOOK_B2 (the patched `bl` at 0x972520): with stock blob1 (no curve 38) only the matrix patches apply; with
#     curve 38 present all 20 words apply; registers kept; blob2 unchanged elsewhere.
#   3 pipeline (patched blob2 + patched tuning image, real FUN_00f32fcc / FUN_00f2d404 / FUN_00f30b10 /
#     FUN_00f2c8fc / FUN_00f321f0 / FUN_00f3232c):
#       colour mode 1 = what colour mode 7 produced on the flashed v2 (matrices) / curve 38 (tone), in every variant
#       colour mode 7 = what it produces on stock firmware; colour mode 0 (PROVIA) and 3 (SEPIA) unchanged.
import os, struct, sys, zlib
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'public'))
import crumbs as C, cchook as H, fsim11 as F, cclook as K
import xpro1_cc_patch as P

dat, boot, W, flash = sys.argv[1:5]
img = bytes(x ^ 0xff for x in open(dat, 'rb').read())
fimg = bytes(x ^ 0xff for x in open(flash, 'rb').read())
ffboot = open(boot, 'rb').read()
m = ffboot.find(struct.pack('<I', 0x4e494843)); _, po, pl, ol, crc = struct.unpack('<5I', ffboot[m - 0x14:m])
loader = zlib.decompress(ffboot[po:po + pl], -15)
b1 = open(os.path.join(W, 'blob1.bin'), 'rb').read(); b2 = open(os.path.join(W, 'blob2.bin'), 'rb').read()
u1, p1 = struct.unpack('<II', fimg[0x10025c:0x100264]); fb1 = P.lz_decode(fimg, 0x10025c + 20, 0x10025c + p1, u1)
stock = img[K.DB_FILE:K.DB_FILE + K.DB_LEN]; v2 = fimg[K.DB_FILE:K.DB_FILE + K.DB_LEN]
plan = K.db_bytes(stock, v2)
want = bytearray(v2)
for i, (o, n) in plan.items(): want[i] = n
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
    if a == 0xf28ba0 and st.get('phase') == 'pipe':                      # tone blend: capture the curve numbers
        st['curves'] = [uc.reg_read(r) for r in REGS[:3]]; uc.emu_stop(); return
    if a in (STOP, st.get('stop')): uc.emu_stop(); return
    if a == H.FN_DB and st.get('phase') == 'db':
        uc.mem_write(H.DB_RAM, st['db']); uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR)); return
    if a == 0x857be0 and st.get('phase') == 'pipe':                      # DB getter: byte from the test image
        i = uc.reg_read(UC_ARM_REG_R0); st['ids'].append(i)
        uc.reg_write(UC_ARM_REG_R0, st['dbimg'][i]); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR)); return
mu.hook_add(UC_HOOK_CODE, code)

# ---- stage B
st['phase'] = 'loader'
mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, 0x3f00)
mu.reg_write(UC_ARM_REG_R0, 0x8554c4); mu.reg_write(UC_ARM_REG_R3, 0x40020)
try: mu.emu_start(0x405c, 0xffffffff, count=60_000_000)
except UcError as e: print('loader run error', e, hex(mu.reg_read(UC_ARM_REG_PC)))
check('loader side reaches blob1 entry', st.get('at_blob1'))
L = bytes(mu.mem_read(0, 0x10000))

def call(fn, regs, sp=0x1e00000, stop=STOP, lr=STOP, count=3_000_000):
    mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, sp); mu.reg_write(UC_ARM_REG_LR, lr)
    for r, v in zip(REGS, regs): mu.reg_write(r, v)
    mu.mem_write(sp - 0x100, b'\xa5' * 0x200); st['stop'] = stop
    try: mu.emu_start(fn, 0xffffffff, count=count)
    except UcError as e: return ('error', str(e), hex(mu.reg_read(UC_ARM_REG_PC)))
    if mu.reg_read(UC_ARM_REG_PC) != stop: return ('no stop', hex(mu.reg_read(UC_ARM_REG_PC)))
    above = bytes(mu.mem_read(sp, 0x100)) == b'\xa5' * 0x100
    return ('ok', [mu.reg_read(r) for r in REGS], mu.reg_read(UC_ARM_REG_SP) == sp and above, mu.reg_read(UC_ARM_REG_LR))

# ---- 1 tuning hook
st['phase'] = 'db'
st['db'] = v2; r = call(0x857e44, [0]); got = bytes(mu.mem_read(H.DB_RAM, K.DB_LEN))
diff = [i for i in range(K.DB_LEN) if got[i] != want[i]]
check('tuning hook: flashed area -> planned image, exactly', r[0] == 'ok' and not diff, f'{len(diff)} bytes differ {[hex(i) for i in diff[:6]]}')
negs = [i for i in range(K.DB_LEN) if stock[i] != v2[i]]
check('  PRO Neg. Hi IDs back to stock', all(got[i] == stock[i] for i in negs), f'{len(negs)} bytes')
st['db'] = stock; r = call(0x857e44, [0]); got = bytes(mu.mem_read(H.DB_RAM, K.DB_LEN))
exp = bytearray(stock)
for i, o, n in K.db_params(plan, v2):                               # u16 entries: both bytes must match
    if stock[i:i + 2].hex() == o: exp[i:i + 2] = bytes.fromhex(n)
diff = [i for i in range(K.DB_LEN) if got[i] != exp[i]]
check('tuning hook: official 3.82 area -> only stock-matching entries apply', r[0] == 'ok' and not diff and all(got[i] == stock[i] for i in negs), str(len(diff)))
dbimg = bytes(want)

# ---- 2 HOOK_B2
mu.mem_write(F.B2_BASE, b2)
regs = [0x77, 0x88, 0x99, 3, 4, 5]
r = call(F.SITE_B2, regs, stop=F.START_B2, lr=0xdead0000)
got = bytes(mu.mem_read(F.B2_BASE, len(b2)))
lay = K.layout(0)                                                  # addresses from the card's B2TAB instead
tab = L.find(struct.pack('<3I', K.CODE[0][0], K.CODE[0][1], 0) [:8])
ent = []
while True:
    a, o, n, fl = struct.unpack('<4I', L[tab:tab + 16])
    if a == 0: break
    ent.append((a, o, n, fl)); tab += 16
check('card holds the 20-entry blob2 table (6 tone entries flagged)', len(ent) == 20 and sum(fl for *_, fl in ent) == 6)
ch = sorted({(i & ~3) + F.B2_BASE for i in range(len(b2)) if got[i] != b2[i]})
check('HOOK_B2 without curve 38: the 14 matrix patches only, registers kept',
      r[0] == 'ok' and r[1] == regs and r[2] and ch == sorted(a for a, o, n, fl in ent if not fl)
      and all(W32(got, a - F.B2_BASE) == n for a, o, n, fl in ent if not fl), str(r[:1] + r[3:]))
mu.mem_write(F.B2_BASE, b2); mu.mem_write(0x774000, fb1)        # flashed blob1: curve table holds #38
ids = [W32(fb1, 0x80b700 - 0x774000 + 0x48 * i) for i in range(W32(fb1, 0x80b6f8 - 0x774000))]
check('flashed blob1 curve table has curve 38', 38 in ids)
r = call(F.SITE_B2, regs, stop=F.START_B2, lr=0xdead0000)
got = bytes(mu.mem_read(F.B2_BASE, len(b2)))
ch = sorted({(i & ~3) + F.B2_BASE for i in range(len(b2)) if got[i] != b2[i]})
check('HOOK_B2 with curve 38: all 20 words applied, nothing else',
      r[0] == 'ok' and ch == sorted(a for a, *_ in ent) and all(W32(got, a - F.B2_BASE) == n for a, o, n, fl in ent))
r = call(F.SITE_B2, regs, stop=F.START_B2, lr=0xdead0000)
check('HOOK_B2 again: idempotent', bytes(mu.mem_read(F.B2_BASE, len(b2))) == got)
patched = got

# ---- 3 pipeline
st['phase'] = 'pipe'
REC = 0x1e10000
def recctl(cm, alt=0, mode=0, flag180=0, e4=0, f154=0, b8=0, f118=3, f124=0):
    mu.mem_write(REC, bytes(0x300))
    for off, v in ((0xc4, cm), (0xc8, alt), (0x104, mode), (0x180, flag180), (0xe4, e4), (0x154, f154), (0xb8, b8),
                   (0x118, f118), (0x124, f124), (0xa8, 0), (0xd0, 0), (0xfc, 0), (0x164, 0)):
        mu.mem_write(REC + off, struct.pack('<I', v))
def run(blob2, dbimage, fn, regs, out_len=0, stop=STOP):
    mu.mem_write(F.B2_BASE, blob2); st['dbimg'] = dbimage; st['ids'] = []; st['curves'] = None
    mu.mem_write(0x1e20000, bytes(0x100))
    r = call(fn, regs, stop=stop)
    return r, bytes(mu.mem_read(0x1e20000, out_len)) if out_len else st['curves'], list(st['ids'])
bad = []
def m3x3(blob2, dbimage, cm, alt, mode):
    recctl(cm, alt, mode); r, out, ids = run(blob2, dbimage, 0xf32fcc, [0x1e20000, REC], 18)
    assert r[0] == 'ok', (r, cm, alt, mode); return out, ids
def m2x2(blob2, dbimage, cm, alt):
    r, out, ids = run(blob2, dbimage, 0xf2d404, [0x1e20000, 0, cm, alt, 0], 16); assert r[0] == 'ok', r; return out, ids
def m2x2b(blob2, dbimage, cm, alt, p6, p7):
    mu.mem_write(0x1e00000 - 0x100, b'\xa5' * 0x200)
    mu.mem_write(0x1e00000, struct.pack('<2I', p6, p7))               # stack args 6, 7
    r, out, ids = run(blob2, dbimage, 0xf30b10, [0x1e20000, 0, cm, alt, 0, p6], 16); assert r[0] == 'ok', r; return out, ids
def gain(blob2, dbimage, cm):
    r, out, ids = run(blob2, dbimage, 0xf2c8fc, [0x1e20000, 3, 0, cm], 4); assert r[0] == 'ok', r; return out, ids
def tone(blob2, dbimage, fn, cm, **kw):
    recctl(cm, **kw); r, cur, ids = run(blob2, dbimage, fn, [REC, 0x1e20080, 0x1e200c0, 0x1e20100], stop=0xf28ba0)
    assert r[0] == 'ok' and cur is not None, (r, cm, kw); return cur[:2], ids
for mode in (0, 4, 5):
    for alt in (0, 1):
        new1, ids1 = m3x3(patched, dbimg, 1, alt, mode); old7, _ = m3x3(b2, v2, 7, alt, mode)
        new7, _ = m3x3(patched, dbimg, 7, alt, mode); st7, _ = m3x3(b2, stock, 7, alt, mode)
        new0, _ = m3x3(patched, dbimg, 0, alt, mode); st0, _ = m3x3(b2, stock, 0, alt, mode)
        if new1 != old7: bad.append(('3x3 cm1 != v2 cm7', mode, alt, ids1[:3]))
        if new7 != st7: bad.append(('3x3 cm7 != stock', mode, alt))
        if new0 != st0: bad.append(('3x3 cm0 changed', mode, alt))
        if new1 == new0: bad.append(('3x3 cm1 == PROVIA', mode, alt))
check('3x3: cm 1 = v2 PRO Neg. Hi (CC), cm 7 = stock PRO Neg. Hi, PROVIA unchanged, sRGB/alt x 3 modes', not bad, str(bad[:3]))
bad = []
for alt in (0, 1):
    n1, ids1 = m2x2(patched, dbimg, 1, alt); n7, _ = m2x2(patched, dbimg, 7, alt); s7, _ = m2x2(b2, stock, 7, alt)
    n0, _ = m2x2(patched, dbimg, 0, alt); s0, _ = m2x2(b2, stock, 0, alt)
    if n7 != s7: bad.append(('2x2 cm7 != stock', alt))
    if n0 != s0: bad.append(('2x2 cm0 changed', alt))
    if n1 == n0: bad.append(('2x2 cm1 == PROVIA', alt))
    if not any(i in (0xe4a0, K.SEL_ALT2) for i in ids1) or not any(0xe401 <= i < 0xe409 for i in ids1): bad.append(('2x2 cm1 ids', alt, ids1[:6]))
    for p6, p7 in ((0, 0), (1, 0), (0, 4), (0, 8)):
        n1, ids1 = m2x2b(patched, dbimg, 1, alt, p6, p7); n7, _ = m2x2b(patched, dbimg, 7, alt, p6, p7); s7, _ = m2x2b(b2, stock, 7, alt, p6, p7)
        n0, _ = m2x2b(patched, dbimg, 0, alt, p6, p7); s0, _ = m2x2b(b2, stock, 0, alt, p6, p7)
        if n7 != s7 or n0 != s0 or n1 == n0 or not any(0xe401 <= i < 0xe409 for i in ids1): bad.append(('2x2b', alt, p6, p7, ids1[:4]))
v3 = struct.unpack('<4H', K.V3_2X2)
check('2x2 (both consumers): cm 1 reads preset 12, cm 7 = stock, PROVIA unchanged; sRGB/alt, 4 mode rows', not bad, str(bad[:3]))
g1, i1 = gain(patched, dbimg, 1); g7, i7 = gain(patched, dbimg, 7); s7, _ = gain(b2, stock, 7); s0, _ = gain(b2, stock, 0)
check('chroma gain (column 3): cm 1 = PROVIA preset 1, cm 7 = stock preset 2', g1 == s0 and g7 == s7 and g7 != g1
      and i1[0] == 0xe4e8 and i7[0] == 0xe4ec, str((g1.hex(), g7.hex(), s0.hex(), s7.hex())))
bad = []
for fn, kw in ((0xf321f0, {}), (0xf321f0, {'flag180': 1}), (0xf321f0, {'mode': 4}), (0xf321f0, {'e4': 7, 'mode': 4}),
               (0xf3232c, {}), (0xf3232c, {'f154': 2}), (0xf3232c, {'f154': 2, 'b8': 4}), (0xf3232c, {'mode': 5, 'f124': 3, 'f118': 7}),
               (0xf3232c, {'mode': 5})):
    c1, _ = tone(patched, dbimg, fn, 1, **kw); c0, _ = tone(patched, dbimg, fn, 0, **kw); s0, _ = tone(b2, stock, fn, 0, **kw)
    c3, _ = tone(patched, dbimg, fn, 3, **kw); s3, _ = tone(b2, stock, fn, 3, **kw)
    c7, _ = tone(patched, dbimg, fn, 7, **kw); s7, _ = tone(b2, stock, fn, 7, **kw); o7, _ = tone(b2, v2, fn, 7, **kw)
    c2, _ = tone(patched, dbimg, fn, 2, **kw); s2, _ = tone(b2, stock, fn, 2, **kw)
    if c1 != o7 or (c1 != [38, 38] and 'e4' not in kw): bad.append(('cm1', hex(fn), kw, c1, o7))
    if c0 != s0 or c3 != s3 or c7 != s7 or c2 != s2: bad.append(('others', hex(fn), kw, c0, s0, c3, s3, c7, s7))
check('tone: cm 1 = v2 PRO Neg. Hi (curve 38; 16 in the fixed-curve mode), SEPIA/MONO/PROVIA/PRO Neg. Hi = stock, 9 variants', not bad, str(bad[:2]))
print('\nRESULT:', 'ALL OK' if ok else 'FAILED'); sys.exit(0 if ok else 1)
