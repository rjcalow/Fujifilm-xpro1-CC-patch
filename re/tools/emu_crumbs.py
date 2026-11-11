# Emulator test for the breadcrumb SD card (build_sdchain.py --crumbs with the chain_crumbs.bin stub).
# usage: emu_crumbs.py <FPUPDATE.DAT> <ffboot.bin> <re/work dir>
#   1 stub: run ffboot.bin from 0 → it must inflate the loader, write the header, the boot-ROM snapshot, progress
#     0x01/0x02/0x03 and the drained-abort fields, then jump to 0.
#   2 loader side, clean: memory as the stock loader leaves it, start at its final jump 0x405c → progress 0x10,
#     0x11-0x15, 0x20 → blob1 entry; marker applied; non-fatal vectors restored, fatal ones trapped.
#   3 phase trampolines: 0x21/0x22/0x23 recorded and `bx r4` taken.
#   4 fault: data abort injected inside 0x43fc0 → exception record (type 4, lr, progress 0x14), heartbeat counts.
#   5 same fault with section 0's resume flag [0x4004d7a0] set → chains to section 0's own handler 0x4013c.
import ctypes, os, struct, sys, zlib
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_PROT_ALL
from unicorn.arm_const import *
sys.path.insert(0, os.path.dirname(__file__))
import crumbs as C, lz, uicolor as UI

dat, boot, W = sys.argv[1:4]
img = bytes(x ^ 0xff for x in open(dat, 'rb').read())
ffboot = open(boot, 'rb').read()
m = ffboot.find(struct.pack('<I', 0x4e494843)); _, po, pl, ol, crc = struct.unpack('<5I', ffboot[m - 0x14:m])
loader = zlib.decompress(ffboot[po:po + pl], -15)
b1 = open(os.path.join(W, 'blob1.bin'), 'rb').read()
ok = True
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(f'{"OK  " if cond else "FAIL"} {name} {detail}')


def machine():
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM); mu.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_R5)
    buf = ctypes.create_string_buffer(0x2000000)
    mu.mem_map_ptr(0, 0x2000000, UC_PROT_ALL, buf); mu.mem_map_ptr(0x40000000, 0x2000000, UC_PROT_ALL, buf)
    mu.mem_map(0x42000000, 0x2000000); mu.mem_map(0xf0000000, 0x10000000)
    mu._keep = buf
    return mu

def crumbs(mu): return bytes(mu.mem_read(C.CRUMB, 0x400))
W32 = lambda b, o: struct.unpack('<I', b[o:o + 4])[0]

# ---- 1: stub
mu = machine(); mu.mem_write(0, ffboot); n = [0]
def code1(uc, a, s, u):
    n[0] += 1
    if a == 0 and n[0] > 1: uc.emu_stop()
mu.hook_add(UC_HOOK_CODE, code1, begin=0, end=0)
mu.mem_write(C.CRUMB, b'\x55' * 0x400)                       # garbage from a previous life
try: mu.emu_start(0, 0xffffffff, count=4_000_000_000)
except UcError as e: print('stub run error', e, hex(mu.reg_read(UC_ARM_REG_PC)))
cb = crumbs(mu)
check('stub: jumped to the loader, loader at 0 identical', bytes(mu.mem_read(0, 0x40000)) == loader)
check('stub: header', W32(cb, 0) == C.MAGIC and W32(cb, 4) == 1)
check('stub: progress 0x03, bitmap 0b111', W32(cb, 0x10) == 0x03 and W32(cb, 0x14) == 0b111, f'{W32(cb, 0x10):#x} {W32(cb, 0x14):#b}')
check('stub: snapshot written (cpsr mode SVC), rest of block zeroed', W32(cb, 0x20) & 0x1f == 0x13 and cb[0x100:0x200] == bytes(0x100))

# ---- 2-5: loader side
def run_loader(fault=None, resume_flag=0, budget=30_000_000):
    mu = machine(); mu.mem_write(0, loader)
    mu.mem_write(0x40000, img[0x8025c:0x8025c + 0xd7a0]); mu.mem_write(0xd0000, img[0xa025c:0xa025c + 0xd760])
    mu.mem_write(0x774000, b1)
    mu.mem_write(C.UI_DB, img[0xc8025c:0xc8025c + C.UI_DB_LEN])
    mu.mem_write(C.CRUMB, cb)                                 # what the stub left
    mu.mem_write(C.BOOTINFO, struct.pack('<3I', 0x0145, 2, 0xd540))   # late snapshot: Fn + dial held, port 2 bit 11 gone
    st = {'stop': None, 'hb': 0}
    def code(uc, a, s, u):
        if a == 0x42c88:
            uc.reg_write(UC_ARM_REG_R0, 0); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR)); return
        if a == 0x8554c4: st['stop'] = 'blob1'; uc.emu_stop(); return
        if a == 0x4013c: st['stop'] = 'section 0 dabt handler'; uc.emu_stop(); return
        if a == 0x40dd0 and resume_flag == 0: st['stop'] = 'section 0 common handler (should be trapped)'; uc.emu_stop(); return
        if fault and a == fault and not st.get('faulted'):
            st['faulted'] = True
            if resume_flag: uc.mem_write(C.RESUME_FLAG, struct.pack('<I', resume_flag))
            cpsr = uc.reg_read(UC_ARM_REG_CPSR)
            uc.reg_write(UC_ARM_REG_CPSR, (cpsr & ~0x1f) | 0x17 | 0x1c0)
            uc.reg_write(UC_ARM_REG_SPSR, cpsr); uc.reg_write(UC_ARM_REG_LR, a + 8)
            uc.reg_write(UC_ARM_REG_SP, 0x3800)
            uc.reg_write(UC_ARM_REG_CP_REG, (15, 0, 0, 5, 0, 0, 0, 0x406)); uc.reg_write(UC_ARM_REG_CP_REG, (15, 0, 0, 6, 0, 0, 0, 0xfffb3400))
            uc.reg_write(UC_ARM_REG_PC, 0x10)
    mu.hook_add(UC_HOOK_CODE, code)
    mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, 0x3f00)
    mu.reg_write(UC_ARM_REG_R0, 0x8554c4); mu.reg_write(UC_ARM_REG_R3, 0x40020)
    try: mu.emu_start(0x405c, 0xffffffff, count=budget)
    except UcError as e: st['err'] = f'{e} at {mu.reg_read(UC_ARM_REG_PC):#x}'
    return mu, st

