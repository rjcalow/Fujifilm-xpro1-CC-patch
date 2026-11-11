# Emulate the SD chain boot past the hand-over into the trace-patched stock loader (unicorn, Cortex-R5 model).
# Hardware regions are plain RAM, so this checks the patch plumbing (checkpoint order, register preservation, crash
# reporter encoding), not the real hardware behaviour.
#   emu_trace.py <FPUPDATE.DAT> <ffboot.bin> [budget]        boot path: order of checkpoints and original routines
#   emu_trace.py <FPUPDATE.DAT> <ffboot.bin> --report         crash reporter: decode its blink groups for test faults
import os, re, struct, sys, zlib
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_SP, UC_CPU_ARM_CORTEX_R5
sys.path.insert(0, os.path.dirname(__file__))
import loader_trace

dat, boot = sys.argv[1:3]
img = open(boot, 'rb').read()
raw = open(dat, 'rb').read(); stock = bytes(x ^ 0xff for x in raw[0x4025c:0x4025c + 0x40000])
probe = bytearray(stock); at = loader_trace.patch(probe)               # addresses of every trampoline
m = img.find(struct.pack('<I', 0x4e494843)); _s, po, pl, n, c = struct.unpack('<5I', img[m - 0x14:m])
assert zlib.decompress(img[po:po + pl], -15) == bytes(probe), 'ffboot payload is not the current trace build'


def machine():
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM); mu.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_R5)
    mu.mem_map(0, 0x1000000); mu.mem_map(0x40000000, 0x2000000); mu.mem_map(0xf0000000, 0x10000000)
    return mu


def led_log(mu):
    log = []; st = {'g': 0, 'o': 0}
    def gpio(uc, acc, a, s, v, u):
        for pin, key in ((2, 'g'), (0, 'o')):
            if v & (1 << (16 + pin)): st[key] = 0 if v & (1 << pin) else 1
        log.append((st['g'], st['o']))
    mu.hook_add(UC_HOOK_MEM_WRITE, gpio, begin=0xfff893c0, end=0xfff893c3)
    return log


def groups(log):
    """Collapse LED states into blink groups: consecutive identical 'on' colours separated by off phases."""
    out = []; prev = (0, 0)
    for g, o in log:
        if (g, o) != (0, 0) and prev == (0, 0):
            col = 'B' if g and o else 'G' if g else 'O'
            if out and out[-1][0] == col and not out[-1][2]: out[-1][1] += 1
            else: out.append([col, 1, False])
        prev = (g, o)
    return [(c, k) for c, k, _ in out]


def decode_binary(log):
    """Binary crash report: MARK = both on; then one 'on' per bit, GREEN = 0, ORANGE = 1."""
    ons = []; prev = (0, 0)
    for g, o in log:
        if (g, o) != (0, 0) and prev == (0, 0): ons.append('B' if g and o else 'G' if g else 'O')
        prev = (g, o)
    if 'B' not in ons: return None
    bits = ons[ons.index('B') + 1:]
    out = []
    for n in (4, 8, 8, 32, 16, 32):
        if len(bits) < n or 'B' in bits[:n]: return out
        out.append(int(''.join('1' if b == 'O' else '0' for b in bits[:n]), 2)); bits = bits[n:]
    return out


if '--report' in sys.argv:
    from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM
    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)
    PRO = 0x0a000                                            # free filler: prologue that sets fault registers
    for name, kind, lr, cp, fsr, far in (('data abort', 't_dabt', 0x4f6c + 8, 4, 0x0008, 0xfffb2004),
                                         ('undef', 't_undef', 0x41f00a04, 0, 0, 0),
                                         ('prefetch abort', 't_pabt', 0x20104, 13, 0x000d, 0x20100)):
        mu = machine(); m = bytearray(probe); struct.pack_into('<I', m, loader_trace.CP_LAST, cp)
        code = bytes(ks.asm(f'''
            cps #0x17
            movw r0, #{fsr & 0xffff}
            mcr p15, 0, r0, c5, c0, 0
            mcr p15, 0, r0, c5, c0, 1
            movw r0, #{far & 0xffff}
            movt r0, #{far >> 16}
            mcr p15, 0, r0, c6, c0, 0
            mcr p15, 0, r0, c6, c0, 2
            movw lr, #{lr & 0xffff}
            movt lr, #{lr >> 16}
            movw sp, #0x3c00
            b {at[kind]:#x}''', PRO)[0])
        m[PRO:PRO + len(code)] = code; mu.mem_write(0, bytes(m)); log = led_log(mu)
        try: mu.emu_start(PRO, 0xffffffff, count=400_000_000)
        except UcError as e: print('stopped:', e)
        got = decode_binary(log)
        exp = [{'t_undef': 1, 't_pabt': 2, 't_dabt': 3}[kind], cp, 0, lr, fsr, far]
        print(f'{name:15} expect {[hex(x) for x in exp]}\n{"":15} got    {[hex(x) for x in got] if got else got}',
              'OK' if got == exp else 'MISMATCH')
    # asynchronous data abort (DFSR 0x406) must be absorbed: counter +1, resume at lr - 8, no report
    mu = machine(); m = bytearray(probe)
    code = bytes(ks.asm(f'''
        cps #0x17
        movw r0, #0x406
        mcr p15, 0, r0, c5, c0, 0
        movw sp, #0x3c00
        mrs r0, cpsr
        bic r0, r0, #0x1f
        orr r0, r0, #0x13
        msr spsr_cxsf, r0
        movw lr, #{PRO + 0x100 + 8:#x}
        b {at['t_dabt']:#x}''', PRO)[0])
    m[PRO:PRO + len(code)] = code; m[PRO + 0x100:PRO + 0x104] = bytes(ks.asm('b .', PRO + 0x100)[0])
    mu.mem_write(0, bytes(m)); log = led_log(mu)
    try: mu.emu_start(PRO, 0xffffffff, count=2_000_000)
    except UcError as e: print('stopped:', e)
    cnt = struct.unpack('<I', mu.mem_read(loader_trace.CP_LAST + 4, 4))[0]
    print('async abort: absorbed count', cnt, 'resumed at', hex(mu.reg_read(UC_ARM_REG_PC)), 'LED writes', len(log),
          'OK' if cnt == 1 and mu.reg_read(UC_ARM_REG_PC) == PRO + 0x100 and not log else 'MISMATCH')
    sys.exit()

budget = int(sys.argv[3], 0) if len(sys.argv) > 3 else 1_500_000_000
mu = machine(); mu.mem_write(0, img); led_log(mu)
names = {at[f'cpg{k}']: f'green cp{k}' for k in range(1, 9)}
names.update({at[f'cpo{k}']: f'orange cp{k}' for k in range(1, 8)})
names.update({0x4060: 'modes', 0x40c4: 'stacks', 0x42bc: 'coreid', 0x4f58: 'gpio-init', 0x41e8: 'mpu', 0x47a4: 'main',
              0x4cbc: 'validity', 0x4c64: 'init', 0x44dc: 'hw-wait', 0x4668: 'sect-table', 0x4760: 'sections',
              at['t_report']: 'CRASH REPORT', at['t_err']: 'LOADER ERROR', at['t_final']: 'FINAL'})
order = []
def visit(uc, a, s, u): order.append(names[a])
for a in names: mu.hook_add(UC_HOOK_CODE, visit, begin=a, end=a)
try: mu.emu_start(0, 0xffffffff, count=budget)
except UcError as e: print('stopped:', e)
print('pc', hex(mu.reg_read(UC_ARM_REG_PC)))
print('order:', ' → '.join(order))
