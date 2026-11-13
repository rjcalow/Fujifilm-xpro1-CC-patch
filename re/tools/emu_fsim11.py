# Emulator test for the 11th film-simulation entry on the SD-boot card (fsim11.py; build_sdchain.py --crumbs --cc
# --fsim11). Runs the real firmware code around every hook.
# usage: emu_fsim11.py <official FPUPDATE.DAT> <ffboot.bin> <re/work dir> <flash firmware FPUPDATE.DAT (v2 build)>
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'public'))
import crumbs as C, cchook as H, fsim11 as F, uitext

dat, boot, W, flash = sys.argv[1:5]
img = bytes(x ^ 0xff for x in open(dat, 'rb').read())
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
# locate the fsim11 stage table in the loader filler (markers are stored as {addr, old, new})
tab = L.find(struct.pack('<3I', F.ROW10, F.END, 13)); marks = []
while W32(L, tab): marks.append(struct.unpack('<3I', L[tab:tab + 12])); tab += 12
want = sorted([0x857a98, H.SITE_LANG] + [x for x, _ in H.DB_SITES] + [a for a, _, _ in marks])
check('stage B changed exactly: Ver3.89 marker + cchook sites + fsim11 table', diff == want, str([hex(x) for x in diff]))
check('fsim11 table applied (every entry holds its new word)', all(W32(now, a - 0x774000) == new for a, _, new in marks)
      and len(marks) == 6)
LIST = marks[2][2]
lst = [W32(L, LIST + 4 * i) for i in range(24)]
check('new menu list = stock rows + row 10', lst == sum(([r, 0] for r in F.STOCK_ROWS + [10, F.END]), []))

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
icon = {k: W32(L, (F.MOD41[2][2] if False else 0) + 0) for k in ()}
want = {a: new for a, _, new in F.MOD41 if not isinstance(new, str)}
check('module hook: exactly the eight module words changed', ch == sorted(a for a, _, _ in F.MOD41), str([hex(x) for x in ch]))
check('module hook: name entry 819, row limit cmp r4,#10, fsim 6 → row 10 in both row maps', all(W32(got, a - F.M41_BASE) == v for a, v in want.items()))
iA, iB = W32(got, 0x14299fc - F.M41_BASE), W32(got, 0x1429a00 - F.M41_BASE)
tA = [W32(L, iA + 4 * i) for i in range(11)]; tB = [W32(L, iB + 4 * i) for i in range(11)]
check('module hook: both FILM SIMULATION records → 11-entry icon tables (stock + 1215)',
      W32(got, 0x142bd98 - F.M41_BASE) == iA and W32(got, 0x142bd9c - F.M41_BASE) == iB
      and tA == [W32(m41, 0x142aa4c - F.M41_BASE + 4 * i) for i in range(10)] + [1215]
      and tB == [W32(m41, 0x1427320 - F.M41_BASE + 4 * i) for i in range(10)] + [1215])
check('module hook: fsim → row maps give row 10 for fsim 6, stock rows otherwise',
      all(list(got[t - F.M41_BASE:t - F.M41_BASE + 13]) == [0, 2, 0, 1, 5, 9, 10, 5, 7, 6, 8, 4, 3] for t in (0x1474e7c, 0x1474e3c)))
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
print('\nRESULT:', 'ALL OK' if ok else 'FAILED'); sys.exit(0 if ok else 1)
