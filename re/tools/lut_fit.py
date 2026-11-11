# Fit a 3D .cube LUT with what the X-Pro1 pipeline can do: one tone curve (same for R, G, B) after a 3x3 matrix in
# linear light. Reports how much of the LUT that model reproduces (CIELAB ΔE76 against the real LUT).
# usage: lut_fit.py LUT.cube [...]
# Model: out_srgb = curve( srgb_encode( M · srgb_decode(in) ) ), curve from the LUT's neutral axis, M least squares.
import sys
import numpy as np


def load_cube(path):
    n = None; rows = []
    for line in open(path):
        t = line.split()
        if not t or t[0].startswith('#'): continue
        if t[0] == 'LUT_3D_SIZE': n = int(t[1]); continue
        try: rows.append([float(x) for x in t[:3]])
        except ValueError: continue
    a = np.array(rows); assert n and len(a) == n ** 3, (path, n, len(a))
    return n, a.reshape(n, n, n, 3)            # [b][g][r] (red varies fastest in .cube)


def dec(v): v = np.clip(v, 0, 1); return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)
def enc(v): v = np.clip(v, 0, 1); return np.where(v <= 0.0031308, v * 12.92, 1.055 * v ** (1 / 2.4) - 0.055)


def lab(srgb):
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = dec(srgb) @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def fit(path):
    n, L = load_cube(path)
    g = np.linspace(0, 1, n)
    B, G, R = np.meshgrid(g, g, g, indexing='ij'); inp = np.stack([R, G, B], -1)
    out = L
    # tone curve: neutral axis, mean of the three output channels, made monotonic
    neutral = np.array([out[i, i, i].mean() for i in range(n)])
    curve = np.maximum.accumulate(neutral)
    cfun = lambda x: np.interp(x, g, curve)
    cinv = lambda y: np.interp(y, curve + np.arange(n) * 1e-9, g)
    # matrix: in linear light, target = linear value that the curve maps onto the LUT output
    X = dec(inp).reshape(-1, 3); Y = dec(cinv(out)).reshape(-1, 3)
    w = (lab(inp).reshape(-1, 3)[:, 1:] ** 2).sum(1) < 60 ** 2          # fit on everyday colours (C* < 60)
    M, *_ = np.linalg.lstsq(X[w], Y[w], rcond=None); M = M.T
    model = cfun(enc(X @ M.T)).reshape(out.shape)
    curve_only = cfun(inp)
    res = {}
    for name, pred in (('do nothing', inp), ('tone curve only', curve_only), ('curve + 3x3', model)):
        d = np.linalg.norm(lab(pred) - lab(out), axis=-1).reshape(-1)
        res[name] = (np.median(d[w]), np.percentile(d[w], 90), np.median(d))
    return n, M, curve, res


if __name__ == '__main__':
    for p in sys.argv[1:]:
        n, M, curve, res = fit(p)
        print(f'== {p} ({n}^3)')
        print('   fit M (linear light):\n' + '\n'.join('     ' + ' '.join(f'{v:+.4f}' for v in row) for row in M))
        print('   tone curve (neutral in → out, 0..1):', ' '.join(f'{v:.3f}' for v in curve[::4]))
        for k, (med, p90, all_med) in res.items():
            print(f'   ΔE76 {k:16s}: everyday colours median {med:5.2f}, p90 {p90:5.2f}; whole cube median {all_med:5.2f}')


# ---------------------------------------------------------------------------------------------------------------
# Camera-domain fit (used by tune.py lut). The X-Pro1 renders: display = curve( M · x ), x = camera-linear RGB,
# M = 3x3 colour matrix (13-bit, ×1024), curve = 27 knots on 0..16384 linear input → 0..16383 output; knot k sits at
# the end of thirds of 9 segments of length 2^(seg+6) (seg = 2 2 3 4 5 5 5 6 6; verified: curve #39 is the identity).
# Reference = PROVIA (matrix preset 1, curve #0). Target = LUT(PROVIA output). Fit a new matrix and curve so that
# curve_new(M_new · x) ≈ target over camera-linear inputs.
SEG = [2, 2, 3, 4, 5, 5, 5, 6, 6]


def knot_x(seg=SEG):
    x = []; s = 0
    for e in seg:
        L = 2 ** (e + 6); x += [s + L * k / 3 for k in (1, 2, 3)]; s += L
    return np.array(x)                                   # 27 positions, last = 16384


def curve_eval(knots, lin):
    """knots: 27 values 0..16383 at knot_x(); lin: 0..1 linear → display 0..1 (piecewise linear, from (0, 0))."""
    xs = np.concatenate([[0.0], knot_x() / 16384]); ys = np.concatenate([[0.0], np.asarray(knots, float) / 16383])
    return np.interp(np.clip(lin, 0, 1), xs, ys)


