"""Classic Chrome v3 tuning values (2026-11-12): the 2x2 chroma matrix fitted to an X-T20 Classic Chrome JPEG.

(parameter ID, v2 bytes, v3 bytes), 13-bit signed, 0x400 = 1.0, little endian. Applied by the tuning hooks to
PRO Neg. Hi's 2x2 preset 5 (the borrowed look); the own look copies the same matrix into preset 12 (cc_look.py).
Also used by tools/build_cc3.py (flashable v3 candidate, not camera-tested).
"""
PARAMS3 = [
    (0xe3c9, 'd603', 'ae02'),   # 2x2 m00 (Cr gain)   0.959 → 0.670
    (0xe3cd, '2300', 'e11f'),   # 2x2 m01 (Cb → Cr)   0.034 → -0.030
    (0xe3cf, '1000', '2400'),   # 2x2 m10 (Cr → Cb)   0.016 → 0.035
    (0xe3cb, '4404', '0a04'),   # 2x2 m11 (Cb gain)   1.066 → 1.010
]
