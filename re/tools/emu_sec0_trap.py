# Emulator test for the section-0 exception reporter (sec0_trap.py) in an SD chain card (build_sdchain.py --sec0trap).
# usage: emu_sec0_trap.py <FPUPDATE.DAT> <ffboot.bin> [--video out.mp4] [--cp]   (--cp: card built with --sec0cp)
# Memory is set up as the stock loader leaves it (sections from the update file at their RAM addresses, DRAM aliased at
# 0 and 0x40000000), then execution starts at the loader's final jump (0x405c; r0 = blob1 entry, r3 = section 0 entry).
#   run 1, no fault: PRE → stage A (ORANGE) → section 0 → stage B (GREEN; marker applied, section 0's own vector
#          literals restored, progress 2) → blob1 entry.
#   run 2, fault injected inside section 0 (data abort at a VIC write in 0x43fc0, before stage B): the report on the
#          GPIO writes must decode to exactly the injected values. --video renders run 2 as a phone-like video for
#          led_video.py --layout sec0.
# Needs: unicorn, keystone (via sec0_trap import), numpy + ffmpeg for --video.
import os, struct, subprocess, sys, zlib, ctypes
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_PROT_ALL
from unicorn.arm_const import *
sys.path.insert(0, os.path.dirname(__file__))
import sec0_trap

args = sys.argv[1:]
video = args[args.index('--video') + 1] if '--video' in args else None
cp = '--cp' in args
dat, boot = args[:2]
img = bytes(x ^ 0xff for x in open(dat, 'rb').read())
ffboot = open(boot, 'rb').read()
m = ffboot.find(struct.pack('<I', 0x4e494843)); _, po, pl, ol, crc = struct.unpack('<5I', ffboot[m - 0x14:m])
loader = zlib.decompress(ffboot[po:po + pl], -15); assert len(loader) == ol and zlib.crc32(loader) & 0xffffffff == crc
sys.path.insert(0, os.path.dirname(__file__)); import lz
def blob(off):
    dst, src = struct.unpack('<2I', img[off:off + 8]); o, p, err = lz.decode(img, off + 20, src - 20)
    assert err is None and len(o) == dst; return bytes(o)
SECTIONS = [(0x40000, img[0x8025c:0x8025c + 0xd7a0]), (0xd0000, img[0xa025c:0xa025c + 0xd760]),
            (0x774000, blob(0x10025c))]
MARK_AT, MARK_OLD, MARK_NEW = 0x857a98, 0xe3a03032, 0xe3a03039
BLOB1_ENTRY, SEC0_ENTRY = 0x8554c4, 0x40020
GPIO = 0xfff893c0
DELAY_INSN = struct.pack('<I', 0xe25cc001)        # subs r12, r12, #1 (all LED delay loops in loader_hook / sec0_trap)


def cp15(mu, crn, crm, opc1, opc2, val=None):
    if val is None: return mu.reg_read(UC_ARM_REG_CP_REG, (15, 0, 0, crn, crm, opc1, opc2))
    mu.reg_write(UC_ARM_REG_CP_REG, (15, 0, 0, crn, crm, opc1, opc2, val))


def run(fault=None, budget=20_000_000):
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM); mu.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_R5)
    buf = ctypes.create_string_buffer(0x2000000)
    mu.mem_map_ptr(0, 0x2000000, UC_PROT_ALL, buf); mu.mem_map_ptr(0x40000000, 0x2000000, UC_PROT_ALL, buf)
    mu.mem_map(0x42000000, 0x2000000); mu.mem_map(0xf0000000, 0x10000000)
    mu.mem_write(0, loader)
    for a, b in SECTIONS: mu.mem_write(a, b)
    mu.mem_write(sec0_trap.STUB_ABSORBED, struct.pack('<II', 1, 0x406))      # stub drained one ROM abort
    st = {'led': [], 'stop': None, 'faulted': False}
    led = {'g': 0, 'o': 0}
    def gpio(uc, acc, a, s, v, u):
        for pin, key in ((2, 'g'), (0, 'o')):
            if v & (1 << (16 + pin)): led[key] = 0 if v & (1 << pin) else 1
        st['led'].append((st['n'], led['g'], led['o']))
        if led['g'] and led['o']:              # MARK (both on): stop at the start of the third report cycle
            st['marks'] = st.get('marks', 0) + 1
            if st['marks'] == 3: st['stop'] = 'two report cycles'; uc.emu_stop()
    st['n'] = 0
    def code(uc, a, s, u):
        st['n'] += 1
        if 0x9000 <= a < 0xc000 and uc.mem_read(a, 4) == DELAY_INSN:   # LED delay loop: skip, keep virtual time
            r12 = uc.reg_read(UC_ARM_REG_R12)
            if r12 > 1: st['n'] += 2 * (r12 - 1); uc.reg_write(UC_ARM_REG_R12, 1)
            return
        if a == 0x42c88:                       # core-0 check (DBGDSAR == 0x4003): unicorn's p14 reads 0
            uc.reg_write(UC_ARM_REG_R0, 0); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR)); return
        if a == BLOB1_ENTRY: st['stop'] = 'blob1 entry'; uc.emu_stop(); return
        if fault and a == fault['pc'] and not st['faulted']:
            st['faulted'] = True                # take a data abort as the CPU would: abort mode, lr = pc + 8
            cpsr = uc.reg_read(UC_ARM_REG_CPSR)
            uc.reg_write(UC_ARM_REG_CPSR, (cpsr & ~0x1f) | 0x17 | 0x1c0)
            uc.reg_write(UC_ARM_REG_SPSR, cpsr); uc.reg_write(UC_ARM_REG_LR, a + 8)
            cp15(uc, 5, 0, 0, 0, fault['dfsr']); cp15(uc, 6, 0, 0, 0, fault['dfar'])
            uc.reg_write(UC_ARM_REG_PC, 0x10)
    mu.hook_add(UC_HOOK_CODE, code)
    mu.hook_add(UC_HOOK_MEM_WRITE, gpio, begin=GPIO, end=GPIO + 3)
    mu.reg_write(UC_ARM_REG_CPSR, 0x1d3); mu.reg_write(UC_ARM_REG_SP, 0x3f00)
    mu.reg_write(UC_ARM_REG_R0, BLOB1_ENTRY); mu.reg_write(UC_ARM_REG_R3, SEC0_ENTRY)
    try: mu.emu_start(0x405c, 0xffffffff, count=budget)
    except UcError as e: st['err'] = f'{e} at {mu.reg_read(UC_ARM_REG_PC):#x}'
    st['mem'] = lambda a, n=4: bytes(mu.mem_read(a, n)); st['_keep'] = (mu, buf)   # buf backs the RAM mapping
    return st


