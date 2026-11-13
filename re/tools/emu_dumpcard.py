# Emulator test for the ROM dump card (romdump/build_dumpcard.py). Run emu_crumbs.py on the same card as well (stub,
# loader side, traps): this script checks only what the dump card adds.
# usage: emu_dumpcard.py <ffboot.bin> <re/work dir with blob1.bin, blob2.bin>
#   1 stage B (crumbs STAGE_B, real code from the card's loader): blob1 0x972520 → bl DUMP_HOOK, Ver3.89 marker.
#   2 blob1 0x972518 (the real "start blob2" routine) → DUMP_HOOK → 0x854e48 reached with lr = 0x972524 and the
#     same registers / sp as a stock run, then returns normally; opcode 0x9010 slot → PEEK handler, status 1.
#   3 the real PTP dispatcher FUN_00f4521c (blob2) with that RAM: PEEK returns memory, clamps at 0x10000, refuses
#     without a session; 0x9011 / 0x9012 (POKE / CALL on the debug firmware) stay "not supported"; GetStorageIDs
#     still routed; the ID block reads back.
#   4 slot already in use (flashed debug firmware): left alone, status 2. Other firmware (call site differs): no
#     redirect at stage B, blob2 starts as stock, status stays 0xffffffff.
import ctypes, os, struct, sys, zlib
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_PROT_ALL
from unicorn.arm_const import *
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', '..', 'romdump'))
import crumbs as C, build_ptpdebug as B, build_dumpcard as D

boot, W = sys.argv[1:3]
ffboot = open(boot, 'rb').read()
m = ffboot.find(struct.pack('<I', 0x4e494843)); _, po, pl, ol, crc = struct.unpack('<5I', ffboot[m - 0x14:m])
loader = zlib.decompress(ffboot[po:po + pl], -15)
assert zlib.crc32(loader) & 0xffffffff == crc
b1 = open(os.path.join(W, 'blob1.bin'), 'rb').read(); b2 = open(os.path.join(W, 'blob2.bin'), 'rb').read()
DISPATCH, REQ, STACK, DONE, FN = 0xf4521c, 0x1f00000, 0x1e00000, 0x1f30000, 0x1f20000
ok = True
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(f'{"OK  " if cond else "FAIL"} {name} {detail}')


def machine(blob1=b1, slot=None):
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM); mu.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_R5)
    mu.mem_map(0, 0x2000000); mu.mem_map(0x40000000, 0x8000000)
    mu.mem_write(0, loader); mu.mem_write(0x774000, blob1); mu.mem_write(B.B2_BASE, b2)
    if slot is not None: mu.mem_write(D.SLOT, struct.pack('<I', slot))
    mu.mem_write(DONE, bytes.fromhex('00f020e3'))                     # nop (stop marker)
    return mu

w = lambda mu, a: struct.unpack('<I', bytes(mu.mem_read(a, 4)))[0]
bl = lambda frm, to: 0xeb000000 | (((to - frm - 8) >> 2) & 0xffffff)


def stage_b(mu):
    mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_R4, DONE); mu.reg_write(UC_ARM_REG_LR, 0x40bb0); mu.reg_write(UC_ARM_REG_R0, 0)
    mu.emu_start(C.STAGE_B, DONE, count=100_000)
    return mu.reg_read(UC_ARM_REG_PC) == DONE


def start_blob2(mu):
    """Run blob1 0x972518 to its return; returns what the blob2 entry 0x854e48 saw."""
    seen = {}
    def code(uc, a, s, u):
        if a == D.START_B2:
            seen['lr'] = uc.reg_read(UC_ARM_REG_LR)
            seen['regs'] = [uc.reg_read(r) for r in (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                                                     UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)]
            seen['sp'] = uc.reg_read(UC_ARM_REG_SP)
            uc.reg_write(UC_ARM_REG_PC, seen['lr'])                    # blob2 runs, then returns
    h = mu.hook_add(UC_HOOK_CODE, code)
    mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, STACK); mu.reg_write(UC_ARM_REG_LR, DONE)
    regs = [0x44440000 + i for i in range(4, 12)]
    for r, v in zip((UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9,
                     UC_ARM_REG_R10, UC_ARM_REG_R11), regs): mu.reg_write(r, v)
    mu.emu_start(0x972518, DONE, count=100_000)
    mu.hook_del(h)
    seen['returned'] = mu.reg_read(UC_ARM_REG_PC) == DONE and mu.reg_read(UC_ARM_REG_SP) == STACK
    return seen, regs


# ---- 1 + 2
mu = machine()
check('stage B: returns through bx r4', stage_b(mu))
check('stage B: 0x972520 → bl DUMP_HOOK', w(mu, D.SITE) == bl(D.SITE, D.HOOK_AT), f'{w(mu, D.SITE):#x}')
check('stage B: Ver3.89 marker applied', w(mu, 0x857a98) == 0xe3a03039)
check('before blob2 start: slot stock, status unset', w(mu, D.SLOT) == B.GENERIC and w(mu, D.STATUS_AT) == 0xffffffff)
seen, regs = start_blob2(mu)
check('blob2 entry reached with lr = 0x972524', seen.get('lr') == 0x972524, str({k: v for k, v in seen.items() if k != 'regs'}))
ref = machine(); ref_seen, _ = start_blob2(ref)                       # stock: no stage B, no hook
check('registers and sp at blob2 entry identical to a stock run', seen.get('regs') == ref_seen.get('regs') and
      seen.get('sp') == ref_seen.get('sp') and seen['regs'][:7] == regs[:7])
