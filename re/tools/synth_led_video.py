# Make a synthetic phone video of the status LED for a faked crash, to test led_video.py end to end.
# Emulates the trace-patched loader's crash reporter (unicorn) and renders the LED states as a blinking dot over a noisy
# background, H.264-compressed. usage: synth_led_video.py <FPUPDATE.DAT> <out.mp4> [fps]
import os, struct, subprocess, sys
import numpy as np
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PC, UC_CPU_ARM_CORTEX_R5
sys.path.insert(0, os.path.dirname(__file__))
import loader_trace

dat, out = sys.argv[1:3]; fps = int(sys.argv[3]) if len(sys.argv) > 3 else 30
raw = open(dat, 'rb').read(); L = bytearray(bytes(x ^ 0xff for x in raw[0x4025c:0x4025c + 0x40000]))
at = loader_trace.patch(L)
struct.pack_into('<II', L, loader_trace.CP_LAST, 5, 1)          # fake: last checkpoint 5, one async abort absorbed
code = bytes(Ks(KS_ARCH_ARM, KS_MODE_ARM).asm(f'''
    cps #0x17
    movw r0, #0x8
    mcr p15, 0, r0, c5, c0, 0
    movw r0, #0x2004
    movt r0, #0xfffb
    mcr p15, 0, r0, c6, c0, 0
    movw lr, #0x4f74
    movw sp, #0x3c00
    b {at['t_dabt']:#x}''', 0xa000)[0])
L[0xa000:0xa000 + len(code)] = code
mu = Uc(UC_ARCH_ARM, UC_MODE_ARM); mu.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_R5)
mu.mem_map(0, 0x1000000); mu.mem_map(0x40000000, 0x2000000); mu.mem_map(0xf0000000, 0x10000000)
mu.mem_write(0, bytes(L))
SLICE = 100_000; tick = [0]; events = []; st = {'g': 0, 'o': 0}
def gpio(uc, acc, a, s, v, u):
    for pin, key in ((2, 'g'), (0, 'o')):
        if v & (1 << (16 + pin)): st[key] = 0 if v & (1 << pin) else 1
    events.append((tick[0], st['g'], st['o']))
mu.hook_add(UC_HOOK_MEM_WRITE, gpio, begin=0xfff893c0, end=0xfff893c3)
pc = 0xa000
for tick[0] in range(9000):                                     # 900M instructions: more than one report cycle
    try: mu.emu_start(pc, 0xffffffff, count=SLICE)
    except UcError as e: print(e); break
    pc = mu.reg_read(UC_ARM_REG_PC)
ips = 5.2e6 / SLICE                                             # slices per second at an assumed camera speed
T = events[-1][0] / ips + 2; frames = int(T * fps)
rng = np.random.default_rng(1); h, w = 360, 640
bg = (rng.random((h, w, 3)) * 60 + 40).astype(np.uint8)
yy, xx = np.ogrid[:h, :w]; dot = (yy - 200) ** 2 + (xx - 420) ** 2 <= 36
p = subprocess.Popen(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                      '-s', f'{w}x{h}', '-r', str(fps), '-i', '-', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                      '-crf', '28', out], stdin=subprocess.PIPE)
ei = 0; g = o = 0
for fi in range(frames):
    t = fi / fps
    while ei < len(events) and events[ei][0] / ips <= t: _, g, o = events[ei]; ei += 1
    img = bg.copy()
    col = np.clip(np.array([60, 255, 60]) * g + np.array([255, 140, 20]) * o, 0, 255)
    if g or o: img[dot] = col.astype(np.uint8)
    img = np.clip(img.astype(int) + rng.integers(-8, 9, img.shape), 0, 255).astype(np.uint8)
    p.stdin.write(img.tobytes())
p.stdin.close(); p.wait()
print(f'{out}: {frames} frames, {T:.1f} s, {len(events)} LED writes; expected report: data abort | cp 5 | async 1 | '
      f'lr 0x4f74 | fsr 0x8 | far 0xfffb2004')
