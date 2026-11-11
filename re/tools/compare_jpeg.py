# Pixel-aligned comparison of two in-camera conversions of the same RAW (CIELAB, D65).
# usage: compare_jpeg.py <reference.jpg> <test.jpg> [more test.jpg ...]
# Prints mean |ΔL*|, chroma ratio test/ref (median, p10, p90) over pixels with ref C* > 10, the same for red hues
# (h 0-60° and 330-360°), and the median hue shift. Images are downsampled 4× to average out JPEG noise.
import sys
import numpy as np
from PIL import Image


def lab(path):
    a = np.asarray(Image.open(path).convert('RGB'), dtype=np.float64) / 255.0
    h, w, _ = a.shape; a = a[:h // 4 * 4, :w // 4 * 4].reshape(h // 4, 4, w // 4, 4, 3).mean(axis=(1, 3))
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16; A = 500 * (f[..., 0] - f[..., 1]); B = 200 * (f[..., 1] - f[..., 2])
    return L, np.hypot(A, B), np.degrees(np.arctan2(B, A)) % 360


def stats(ref, test):
    (L0, C0, H0), (L1, C1, H1) = ref, test
    out = {'dL': float(np.mean(np.abs(L1 - L0)))}
    for name, m in (('all', C0 > 10), ('red', (C0 > 10) & ((H0 < 60) | (H0 > 330)))):
        r = C1[m] / C0[m]
        dh = (H1[m] - H0[m] + 180) % 360 - 180
        out[name] = (int(m.sum()), *np.percentile(r, [50, 10, 90]), float(np.median(dh)), float(C0[m].max()), float(C1[m].max()))
    return out


if __name__ == '__main__':
    ref = lab(sys.argv[1])
    for t in sys.argv[2:]:
        s = stats(ref, lab(t))
        print(f'{t} vs {sys.argv[1]}: mean |ΔL*| {s["dL"]:.2f}')
        for k in ('all', 'red'):
            n, med, p10, p90, dh, cmax0, cmax1 = s[k]
            print(f'  {k:3s} ({n} px): chroma ratio median ×{med:.3f} (p10 {p10:.3f}, p90 {p90:.3f}), hue shift {dh:+.2f}°,'
                  f' max C* {cmax0:.1f} → {cmax1:.1f}')
