# Decode the X-Pro1 status LED from a phone video of an SD-boot test.
# usage: led_video.py <video> [--roi x,y,w,h] [--debug]
# Finds the LED (pixels whose brightness changes most), classifies every frame as off / G (green) / O (orange) /
# B (both), prints the on/off timeline, the checkpoint blink groups, and decodes any binary crash report
# (re/tools/loader_trace.py): MARK = long B, then one blink per bit (G = 0, O = 1), words of
# 4 | 8 | 8 | 32 | 16 | 32 bits: type, last checkpoint, async aborts absorbed, exception lr, fault status, fault address.
# --layout sec0: section-0 exception report of sec0_trap.py (fields in sec0_trap.FIELDS).
import json, subprocess, sys
import numpy as np

FFMPEG = 'ffmpeg'
try:
    import imageio_ffmpeg; FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    pass
WIDTH = 480
TYPES = {1: 'undefined instruction', 2: 'prefetch abort', 3: 'data abort'}


def probe(path):
    out = subprocess.run([FFMPEG, '-hide_banner', '-i', path], capture_output=True, text=True).stderr
    import re
    m = re.search(r'(\d+(?:\.\d+)?) fps', out); fps = float(m.group(1)) if m else 30.0
    m = re.search(r', (\d{2,5})x(\d{2,5})', out); w, h = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    return fps, w, h


