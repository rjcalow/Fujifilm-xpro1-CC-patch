# Emulator test for the Classic Chrome SD-boot hooks (cchook.py; card built with build_sdchain.py --crumbs --cc).
# usage: emu_cchook.py <official FPUPDATE.DAT> <ffboot.bin> <re/work dir> <flash firmware FPUPDATE.DAT (v2 build)>
#   1 loader side: from the loader's final jump to blob1's entry → stage B has redirected the two blob1 calls.
#   2 language hook: real blob1 0x86334c(k) for all 35 languages, block read simulated at 0x8632a4 → name shown is
#     CLASSIC CHROME, exactly three descriptor words + the tail differ, uiname.unpatch gives the original block,
#     return value kept. Also: no table entry matches in a foreign language block.
#   3 tuning hook: real blob1 0x857e44, read simulated at 0x863940 with the flash firmware's area → only the four
#     2x2 values change (= build_cc3 values); official 3.82 values or already-v3 values → nothing changes.
import os, struct, sys, zlib
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crumbs as C, cchook as H, uiname
from build_cc3 import PARAMS3

dat, boot, W, flash = sys.argv[1:5]
img = bytes(x ^ 0xff for x in open(dat, 'rb').read())
fimg = bytes(x ^ 0xff for x in open(flash, 'rb').read())
ffboot = open(boot, 'rb').read()
m = ffboot.find(struct.pack('<I', 0x4e494843)); _, po, pl, ol, crc = struct.unpack('<5I', ffboot[m - 0x14:m])
loader = zlib.decompress(ffboot[po:po + pl], -15)
b1 = open(os.path.join(W, 'blob1.bin'), 'rb').read()
ok = True
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(f'{"OK  " if cond else "FAIL"} {name} {detail}')
W32 = lambda b, o: struct.unpack('<I', b[o:o + 4])[0]
STOP = 0x1f00000

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
    if a == STOP: uc.emu_stop(); return
    if a == H.FN_LANG and st.get('phase') == 'lang':
        r = [uc.reg_read(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        st['args'] = r; uc.mem_write(r[2], st['blk'])
        uc.reg_write(UC_ARM_REG_R0, st['ret']); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR)); return
    if a in (0x858394, H.FN_DB) and st.get('phase') == 'db':
        r = [uc.reg_read(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1)]
        st['args'] = r if a == H.FN_DB else [H.DB_RAM, 0xb3700]; st['hit'] = a; uc.mem_write(H.DB_RAM, st['db'])
        uc.reg_write(UC_ARM_REG_R0, st['ret']); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR)); return
mu.hook_add(UC_HOOK_CODE, code)

# ---- 1
st['phase'] = 'loader'
mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, 0x3f00)
mu.reg_write(UC_ARM_REG_R0, 0x8554c4); mu.reg_write(UC_ARM_REG_R3, 0x40020)
try: mu.emu_start(0x405c, 0xffffffff, count=60_000_000)
except UcError as e: print('loader run error', e, hex(mu.reg_read(UC_ARM_REG_PC)))
check('loader side reaches blob1 entry', st.get('at_blob1'))
now = bytes(mu.mem_read(0x774000, len(b1)))
diff = sorted({(i & ~3) + 0x774000 for i in range(len(b1)) if now[i] != b1[i]})
info = None
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM
ks = Ks(KS_ARCH_ARM, KS_MODE_ARM); bl = lambda frm, to: struct.unpack('<I', bytes(ks.asm(f'bl {to:#x}', frm)[0]))[0]
check('stage B changed exactly: marker + three call sites', diff == sorted([0x857a98, H.SITE_LANG] + [x for x, _ in H.DB_SITES]), str([hex(x) for x in diff]))
for k, (site, _) in enumerate(H.DB_SITES):
    check(f'tuning call {site:#x} → HOOK_DB{k}', W32(now, site - 0x774000) == bl(site, H.AREA + 0x80 * k))
check('language call → HOOK_LANG', W32(now, H.SITE_LANG - 0x774000) == bl(H.SITE_LANG, H.AREA + 0x100))
check('Ver3.89 marker', W32(now, 0x857a98 - 0x774000) == 0xe3a03039)

def call(fn, r0, sp=0x1e00000):
    mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, sp); mu.reg_write(UC_ARM_REG_LR, STOP)
    mu.reg_write(UC_ARM_REG_R0, r0); mu.mem_write(sp - 0x100, b'\xa5' * 0x200)
    try: mu.emu_start(fn, 0xffffffff, count=2_000_000)
    except UcError as e: return ('error', str(e), hex(mu.reg_read(UC_ARM_REG_PC)))
    if mu.reg_read(UC_ARM_REG_PC) != STOP: return ('no return', hex(mu.reg_read(UC_ARM_REG_PC)))
    above = bytes(mu.mem_read(sp, 0x100)) == b'\xa5' * 0x100          # nothing written above the entry sp
    return ('ok', mu.reg_read(UC_ARM_REG_R0), mu.reg_read(UC_ARM_REG_SP) == sp and above)

