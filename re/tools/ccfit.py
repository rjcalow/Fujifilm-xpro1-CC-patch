"""Which 2x2 chroma matrix produced a Classic Chrome-slot JPEG? Uses two in-camera conversions of the SAME RAW.
usage: ccfit.py PROVIA.JPG CC.JPG [more CC.JPG ...]          (run with ~/.venvs/xpro1-re/bin/python)

Model of the X-Pro1 pipeline (NOTES 2026-11-12): linear camera RGB → 3x3 matrix → tone curve (per channel) →
Y'CbCr (BT.601) → 2x2 chroma matrix on [Cr, Cb]. The PROVIA JPEG is inverted through PROVIA's matrix, curve #0 and
2x2, then rendered with the PRO Neg. Hi slot's 3x3 + Classic Chrome curve #38 and a candidate 2x2. Prints the
prediction error for the known value sets (v2 flashed, v3 candidate) and the best-fitting 2x2.
Checked on DSCF2761 (PROVIA) / DSCF2759 (CC slot, SD boot with the first --cc card): best fit
[[0.948, 0.035], [0.028, 1.064]] = the v2 values (median Δab 0.54) → the start-up tuning load was not hooked yet.
Assumes Colour 0, Highlight / Shadow 0 and the same white balance in both conversions.
"""
import os, struct, sys
import numpy as np
from PIL import Image
from scipy.optimize import least_squares
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'public'))
import xpro1_cc_patch as P

STOCK = os.path.join(ROOT, 'FPUPDATE.DAT'); BLOB1 = os.path.join(ROOT, 're', 'work', 'blob1.bin')
def s13(v): v &= 0x1fff; return v - 0x2000 if v & 0x1000 else v
db = bytearray(255 - x for x in open(STOCK, 'rb').read()[P.TUNING:P.TUNING + 0x10000])
for pid, _, new in P.PARAMS: db[pid:pid + len(bytes.fromhex(new))] = bytes.fromhex(new)      # v2 = flashed
g = lambda i: s13(struct.unpack('<H', db[i:i + 2])[0]) / 1024
m3 = lambda b: np.array([g(b + 2 * k) for k in range(9)]).reshape(3, 3)
m2 = lambda b: np.array([[g(b), g(b + 4)], [g(b + 6), g(b + 2)]])               # storage m00 m11 m01 m10
MP, NP, MC, NC = m3(0xdb03), m2(0xe3a9), m3(0xdb4b), m2(0xe3c9)
b1 = open(BLOB1, 'rb').read()
K0 = np.array(struct.unpack('<27H', b1[0x80b700 - 0x774000 + 16:][:54]), float)            # PROVIA curve #0
K38 = np.array(struct.unpack('<27H', bytes.fromhex(P.CURVE_NEW)[16:70]), float)            # Classic Chrome #38
V3 = np.array([[0.670, -0.030], [0.035, 1.010]])
SEG = [2, 2, 3, 4, 5, 5, 5, 6, 6]
XS = np.concatenate([[0.0], np.array([sum(2 ** (e + 6) for e in SEG[:j]) + 2 ** (SEG[j] + 6) * k / 3
                                      for j in range(9) for k in (1, 2, 3)]) / 16384])
curve = lambda k, x: np.interp(np.clip(x, 0, 1), XS, np.concatenate([[0.0], k / 16383]))
icurve = lambda k, y: np.interp(np.clip(y, 0, 1), np.concatenate([[0.0], k / 16383]) + np.arange(28) * 1e-9, XS)
def ycc(rgb):
    y = 0.299 * rgb[:, 0] + 0.587 * rgb[:, 1] + 0.114 * rgb[:, 2]
    return y, np.stack([(rgb[:, 0] - y) / 1.402, (rgb[:, 2] - y) / 1.772], -1)            # [Cr, Cb]
def rgb_(y, c):
    r = y + 1.402 * c[:, 0]; b = y + 1.772 * c[:, 1]; return np.stack([r, (y - 0.299 * r - 0.114 * b) / 0.587, b], -1)
def lab(a):
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    xyz = lin @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T / [0.95047, 1, 1.08883]
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], -1)
def load(p): return np.asarray(Image.open(p).convert('RGB').reduce(8), float).reshape(-1, 3) / 255
def predict(provia, N):
    y, c = ycc(provia); x = icurve(K0, rgb_(y, c @ np.linalg.inv(NP).T)) @ (MC @ np.linalg.inv(MP)).T
    y, c = ycc(curve(K38, x)); return np.clip(rgb_(y, c @ N.T), 0, 1)

if __name__ == '__main__':
    if len(sys.argv) < 3: sys.exit(__doc__)
    A = load(sys.argv[1]); LA = lab(A)
    mask = (LA[:, 0] > 8) & (LA[:, 0] < 92) & (np.hypot(LA[:, 1], LA[:, 2]) > 4); idx = np.where(mask)[0][::3]
    for path in sys.argv[2:]:
        LB = lab(load(path)); print(f'{os.path.basename(path)} (reference {os.path.basename(sys.argv[1])}):')
        d = lambda N, sel=mask: np.median(np.hypot(*(lab(predict(A[sel], N)) - LB[sel])[:, 1:].T))
        for nm, N in (('v2 (flashed)', NC), ('v3 candidate', V3)): print(f'  {nm:14s} median Δab {d(N):.2f}')
        s = least_squares(lambda p: (lab(predict(A[idx], p.reshape(2, 2))) - LB[idx])[:, 1:].ravel(), NC.ravel())
        F = s.x.reshape(2, 2); near = 'v2' if np.abs(F - NC).sum() < np.abs(F - V3).sum() else 'v3'
        print(f'  best fit [[{F[0,0]:.3f}, {F[0,1]:.3f}], [{F[1,0]:.3f}, {F[1,1]:.3f}]]  median Δab {d(F):.2f}  → closest to {near}')
