# Emulator test for the PTP debug operations (build_ptpdebug.py): runs the real PTP dispatcher FUN_00f4521c of the
# patched blob2 (with blob1 mapped for its library calls). Only the USB send FUN_00f44ca8 is replaced by a hook that
# records the container (code, data pointer/length, data bytes).
# usage: emu_ptpdebug.py <re/work dir with blob1.bin, blob2.bin>
import os, struct, sys
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
sys.path.insert(0, os.path.dirname(__file__))
import build_ptpdebug as B

W = sys.argv[1]
b1 = open(os.path.join(W, 'blob1.bin'), 'rb').read()
stock_b2 = open(os.path.join(W, 'blob2.bin'), 'rb').read()
b2 = bytearray(stock_b2); info = B.patch_blob2(b2)
DISPATCH, REQ, STACK, DONE, FN = 0xf4521c, 0x1f00000, 0x1e00000, 0x1f30000, 0x1f20000
seen = {}


def machine(session=1):
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM); mu.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_R5)
    mu.mem_map(0, 0x2000000); mu.mem_map(0x40000000, 0x8000000)
    mu.mem_write(0x774000, b1); mu.mem_write(B.B2_BASE, bytes(b2))
    mu.mem_write(B.SESSION, struct.pack('<I', session)); mu.mem_write(B.CB, struct.pack('<I', 0xf5100c))
    mu.mem_write(0x11f3eb8, struct.pack('<I', 0))                    # allocator state → 4 MB buffer 0x42dfad10
    mu.mem_write(DONE, struct.pack('<I', 0xe1a00000))                 # nop (stop marker)
    mu.mem_write(FN, bytes.fromhex('010080e2') + bytes.fromhex('1eff2fe1'))   # add r0, r0, #1 ; bx lr
    sent = []
    def code(uc, a, s, u):
        if a == B.F_SEND:
            c = B.CONT; rd = lambda o, n=4: int.from_bytes(uc.mem_read(c + o, n), 'little')
            ptr, ln = rd(0x24), rd(0x28)
            sent.append({'code': rd(0, 2), 'tid': rd(8), 'len': ln, 'data': bytes(uc.mem_read(ptr, ln)) if ln else b''})
            uc.reg_write(UC_ARM_REG_R0, 0); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        elif a == DONE: uc.emu_stop()
        elif a in (0xf4a840, B.GENERIC) or B.CAVE <= a < B.CAVE_END: seen.setdefault(a, 0); seen[a] += 1
    mu.hook_add(UC_HOOK_CODE, code)
    return mu, sent


def op(mu, opcode, phase, *params, tid=0x55):
    req = struct.pack('<HHII', opcode, 0, 1, tid) + struct.pack('<I', len(params)) + b''.join(struct.pack('<I', p) for p in params)
    mu.mem_write(REQ, req + bytes(0x40 - len(req)))
    mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_R0, phase); mu.reg_write(UC_ARM_REG_R1, REQ); mu.reg_write(UC_ARM_REG_LR, DONE)
    mu.emu_start(DISPATCH, 0xffffffff, count=5_000_000)


ok = True
def check(name, cond, detail=''):
    global ok; ok &= bool(cond); print(f'{"OK  " if cond else "FAIL"} {name} {detail}')

print('patch:', info)
mu, sent = machine()
op(mu, 0x9010, 1, 0x774000, 0x100); op(mu, 0x9010, 2)
check('PEEK data phase', sent[0]['code'] == 0x9010 and sent[0]['data'] == b1[:0x100], f"len {sent[0]['len']:#x}")
check('PEEK response OK', sent[1]['code'] == 0x2001 and sent[1]['tid'] == 0x55)
sent.clear(); op(mu, 0x9010, 1, B.B2_BASE + 0x1000, 0x20003); op(mu, 0x9010, 2)
check('PEEK length clamped to 0x10000', sent[0]['len'] == 0x10000 and sent[0]['data'] == stock_b2[0x1000:0x11000])
sent.clear(); op(mu, 0x9011, 1, 0x1f10000, 0x12345678)
check('POKE writes + responds OK', mu.mem_read(0x1f10000, 4) == struct.pack('<I', 0x12345678) and sent[0]['code'] == 0x2001)
sent.clear(); op(mu, 0x9012, 1, FN, 41); res = struct.unpack('<I', mu.mem_read(int(info['handlers']['result'], 16), 4))[0]
check('CALL runs + result stored', res == 42 and sent[0]['code'] == 0x2001, f'result {res}')
sent.clear(); op(mu, 0x9010, 1, int(info['handlers']['result'], 16), 4); op(mu, 0x9010, 2)
check('PEEK reads back RESULT', sent[0]['data'] == struct.pack('<I', 42))
seen.clear(); sent.clear(); op(mu, 0x1004, 1)
check('GetStorageIDs (0x1004) still routed to 0xf4a840', 0xf4a840 in seen)
seen.clear(); sent.clear(); op(mu, 0x1010, 1)
check('0x1010 (old stub slot) → generic not-supported', B.GENERIC in seen and not any(B.CAVE <= a < B.CAVE_END for a in seen))
seen.clear(); sent.clear(); op(mu, 0x9001, 1)
check('0x9001 unchanged → generic', B.GENERIC in seen)
mu2, sent2 = machine(session=0)
op(mu2, 0x9010, 1, 0x774000, 0x100); op(mu2, 0x9010, 2)
check('PEEK without session → 0x2003, no data', sent2[0]['len'] == 0 and sent2[1]['code'] == 0x2003)
sent2.clear(); op(mu2, 0x9011, 1, 0x1f10000, 1)
check('POKE without session → 0x2003, nothing written', sent2[0]['code'] == 0x2003 and mu2.mem_read(0x1f10000, 4) == bytes(4))
print('ALL OK' if ok else 'FAILED'); sys.exit(0 if ok else 1)