# ---- 2
st['phase'] = 'lang'; bad = []
table = H.lang_table(img)
for k in range(uiname.NBLOCKS):
    a = uiname.FILE0 + k * uiname.BLOCK; org = fimg[a:a + uiname.BLOCK]
    if org != img[a:a + uiname.BLOCK]: bad.append((k, 'flash firmware language block differs from the official one')); continue
    st['blk'] = org; st['ret'] = 0x55 if k == 1 else 0
    r = call(0x86334c, k)
    got = bytearray(mu.mem_read(uiname.RAM, uiname.BLOCK))
    if r != ('ok', st['ret'], True): bad.append((k, r)); continue
    if st['args'][:3] != [(0x1040000 + k * 0x20000) >> 17, 1, uiname.RAM]: bad.append((k, 'loader args', st['args'])); continue
    ch = sorted({i & ~3 for i in range(uiname.BLOCK) if got[i] != org[i]})
    recs = uiname.find_recs(org)
    if [c for c in ch if c < H.TAIL] != sorted(d for d, _, _ in recs): bad.append((k, 'descriptor set')); continue
    if any(c >= H.TAIL + H.TAIL_LEN for c in ch) or uiname.current(got) != uiname.NEW: bad.append((k, 'tail / name', uiname.current(got))); continue
    for d, ptr, text in recs:                                   # follow each descriptor like the firmware
        s = W32(got, d) - uiname.RAM; e = s
        while got[e:e + 2] != b'\0\0': e += 2
        if got[s:e].decode('utf-16le') != text.replace(uiname.OLD, uiname.NEW): bad.append((k, 'text', d))
    # entries of other languages must not match this block
    foreign = [e for e in table if W32(org, e[0] - uiname.RAM) == e[1] and (e[0] - uiname.RAM) not in [d for d, _, _ in recs]]
    if foreign: bad.append((k, 'foreign match', foreign))
    back = bytearray(got)
    if not uiname.unpatch(back) or bytes(back) != org: bad.append((k, 'unpatch'))
check('language hook: all 35 blocks → CLASSIC CHROME, 3 descriptors, restorable, r0 and stack kept', not bad, str(bad[:3]))
st['blk'] = b'\xff' * uiname.BLOCK; st['ret'] = 0xffffffe2                    # failed read: nothing to match
r = call(0x86334c, 1); got = bytes(mu.mem_read(uiname.RAM, uiname.BLOCK))
check('language hook: failed read → no descriptor written, error code kept',
      r == ('ok', 0xffffffe2, True) and got[:H.TAIL] == b'\xff' * H.TAIL)

# ---- 3: both tuning paths: start-up (the real call at 0x8550d4, running from there to the next call) and reload 0x857e44
st['phase'] = 'db'
DBF, DBLEN = 0xae025c, 0xb3700
ids = {pid + i for pid, _, _ in PARAMS3 for i in range(2)}
def run_db(path, src, ret=0):
    st['db'] = src; st['ret'] = ret; st['hit'] = None
    if path == 'start-up':                                   # execute the patched bl at 0x8550d4, stop right after it
        mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, 0x1e00000); mu.mem_write(0x1e00000 - 0x100, b'\xa5' * 0x200)
        h = mu.hook_add(UC_HOOK_CODE, lambda uc, a, s_, u: uc.emu_stop(), begin=0x8550d8, end=0x8550d8)
        try: mu.emu_start(0x8550d4, 0xffffffff, count=2_000_000); r = ('ok', mu.reg_read(UC_ARM_REG_R0),
              mu.reg_read(UC_ARM_REG_SP) == 0x1e00000 and bytes(mu.mem_read(0x1e00000, 0x100)) == b'\xa5' * 0x100)
        except UcError as e: r = ('error', str(e))
        mu.hook_del(h)
        if mu.reg_read(UC_ARM_REG_PC) != 0x8550d8: r = ('no return', hex(mu.reg_read(UC_ARM_REG_PC)))
    else:
        r = call(0x857e44, 0)
    return r, bytes(mu.mem_read(H.DB_RAM, DBLEN))
v2 = fimg[DBF:DBF + DBLEN]; stock = img[DBF:DBF + DBLEN]
for path, fn in (('start-up', 0x858394), ('reload', H.FN_DB)):
    r, got = run_db(path, v2)
    ch = {i for i in range(DBLEN) if got[i] != v2[i]}
    want = all(got[pid:pid + 2] == bytes.fromhex(new) for pid, _, new in PARAMS3)
    check(f'{path}: original loader {fn:#x} called, v2 values → v3, only the four 2x2 values change',
          r == ('ok', 0, True) and st['hit'] == fn and ch <= ids and want, f'{len(ch)} bytes {r}')
    r, got2 = run_db(path, got)
    check(f'{path}: already v3 → unchanged', r[0] == 'ok' and got2 == got)
    r, got3 = run_db(path, stock, 7)
    check(f'{path}: official 3.82 values → unchanged, return value kept', r == ('ok', 7, True) and got3 == stock)
print('\nRESULT:', 'ALL OK' if ok else 'FAILED'); sys.exit(0 if ok else 1)
