# Classic Chrome v3 CANDIDATE for the X-Pro1: v2 + chroma matrix matched to an X-T20 + menu name "CLASSIC CHROME".
# usage: build_cc3.py <base FPUPDATE.DAT> <out/FPUPDATE.DAT> [--version 3.86] [--name "CLASSIC CHROME"] [--no-rename]
#   base = the flashed v2 file (re/build/ccswap_v2, sha 0df1cefe…) or the USB debug build made from it
#          (re/build/ptpdebug_385); the debug operations are kept if the base has them.
#
# Not camera-tested as a flashed build. The same values can be tried without flashing:
#   tune.py setmat cc2x2 0.67 -0.03 0.035 1.01   and   uiname.py set
#
# 1. Colour (2026-11-12). The 2x2 chroma matrix of the PRO Neg. Hi slot (preset 5, IDs 0xe3c9 m00, 0xe3cd m01,
#    0xe3cf m10, 0xe3cb m11) acts on [Cr, Cb] (m00 = Cr gain, m11 = Cb gain). v2 (ported from the X-E2):
#    [[0.959, 0.034], [0.016, 1.066]]. Against a genuine X-T20 Classic Chrome JPEG of the same scene (12 patches,
#    white balance and exposure normalised on the neutral ones, pipeline simulated on the X-Pro1 JPEG) the best
#    matrix is [[0.67, -0.03], [0.035, 1.01]]: mean Δab 2.1 → 0.7. In words: red-green chroma about 30 % lower,
#    blue-yellow chroma 5 % lower. The 3x3 matrix and the tone curve are unchanged (fitting the 3x3 as well gave no gain).
# 2. Name: uiname.patch_image() (three text descriptors per language block → new string in the block's free tail).
import hashlib, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', '..', 'public'))
import xpro1_cc_patch as P
import uiname

# (parameter ID, v2 bytes, v3 bytes): 13-bit signed, 0x400 = 1.0, little endian
PARAMS3 = [
    (0xe3c9, 'd603', 'ae02'),   # 2x2 m00 (Cr gain)   0.959 → 0.670
    (0xe3cd, '2300', 'e11f'),   # 2x2 m01 (Cb → Cr)   0.034 → -0.030
    (0xe3cf, '1000', '2400'),   # 2x2 m10 (Cr → Cb)   0.016 → 0.035
    (0xe3cb, '4404', '0a04'),   # 2x2 m11 (Cb gain)   1.066 → 1.010
]


def build(src, dst, version='3.86', name=uiname.NEW, rename=True):
    raw = open(src, 'rb').read()
    ok, length = P.check(raw); assert ok, 'container checksums of the base file'
    img = bytearray(x ^ 0xff for x in raw); base_img = bytes(img)
    unpacked, packed = struct.unpack('<II', img[P.BLOB1_HDR:P.BLOB1_HDR + 8])
    print('decompressing blob 1 ...')
    blob = bytearray(P.lz_decode(img, P.BLOB1_HDR + 20, P.BLOB1_HDR + packed, unpacked)); base_blob = bytes(blob)
    # the base must be v2: every v2 parameter and the Classic Chrome curve in place
    for pid, _, new in P.PARAMS:
        new = bytes.fromhex(new); a, m = P.TUNING + pid, P.MIRROR - P.BLOB1_BASE + pid
        assert img[a:a + len(new)] == new and blob[m:m + len(new)] == new, f'base is not Classic Chrome v2 (ID {pid:#06x})'
    c = P.CURVE_SLOT - P.BLOB1_BASE
    assert blob[c:c + 72] == bytes.fromhex(P.CURVE_NEW), 'base does not hold the Classic Chrome tone curve'
    for pid, old, new in PARAMS3:                                # both copies, as in v1/v2
        old, new = bytes.fromhex(old), bytes.fromhex(new); a, m = P.TUNING + pid, P.MIRROR - P.BLOB1_BASE + pid
        assert img[a:a + 2] == old and blob[m:m + 2] == old
        img[a:a + 2] = new; blob[m:m + 2] = new
    print('re-compressing blob 1 (about 10-30 s) ...')
    enc = P.lz_encode(bytes(blob)); total = len(enc) + 20
    assert total <= P.BLOB1_END - P.BLOB1_HDR, 'blob 1 does not fit its partition'
    img[P.BLOB1_HDR:P.BLOB1_END] = struct.pack('<5I', unpacked, total, -(-total // 0x4000), 0x4000, 4) + enc \
                                   + bytes(P.BLOB1_END - P.BLOB1_HDR - total)
    assert P.lz_decode(img, P.BLOB1_HDR + 20, P.BLOB1_HDR + total, unpacked) == bytes(blob), 'blob 1 round trip'
    if rename: print(f'renaming in {uiname.patch_image(img, name)} language blocks → {name!r}')

    # --- verification of the result as a whole
    ids = {pid + k for pid, _, _ in PARAMS3 for k in range(2)}
    lang = range(uiname.FILE0, uiname.FILE0 + uiname.NBLOCKS * uiname.BLOCK)
    for i in (i for i in range(len(img)) if img[i] != base_img[i]):
        assert P.BLOB1_HDR <= i < P.BLOB1_END or i - P.TUNING in ids or (rename and i in lang), f'unexpected change at {i:#x}'
    bdiff = {i - (P.MIRROR - P.BLOB1_BASE) for i in range(len(blob)) if blob[i] != base_blob[i]}
    assert bdiff <= ids, 'blob 1 changed outside the four matrix values'
    out = bytearray(x ^ 0xff for x in img)
    out[0x20c:0x210] = struct.pack('<I', P.payload_sum(out, length))
    major, minor = P.parse_version(version)
    out[0x204:0x20c] = struct.pack('<II', major, minor)
    assert P.check(out)[0], 'checksums'
    assert out[:0x204] == raw[:0x204] and out[0x210:0x25c] == raw[0x210:0x25c] and out[0x25c + length:] == raw[0x25c + length:]
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    open(dst, 'wb').write(out)
    s13 = lambda v: (v & 0x1fff) - (0x2000 if v & 0x1000 else 0)
    g = lambda pid: s13(struct.unpack('<H', img[P.TUNING + pid:P.TUNING + pid + 2])[0]) / 1024
    print(f'2x2 chroma matrix on [Cr, Cb]: [[{g(0xe3c9):.3f}, {g(0xe3cd):.3f}], [{g(0xe3cf):.3f}, {g(0xe3cb):.3f}]]')
    print(f'wrote {dst} labelled {version} (base: {os.path.basename(os.path.dirname(os.path.abspath(src)))}), '
          f'SHA-256 {hashlib.sha256(out).hexdigest()}')


if __name__ == '__main__':
    a = sys.argv[1:]; ver = '3.86'; name = uiname.NEW; rename = '--no-rename' not in a
    a = [x for x in a if x != '--no-rename']
    if '--version' in a: k = a.index('--version'); ver = a[k + 1]; del a[k:k + 2]
    if '--name' in a: k = a.index('--name'); name = a[k + 1]; del a[k:k + 2]
    if len(a) != 2: sys.exit(open(__file__).read().split('\nimport')[0])
    build(a[0], a[1], ver, name, rename)