def trilinear(L, v):
    n = L.shape[0]; p = np.clip(v, 0, 1) * (n - 1)
    i0 = np.minimum(p.astype(int), n - 2); f = p - i0
    r, g, b = i0[..., 0], i0[..., 1], i0[..., 2]; fr, fg, fb = f[..., 0:1], f[..., 1:2], f[..., 2:3]
    out = 0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = (fr if dr else 1 - fr) * (fg if dg else 1 - fg) * (fb if db else 1 - fb)
                out = out + w * L[b + db, g + dg, r + dr]
    return out


def camera_fit(lut_path, M_ref, knots_ref, n=21):
    _, L = load_cube(lut_path)
    g = np.linspace(0, 1, n); B_, G_, R_ = np.meshgrid(g, g, g, indexing='ij')
    x = np.stack([R_, G_, B_], -1).reshape(-1, 3) ** 2.2          # camera-linear samples, denser in the shadows
    ref = curve_eval(knots_ref, x @ M_ref.T)                     # PROVIA rendering (display 0..1)
    tgt = trilinear(L, ref)                                      # what the LUT makes of it
    w = (lab(ref)[:, 1:] ** 2).sum(1) < 60 ** 2                  # everyday colours
    # tone curve from the neutral axis: camera-neutral input s(1,1,1) → mean target channel
    s = np.linspace(0, 1, 513)
    neutral = trilinear(L, curve_eval(knots_ref, np.outer(s, M_ref.sum(1))))
    tone = np.maximum.accumulate(neutral.mean(1))
    M = M_ref.copy()
    for _ in range(3):                                           # alternate: matrix (LS in curve-inverse domain), curve
        inv = lambda y: np.interp(y, tone + np.arange(len(s)) * 1e-9, s)
        Y = inv(tgt); X = x
        M = np.linalg.lstsq(X[w], Y[w], rcond=None)[0].T
        lin_n = np.outer(s, M.sum(1)).mean(1)                    # neutral input through the new matrix
        tone = np.maximum.accumulate(np.interp(s, np.maximum.accumulate(lin_n) + np.arange(len(s)) * 1e-12, neutral.mean(1)))
    knots = np.clip(np.round(np.interp(knot_x() / 16384, s, tone) * 16383), 0, 16383)
    knots = np.maximum.accumulate(knots).astype(int); knots[-1] = 16383
    model = curve_eval(knots, x @ M.T)
    dE = lambda a, b: np.linalg.norm(lab(a) - lab(b), axis=-1)
    stats = {'do nothing (PROVIA)': dE(ref, tgt), 'fitted camera settings': dE(model, tgt)}
    return M, knots, {k: (float(np.median(v[w])), float(np.percentile(v[w], 90))) for k, v in stats.items()}


def camera_fit_opt(lut_path, M_ref, knots_ref, n=17):
    """Joint least-squares refinement of camera_fit: 9 matrix entries + 27 knot increments, residual = CIELAB error
    against the LUT target over everyday colours, plus a strong penalty on grey drifting off neutral."""
    from scipy.optimize import least_squares
    M0, k0, _ = camera_fit(lut_path, M_ref, knots_ref, n=21)
    _, L = load_cube(lut_path)
    g = np.linspace(0, 1, n); B_, G_, R_ = np.meshgrid(g, g, g, indexing='ij')
    x = np.stack([R_, G_, B_], -1).reshape(-1, 3) ** 2.2
    ref = curve_eval(knots_ref, x @ M_ref.T); tgt = trilinear(L, ref)
    w = (lab(ref)[:, 1:] ** 2).sum(1) < 60 ** 2
    xs, T = x[w], lab(tgt[w])
    s = np.linspace(0.002, 1, 64); xn = np.outer(s, np.ones(3))
    Tn = lab(trilinear(L, curve_eval(knots_ref, xn @ M_ref.T)))
    def unpack(p):
        M = p[:9].reshape(3, 3); kn = np.minimum(np.cumsum(np.abs(p[9:])), 16383); return M, kn
    def resid(p):
        M, kn = unpack(p)
        r1 = (lab(curve_eval(kn, xs @ M.T)) - T).reshape(-1)
        r2 = 3 * (lab(curve_eval(kn, xn @ M.T)) - Tn).reshape(-1)     # neutrals weighted ×3
        return np.concatenate([r1, r2])
    p0 = np.concatenate([M0.reshape(-1), np.diff(np.concatenate([[0], k0])).astype(float)])
    sol = least_squares(resid, p0, method='trf', max_nfev=2000, x_scale='jac')
    M, kn = unpack(sol.x)
    kn = np.clip(np.round(kn), 0, 16383).astype(int)
    model = curve_eval(kn, x @ M.T)
    dE = lambda a, b: np.linalg.norm(lab(a) - lab(b), axis=-1)
    grey = dE(curve_eval(kn, xn @ M.T), trilinear(L, curve_eval(knots_ref, xn @ M_ref.T)))
    stats = {'do nothing (PROVIA)': dE(ref, tgt), 'fitted camera settings': dE(model, tgt)}
    out = {k: (float(np.median(v[w])), float(np.percentile(v[w], 90))) for k, v in stats.items()}
    out['greys (fitted)'] = (float(np.median(grey)), float(np.percentile(grey, 90)))
    return M, kn, out