def frames(path, w, h):
    cmd = [FFMPEG, '-hide_banner', '-loglevel', 'error', '-i', path, '-vf', f'scale={w}:{h}', '-f', 'rawvideo',
           '-pix_fmt', 'rgb24', '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = w * h * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n: break
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    p.wait()


def main():
    args = sys.argv[1:]; path = args[0]; debug = '--debug' in args
    roi = None
    if '--roi' in args: roi = [int(v) for v in args[args.index('--roi') + 1].split(',')]
    fps, W0, H0 = probe(path)
    w = WIDTH; h = int(round(H0 * WIDTH / W0 / 2)) * 2 if W0 else 270
    if roi is None:                                   # pass 1: locate the LED
        mx = None; sm = None; k = 0
        for f in frames(path, w, h):
            b = f.max(axis=2).astype(np.float32)
            mx = b if mx is None else np.maximum(mx, b); sm = b if sm is None else sm + b; k += 1
        score = mx - sm / k
        score = sum(np.roll(np.roll(score, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        y, x = np.unravel_index(np.argmax(score), score.shape)
        r = 4; roi = [max(0, x - r), max(0, y - r), 2 * r + 1, 2 * r + 1]
        print(f'video {W0}x{H0} @ {fps:.2f} fps, {k} frames; LED found at ({x * W0 // w}, {y * H0 // h}) '
              f'(scaled {x},{y}); override with --roi x,y,w,h on the {w}x{h} scaled frame')
    x, y, rw, rh = roi
    rgb = np.array([f[y:y + rh, x:x + rw].reshape(-1, 3).astype(np.float32) for f in frames(path, w, h)])
    # use the brightest pixels of the ROI in each frame (the LED core), average them
    bright = rgb.max(axis=2)
    idx = np.argsort(bright, axis=1)[:, -6:]
    core = np.take_along_axis(rgb, idx[:, :, None], axis=1).mean(axis=1)
    lum = core.max(axis=1)
    lo, hi = np.percentile(lum, 10), np.percentile(lum, 99)
    on = lum > lo + 0.45 * (hi - lo)
    if on.sum() == 0:
        print('no LED activity found'); return
    # colour: normalise red and green to their off level and their maximum over lit frames.
    # green LED → red low; orange → red high, green not at maximum; both → red and green high.
    off = ~on
    R0, G0 = (np.percentile(core[off, 0], 50), np.percentile(core[off, 1], 50)) if off.any() else (0, 0)
    Rm, Gm = np.percentile(core[on, 0], 98), np.percentile(core[on, 1], 98)
    Rn = (core[:, 0] - R0) / max(Rm - R0, 1); Gn = (core[:, 1] - G0) / max(Gm - G0, 1)
    if debug:
        for name, arr in (('Rn', Rn[on]), ('Gn', Gn[on])):
            print(name, 'percentiles 5/25/50/75/95:', np.round(np.percentile(arr, [5, 25, 50, 75, 95]), 2))
    single = np.percentile(Rn[on], 95) - np.percentile(Rn[on], 5) < 0.3     # only one colour ever lit
    def label(i):
        if not on[i]: return '.'
        if single: return 'G'
        if Rn[i] < 0.5: return 'G'
        return 'B' if Gn[i] >= 0.8 else 'O'
    lab = [label(i) for i in range(len(lum))]
    segs = []                                                     # (label, n_frames)
    for L in lab:
        if segs and segs[-1][0] == L: segs[-1][1] += 1
        else: segs.append([L, 1])
    print('timeline (label:seconds), "." = off:')
    print(' '.join(f'{L}:{n / fps:.2f}' for L, n in segs))
    ons = [(L, n) for L, n in segs if L != '.']
    offs = [n for L, n in segs if L == '.']
    if not ons: return
    unit = np.median([n for L, n in ons if L in 'GO']) if any(L in 'GO' for L, _ in ons) else ons[0][1]
    print(f'\nmedian blink length {unit / fps:.2f} s')
    # checkpoint groups: same-colour blinks separated by short gaps; a long gap (> 2.5 units) ends a group
    groups = []; cur = None
    for (L, n), gap in zip(segs, [0] + [s[1] for s in segs[:-1]]):
        pass
    i = 0; gap_before = 1e9
    for L, n in segs:
        if L == '.': gap_before = n; continue
        if cur and cur[0] == L and gap_before <= 2.5 * unit: cur[1] += 1
        else:
            cur = [L, 1]; groups.append(cur)
        gap_before = 0
    print('blink groups:', ' '.join(f'{L}x{k}' for L, k in groups))
    # binary crash report
    seq = [L for L, n in ons]; lens = [n for L, n in ons]
    if '--layout' in args and args[args.index('--layout') + 1] == 'sec0':
        import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import sec0_trap
        for s0 in range(len(seq)):
            if seq[s0] == 'B' and lens[s0] >= 2 * unit:
                bits = seq[s0 + 1:]; words = []
                for _, nb in sec0_trap.FIELDS:
                    if len(bits) < nb or 'B' in bits[:nb]: break
                    words.append(int(''.join('1' if b == 'O' else '0' for b in bits[:nb]), 2)); bits = bits[nb:]
                if len(words) == len(sec0_trap.FIELDS):
                    d = sec0_trap.decode(words)
                    print('\nSECTION 0 REPORT:')
                    for k, v in d.items(): print(f'  {k:15s} {v:#x}' if isinstance(v, int) else f'  {k:15s} {v}')
                    print(json.dumps({k: v for k, v in d.items()}))
                    return
        print('\n(no complete section-0 report found)'); return
    for s0 in range(len(seq)):
        if seq[s0] == 'B' and lens[s0] >= 2 * unit:
            bits = seq[s0 + 1:]
            words = []
            for nb in (4, 8, 8, 32, 16, 32):
                if len(bits) < nb or 'B' in bits[:nb]: break
                words.append(int(''.join('1' if b == 'O' else '0' for b in bits[:nb]), 2)); bits = bits[nb:]
            if len(words) == 6:
                t, cp, asy, lr, fsr, far = words
                print(f'\nCRASH REPORT: {TYPES.get(t, t)} | last checkpoint {cp} | async aborts absorbed {asy} | '
                      f'lr {lr:#010x} | fault status {fsr:#06x} | fault address {far:#010x}')
                print(json.dumps(dict(type=t, checkpoint=cp, async_absorbed=asy, lr=lr, fsr=fsr, far=far)))
                return
    print('\n(no complete binary crash report found)')


if __name__ == '__main__':
    main()