mu, st = run_loader()
cb2 = crumbs(mu); w = lambda a: struct.unpack('<I', bytes(mu.mem_read(a, 4)))[0]
bits = W32(cb2, 0x14); want = [0x01, 0x02, 0x03, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x20]
check('clean: reached blob1 entry', st['stop'] == 'blob1', str(st))
check('clean: progress 0x20, bitmap = stub + loader + 5 calls + stage B', W32(cb2, 0x10) == 0x20 and
      bits == sum(1 << C.BIT[c] for c in want), f'{W32(cb2, 0x10):#x} {bits:#b}')
check('clean: hand-over snapshot written (cpsr, mpuir)', W32(cb2, C.SNAP_PRE) & 0x1f == 0x13 and W32(cb2, C.SNAP_PRE + 8) != 0)
check('clean: Ver3.89 marker applied', w(0x857a98) == 0xe3a03039)
check('clean: svc/reserved/irq/fiq literals restored, fatal ones trapped',
      [w(C.SLOTS[i]) for i in (1, 4, 5, 6)] == [C.POOL_OLD[i] for i in (1, 4, 5, 6)] and
      all(w(C.SLOTS[i]) != C.POOL_OLD[i] for i in C.FATAL))
check('clean: power-on key snapshot fixed, seen values kept', w(C.BOOTINFO) == 0x0d45 and w(C.BOOTINFO + 4) == 2 and
      w(C.BOOTINFO + 8) == 0xdd40 and W32(cb2, C.KEYS_SEEN) == 0x0145 and W32(cb2, C.KEYS_SEEN + 4) == 0xd540)
uidb = UI.db(); want = bytearray(uidb)
for o, w4 in UI.records(uidb): struct.pack_into('<2I', want, o, w4[1], w4[0])
live = bytes(mu.mem_read(C.UI_DB, C.UI_DB_LEN))
uisw = bytes(mu.mem_read(C.UISWAP, 4)) != b'\xff' * 4
check('clean: UI colours ' + ('swapped exactly as the live-tested plan' if uisw else 'untouched (no --uiswap)'),
      live == (bytes(want) if uisw else uidb), f'{sum(live[i] != uidb[i] for i in range(0, len(uidb), 4))} words changed')
check('clean: no exception record', cb2[C.EXC:C.EXC + 0x20] == bytes(0x20))

# phase trampolines: call each with r4 → a `bx lr` stub, check record + return
for site, code_ in C.PHASES:
    tramp = (struct.unpack('<I', bytes(mu.mem_read(site, 4)))[0] & 0xffffff); off = tramp << 2
    off = off - (1 << 26) if off & (1 << 25) else off; target = site + 8 + off
    mu.mem_write(0x1f40000, bytes.fromhex('1eff2fe1'))             # bx lr
    mu.reg_write(UC_ARM_REG_R4, 0x1f40000); mu.reg_write(UC_ARM_REG_LR, 0x1f40100); mu.mem_write(0x1f40100, bytes.fromhex('fefffeea'))
    mu.reg_write(UC_ARM_REG_SP, 0x1f30000)
    try: mu.emu_start(target, 0x1f40100, count=10_000)
    except UcError as e: print(e)
    check(f'phase checkpoint {code_:#x}', w(C.CRUMB + 0x10) == code_ and mu.reg_read(UC_ARM_REG_PC) == 0x1f40100)

mu, st = run_loader(fault=0x43148)
cb3 = crumbs(mu)
check('fault: exception record', W32(cb3, C.EXC) == 4 and W32(cb3, C.EXC + 4) == 0x43150 and W32(cb3, C.EXC + 12) == 0x406
      and W32(cb3, C.EXC + 16) == 0xfffb3400 and W32(cb3, C.EXC + 20) == 0x14,
      ' '.join(f'{W32(cb3, C.EXC + 4 * i):#x}' for i in range(7)))
check('fault: heartbeat counting', W32(cb3, C.HEARTBEAT) > 1000, str(W32(cb3, C.HEARTBEAT)))
mu, st = run_loader(fault=0x43148, resume_flag=1)
check('fault + resume flag: chained to section 0 handler', st['stop'] == 'section 0 dabt handler', str(st))
print('ALL OK' if ok else 'FAILED'); sys.exit(0 if ok else 1)
