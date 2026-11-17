"""ACROS-style tone curves for the X-Pro1, derived from the X-Pro2 firmware (FINDINGS.md §10).

On the X-Pro2 the base tone curve is chosen per colour mode: PROVIA, MONO and SEPIA use curve 1, ACROS (all four
filter variants) uses curve 7 (blob2 0x13f094c via tables 0x17b0a9c / 0x17b0eb4, blend weight 128 = one curve).
Curves on both cameras share one input grid (segment header 02 02 03 04 05 05 05 06 06, 27 knots, 14-bit), but the
X-Pro2's PROVIA curve differs from the X-Pro1's (other sensor). So ACROS is ported as a change relative to PROVIA:

    acros_x1 = A2 ∘ P2⁻¹ ∘ c_x1      (A2 = X-Pro2 curve 7, P2 = X-Pro2 curve 1, c_x1 = the X-Pro1 curve MONO uses)

i.e. every output level the X-Pro1 curve produces is moved where ACROS moves the same PROVIA level on the X-Pro2.
Piecewise-linear in knot index (exact for the firmware's piecewise-linear curves, same grid on both).
usage: python3 acros_curves.py X-PRO1-FPUPDATE.DAT X-PRO2-FWUP0008.DAT   (prints the curves)
"""
import struct

X1_TAB, X1_CNT, X1_BASE = 0x80b700, 29, 0x774000      # X-Pro1 blob1 curve table
X2_TAB, X2_CNT, X2_BASE = 0xe27970, 48, 0xa51000      # X-Pro2 blob1 curve table
X2_PROVIA, X2_ACROS = 1, 7
MONO_CURVES = (0, 14, 16)                             # X-Pro1 curves MONO's base tone uses (FUN_00f321f0, family 6)
N = 27


def entry(blob, base, tab, cnt, num):
    for i in range(cnt):
        e = blob[tab - base + 0x48 * i: tab - base + 0x48 * (i + 1)]
        if struct.unpack_from('<I', e)[0] == num: return e
    raise KeyError(num)


def knots(e): return list(struct.unpack_from('<28H', e, 0x10))[:N]


def inverse(curve, v):
    """Fractional knot index t with curve(t) = v (curve increasing; clamps at the ends)."""
    if v <= curve[0]: return 0.0
    for i in range(N - 1):
        a, b = curve[i], curve[i + 1]
        if a <= v <= b: return i + (0.0 if b == a else (v - a) / (b - a))
    return float(N - 1)


def at(curve, t):
    i = min(int(t), N - 2); f = t - i
    return curve[i] + f * (curve[i + 1] - curve[i])


def port(c_x1, p2, a2):
    out = [min(16383, max(0, round(at(a2, inverse(p2, v))))) for v in c_x1]
    for i in range(1, N): out[i] = max(out[i], out[i - 1])        # keep it monotonic
    return out


def curves(x1_blob1, x2_blob1):
    """{X-Pro1 curve number: (original 0x48-byte entry, ACROS knots)} for the curves MONO uses."""
    p2 = knots(entry(x2_blob1, X2_BASE, X2_TAB, X2_CNT, X2_PROVIA))
    a2 = knots(entry(x2_blob1, X2_BASE, X2_TAB, X2_CNT, X2_ACROS))
    out = {}
    for n in MONO_CURVES:
        e = entry(x1_blob1, X1_BASE, X1_TAB, X1_CNT, n)
        out[n] = (e, port(knots(e), p2, a2))
    return out


if __name__ == '__main__':
    import sys
    sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__file__), '..', '..', '..', 'public'))
    import xpro1_cc_patch as P
    def blob1(path, hdr):
        img = bytes(x ^ 0xff for x in open(path, 'rb').read()); size, packed = struct.unpack_from('<II', img, hdr)
        return P.lz_decode(img, hdr + 20, hdr + packed, size)
    x1, x2 = blob1(sys.argv[1], 0x10025c), blob1(sys.argv[2], 0x23025c)
    p2 = knots(entry(x2, X2_BASE, X2_TAB, X2_CNT, X2_PROVIA)); a2 = knots(entry(x2, X2_BASE, X2_TAB, X2_CNT, X2_ACROS))
    print('X-Pro2 PROVIA #1 ', ' '.join(f'{v:5}' for v in p2)); print('X-Pro2 ACROS  #7 ', ' '.join(f'{v:5}' for v in a2))
    for n, (e, k) in curves(x1, x2).items():
        print(f'X-Pro1 #{n:<2}       ', ' '.join(f'{v:5}' for v in knots(e)))
        print(f'  → ACROS-style   ', ' '.join(f'{v:5}' for v in k))