def bits_from_led(events):
    """GPIO events → symbols: B (both on), G, O (one on), in order of 'on' states."""
    out = []; prev = (0, 0)
    for _, g, o in events:
        if (g, o) != prev and (g or o): out.append('B' if g and o else 'G' if g else 'O')
        prev = (g, o)
    return out


def decode_report(sym):
    for i, s in enumerate(sym):
        if s != 'B': continue
        bits = sym[i + 1:]; words = []
        for _, nb in sec0_trap.FIELDS:
            if len(bits) < nb or 'B' in bits[:nb]: break
            words.append(int(''.join('1' if b == 'O' else '0' for b in bits[:nb]), 2)); bits = bits[nb:]
        if len(words) == len(sec0_trap.FIELDS): return sec0_trap.decode(words)
    return None


CP_SEQ = ['O'] + sum([['G'] * k + ['O'] for k in range(1, 6)], [])   # stage A, then G×k + ORANGE
ok = True
st = run()
w = lambda a: struct.unpack('<I', st['mem'](a))[0]
slots = [w(a) for a in sec0_trap.SLOTS]; prog = w(sec0_trap.SAVE + 24)
syms = bits_from_led(st['led'])
r1 = (st['stop'] == 'blob1 entry', w(MARK_AT) == MARK_NEW, slots == sec0_trap.POOL_OLD, prog == 2, syms == (CP_SEQ + ['G'] if cp else ['O', 'G']))
print(f'run 1 (no fault): stop={st["stop"]} err={st.get("err")} marker={w(MARK_AT):#x} slots restored={r1[2]} '
      f'progress={prog} LED={syms} pool={[hex(w(sec0_trap.POOL + 4 * i)) for i in range(7)]}')
ok &= all(r1)

FAULT = {'pc': 0x43148, 'dfsr': 0x406, 'dfar': 0xfffb3400}
st = run(FAULT, budget=20_000_000)
syms = bits_from_led(st['led'])
rep = decode_report(syms)
print('run 2 (data abort injected at', hex(FAULT['pc']), '):', 'err', st.get('err'), '| LED symbols', len(syms),
      '| before report:', ''.join(syms[:syms.index('B')]) if 'B' in syms else '-')
if cp: ok &= 'B' in syms and syms[:syms.index('B')] == CP_SEQ[:1 + sum(k + 1 for k in range(1, 5))]
print('  decoded:', {k: (hex(v) if isinstance(v, int) else v) for k, v in (rep or {}).items()})
exp = rep and (rep['progress_type'] == 0x14 and rep['lr'] == FAULT['pc'] + 8 and rep['fsr'] == FAULT['dfsr'] and
               rep['far'] == FAULT['dfar'] and rep['rom_aborts'] == 1 and rep['rom_abort_dfsr'] == 0x406 and
               (rep['spsr'] & 0x1f) == 0x13)
print('  matches injected fault:', bool(exp))
ok &= bool(exp)
if video and st['led']:
    import numpy as np
    ev = st['led']; ips = 13e6                     # instructions per second with caches off (trace video, E13)
    fps = 30; T = ev[-1][0] / ips + 2; nfr = int(T * fps)
    rng = np.random.default_rng(1); h, wd = 360, 640
    bg = (rng.random((h, wd, 3)) * 60 + 40).astype(np.uint8)
    yy, xx = np.ogrid[:h, :wd]; dot = (yy - 200) ** 2 + (xx - 420) ** 2 <= 36
    p = subprocess.Popen(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                          '-s', f'{wd}x{h}', '-r', str(fps), '-i', '-', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                          '-crf', '28', video], stdin=subprocess.PIPE)
    ei = 0; g = o = 0
    for fi in range(nfr):
        t = fi / fps
        while ei < len(ev) and ev[ei][0] / ips <= t: _, g, o = ev[ei]; ei += 1
        fr = bg.copy()
        col = np.clip(np.array([60, 255, 60]) * g + np.array([255, 140, 20]) * o, 0, 255)
        if g or o: fr[dot] = col.astype(np.uint8)
        fr = np.clip(fr.astype(int) + rng.integers(-8, 9, fr.shape), 0, 255).astype(np.uint8)
        p.stdin.write(fr.tobytes())
    p.stdin.close(); p.wait(); print(f'video {video}: {nfr} frames, {T:.0f} s')
print('ALL OK' if ok else 'FAILED'); sys.exit(0 if ok else 1)