check('0x972518 returns normally (sp restored)', seen['returned'])
check('slot 0x9010 → PEEK handler, status 1', w(mu, D.SLOT) == D.PEEK_AT and w(mu, D.STATUS_AT) == 1)
changed = [a for a in range(0, len(b2), 4) if bytes(mu.mem_read(B.B2_BASE + a, 4)) != b2[a:a + 4]]
check('blob2: only the one table word changed', [B.B2_BASE + a for a in changed] == [D.SLOT],
      str([hex(B.B2_BASE + a) for a in changed[:4]]))

# ---- 3: PTP dispatcher
mu.mem_write(B.SESSION, struct.pack('<I', 1)); mu.mem_write(B.CB, struct.pack('<I', 0xf5100c))
mu.mem_write(0x11f3eb8, struct.pack('<I', 0))                         # allocator state → 4 MB buffer
mu.mem_write(FN, bytes.fromhex('010080e2') + bytes.fromhex('1eff2fe1'))
sent = []; visited = set()
def ptp_code(uc, a, s, u):
    if a == B.F_SEND:
        c = B.CONT; rd = lambda o, n=4: int.from_bytes(uc.mem_read(c + o, n), 'little')
        ptr, ln = rd(0x24), rd(0x28)
        sent.append({'code': rd(0, 2), 'tid': rd(8), 'len': ln, 'data': bytes(uc.mem_read(ptr, ln)) if ln else b''})
        uc.reg_write(UC_ARM_REG_R0, 0); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    elif a in (0xf4a840, B.GENERIC, D.PEEK_AT) or B.CAVE <= a < B.CAVE_END: visited.add(a)
mu.hook_add(UC_HOOK_CODE, ptp_code)
def op(opcode, phase, *params, tid=0x55):
    req = struct.pack('<HHII', opcode, 0, 1, tid) + struct.pack('<I', len(params)) + b''.join(struct.pack('<I', p) for p in params)
    mu.mem_write(REQ, req + bytes(0x40 - len(req)))
    mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_R0, phase); mu.reg_write(UC_ARM_REG_R1, REQ); mu.reg_write(UC_ARM_REG_LR, DONE)
    mu.emu_start(DISPATCH, DONE, count=5_000_000)

op(0x9010, 1, 0x774000, 0x100); op(0x9010, 2)
check('PEEK: data phase = memory', sent[0]['code'] == 0x9010 and sent[0]['data'] == b1[:0x100] and D.PEEK_AT in visited)
check('PEEK: response OK, transaction id kept', sent[1]['code'] == 0x2001 and sent[1]['tid'] == 0x55)
sent.clear(); op(0x9010, 1, B.B2_BASE + 0x1000, 0x20003); op(0x9010, 2)
check('PEEK: length clamped to 0x10000', sent[0]['len'] == 0x10000 and sent[0]['data'] == b2[0x1000:0x11000])
sent.clear(); op(0x9010, 1, D.ID_AT, 0x20); op(0x9010, 2)
check('PEEK: ID block reads back', sent[0]['data'][:len(D.ID)] == D.ID and sent[0]['data'][0x1c:0x20] == struct.pack('<I', 1))
for opc, name in ((0x9011, 'POKE'), (0x9012, 'CALL')):
    visited.clear(); sent.clear(); mu.mem_write(0x1f10000, bytes(4)); op(opc, 1, 0x1f10000, FN)
    check(f'{opc:#x} ({name} on the debug firmware) → generic not-supported handler, nothing written',
          B.GENERIC in visited and D.PEEK_AT not in visited and w(mu, 0x1f10000) == 0)
visited.clear(); sent.clear(); op(0x1004, 1)
check('GetStorageIDs (0x1004) still routed to 0xf4a840', 0xf4a840 in visited)
mu.mem_write(B.SESSION, struct.pack('<I', 0)); sent.clear(); op(0x9010, 1, 0x774000, 0x100); op(0x9010, 2)
check('PEEK without a session → 0x2003, no data', sent[0]['len'] == 0 and sent[1]['code'] == 0x2003)

# ---- 4: slot in use / other firmware
mu = machine(slot=0x00f45a58); stage_b(mu); seen, _ = start_blob2(mu)
check('slot already used: left alone, status 2, blob2 started', w(mu, D.SLOT) == 0x00f45a58 and
      w(mu, D.STATUS_AT) == 2 and seen.get('lr') == 0x972524)
other = bytearray(b1); other[D.SITE - 0x774000:D.SITE - 0x774000 + 4] = struct.pack('<I', bl(D.SITE, 0x854e7c))
mu = machine(blob1=bytes(other)); stage_b(mu)
check('other firmware: call site not redirected', w(mu, D.SITE) == bl(D.SITE, 0x854e7c))
print('ALL OK' if ok else 'FAILED'); sys.exit(0 if ok else 1)
