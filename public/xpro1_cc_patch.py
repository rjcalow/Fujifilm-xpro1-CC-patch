#!/usr/bin/env python3
"""
xpro1_cc_patch.py: add Classic Chrome to the Fujifilm X-Pro1 (firmware 3.82) by replacing PRO Neg. Hi.

Reads YOUR copy of the official X-Pro1 3.82 FPUPDATE.DAT and writes a patched FPUPDATE.DAT.
No Fujifilm firmware is distributed with this script; it only contains the small set of changed values.

    python3 xpro1_cc_patch.py FPUPDATE.DAT patched/FPUPDATE.DAT

Selecting PRO Neg. Hi on the camera then gives Classic Chrome. Menu, icon and EXIF still say "PRO Neg. Hi".
USE AT YOUR OWN RISK: flashing modified firmware can brick the camera. See README.md.
Python 3.8+, standard library only.
"""
import hashlib, struct, sys

STOCK_SHA256  = '709e26f6dd77e922660010628fb20937b269be871b188b8810eb2cb4d5d33236'  # X-Pro1 3.82 official
RESULT_SHA256 = 'fb0dc86b2f9e4fd49e8aa0714ee0d85d1a41118c29c10a51489b93778bb5ca3c'  # expected output (v1)

# File layout (offsets in the file; the payload at 0x25c.. is stored bit-inverted)
PAYLOAD      = 0x25c          # flash offset 0 (flash offset = file offset - 0x25c)
BLOB1_HDR    = 0x10025c       # method-4 compressed code image 1 (RAM 0x774000)
BLOB1_END    = 0x24025c       # end of its flash partition
BLOB1_BASE   = 0x774000
TUNING       = 0xae025c       # image-processing parameter area: value(ID) = byte at TUNING + ID
MIRROR       = 0x812470       # compiled copy of the parameter area inside blob 1 (RAM address)
CURVE_SLOT   = 0x80ba60       # tone-curve table entry of unused curve #40 (RAM address)

# (parameter ID, stock bytes, new bytes): written to the parameter area AND its copy in blob 1
PARAMS = [
    (0xdb4b, '5504', '8d05'),  # 3x3 sRGB (preset 5) m00
    (0xdb4d, '661f', 'c81e'),  # 3x3 sRGB (preset 5) m01
    (0xdb4f, '4500', 'ab1f'),  # 3x3 sRGB (preset 5) m02
    (0xdb51, '0400', 'dd1f'),  # 3x3 sRGB (preset 5) m10
    (0xdb53, '6304', '1104'),  # 3x3 sRGB (preset 5) m11
    (0xdb55, '991f', '1200'),  # 3x3 sRGB (preset 5) m12
    (0xdb57, '7700', '6b00'),  # 3x3 sRGB (preset 5) m20
    (0xdb59, '741f', '351f'),  # 3x3 sRGB (preset 5) m21
    (0xdb5b, '1504', '5f04'),  # 3x3 sRGB (preset 5) m22
    (0xdba5, '2c04', '8e04'),  # 3x3 alt (preset 10) m00 [approximate]
    (0xdba7, 'f91f', 'c700'),  # 3x3 alt (preset 10) m01 [approximate]
    (0xdba9, 'db1f', 'ab1e'),  # 3x3 alt (preset 10) m02 [approximate]
    (0xdbab, 'ca1f', '0d00'),  # 3x3 alt (preset 10) m10 [approximate]
    (0xdbad, '9704', '3c04'),  # 3x3 alt (preset 10) m11 [approximate]
    (0xdbaf, '9f1f', 'b71f'),  # 3x3 alt (preset 10) m12 [approximate]
    (0xdbb1, '5d00', '8600'),  # 3x3 alt (preset 10) m20 [approximate]
    (0xdbb3, 'a01f', '1a1f'),  # 3x3 alt (preset 10) m21 [approximate]
    (0xdbb5, '0304', '6104'),  # 3x3 alt (preset 10) m22 [approximate]
    (0xe3c9, '2606', 'd603'),  # 2x2 chroma (preset 5) m00
    (0xe3cb, '2007', '4404'),  # 2x2 chroma (preset 5) m11
    (0xe3cd, 'b01f', '2300'),  # 2x2 chroma (preset 5) m01
    (0xe3cf, 'd000', '1000'),  # 2x2 chroma (preset 5) m10
    (0xffc6, '03', '01'),  # detail preset NegHi -> PROVIA value (1)
    (0xe13b, '02', '01'),  # H/S tone family plane0 NegHi -> PROVIA value (1)
    (0xde13, '16', '26'),  # NegHi tone curve number 22 -> 38
    (0xde14, '16', '26'),  # NegHi tone curve number 22 -> 38
    (0xde15, '16', '26'),  # NegHi tone curve number 22 -> 38
    (0xde16, '17', '26'),  # NegHi tone curve number 23 -> 38
    (0xde17, '17', '26'),  # NegHi tone curve number 23 -> 38
    (0xde18, '17', '26'),  # NegHi tone curve number 23 -> 38
    (0xde19, '18', '26'),  # NegHi tone curve number 24 -> 38
    (0xde1a, '18', '26'),  # NegHi tone curve number 24 -> 38
    (0xde1b, '18', '26'),  # NegHi tone curve number 24 -> 38
    (0xde1c, '19', '26'),  # NegHi tone curve number 25 -> 38
    (0xde1d, '19', '26'),  # NegHi tone curve number 25 -> 38
    (0xde1e, '19', '26'),  # NegHi tone curve number 25 -> 38
    (0xde1f, '1a', '26'),  # NegHi tone curve number 26 -> 38
    (0xde20, '1a', '26'),  # NegHi tone curve number 26 -> 38
    (0xde21, '1a', '26'),  # NegHi tone curve number 26 -> 38
    (0xde22, '1b', '26'),  # NegHi tone curve number 27 -> 38
    (0xde23, '1b', '26'),  # NegHi tone curve number 27 -> 38
    (0xde24, '1b', '26'),  # NegHi tone curve number 27 -> 38
    (0xde91, '16', '26'),  # NegHi tone curve number 22 -> 38
    (0xde92, '16', '26'),  # NegHi tone curve number 22 -> 38
    (0xde93, '16', '26'),  # NegHi tone curve number 22 -> 38
    (0xde94, '17', '26'),  # NegHi tone curve number 23 -> 38
    (0xde95, '17', '26'),  # NegHi tone curve number 23 -> 38
    (0xde96, '17', '26'),  # NegHi tone curve number 23 -> 38
    (0xde97, '18', '26'),  # NegHi tone curve number 24 -> 38
    (0xde98, '18', '26'),  # NegHi tone curve number 24 -> 38
    (0xde99, '18', '26'),  # NegHi tone curve number 24 -> 38
    (0xde9a, '19', '26'),  # NegHi tone curve number 25 -> 38
    (0xde9b, '19', '26'),  # NegHi tone curve number 25 -> 38
    (0xde9c, '19', '26'),  # NegHi tone curve number 25 -> 38
    (0xde9d, '1a', '26'),  # NegHi tone curve number 26 -> 38
    (0xde9e, '1a', '26'),  # NegHi tone curve number 26 -> 38
    (0xde9f, '1a', '26'),  # NegHi tone curve number 26 -> 38
    (0xdea0, '1b', '26'),  # NegHi tone curve number 27 -> 38
    (0xdea1, '1b', '26'),  # NegHi tone curve number 27 -> 38
    (0xdea2, '1b', '26'),  # NegHi tone curve number 27 -> 38
    (0xdf91, '1b', '26'),  # NegHi tone curve number 27 -> 38
    (0xdf98, '1b', '26'),  # NegHi tone curve number 27 -> 38
    (0xdf9f, '1b', '26'),  # NegHi tone curve number 27 -> 38
    (0xdfad, '1b', '26')  # NegHi tone curve number 27 -> 38
]
# X-E2 Classic Chrome tone curve #38: u32 number, 9-byte segment header, pad, 28 x u16 knots (14-bit)
CURVE_OLD_FIRST4 = '28000000'   # slot currently holds curve #40 (unreferenced by any X-Pro1 film simulation)
CURVE_NEW = '260000000202030405050506060000008600530153025103650476059c07cf09f20b761047148517031eef22b1266f2afb2c352f77311033963485378a39733b1b3dc23eff3f0000'

# ---------------------------------------------------------------- method-4 LZ (Fujifilm)
# Header: u32 unpacked, u32 packed (incl. header), u32 pages=ceil(packed/0x4000), u32 0x4000, u32 4.
# Tokens: 0nnnnnnn = n literal bytes (1..127); 1ddddddd ddddllll = copy l (1..15) from distance d (1..2047).
def lz_decode(buf, pos, end, size):
    out = bytearray()
    while pos < end and len(out) < size:
        b = buf[pos]
        if b & 0x80:
            t = (b << 8) | buf[pos + 1]; pos += 2
            d, l = (t & 0x7ff0) >> 4, t & 0xf
            if not (0 < d <= len(out) and l): raise ValueError('bad match token')
            for _ in range(l): out.append(out[-d])
        else:
            if b == 0: raise ValueError('zero literal')
            out += buf[pos + 1:pos + 1 + b]; pos += 1 + b
    if len(out) != size: raise ValueError('size mismatch')
    return bytes(out)

def lz_encode(data, header_len=20, page=0x4000):
    """Greedy encoder. Like Fujifilm's own encoder, no token crosses a 16 KiB page boundary
    (counted from the blob header) and every page boundary is hit exactly."""
    toks = []; i = 0; n = len(data); idx = {}; lit = None
    while i < n:
        bl = bd = 0
        if i + 3 <= n:
            for j in reversed(idx.get(data[i:i + 3], [])[-32:]):
                d = i - j
                if d > 2047: break
                l = 0
                while l < 15 and i + l < n and data[j + l] == data[i + l]: l += 1
                if l > bl: bl, bd = l, d
                if l == 15: break
        if bl >= 3:
            if lit is not None: toks.append(['L', lit, i - lit]); lit = None
            toks.append(['M', i, bl, bd])
            for k in range(bl):
                if i + k + 3 <= n: idx.setdefault(data[i + k:i + k + 3], []).append(i + k)
            i += bl
        else:
            if i + 3 <= n: idx.setdefault(data[i:i + 3], []).append(i)
            if lit is None: lit = i
            i += 1
    if lit is not None: toks.append(['L', lit, n - lit])
    out = bytearray(); ti = 0
    def take(k):
        nonlocal ti
        got = bytearray()
        while k and ti < len(toks):
            t = toks[ti]; u = min(k, t[2]); got += data[t[1]:t[1] + u]
            t[1] += u; t[2] -= u; k -= u
            if t[2] == 0: ti += 1
        return got
    while ti < len(toks):
        t = toks[ti]; r = page - ((header_len + len(out)) % page)
        if r == 3:
            lits = take(2); out.append(len(lits)); out += lits; continue
        if t[0] == 'M':
            out += bytes([0x80 | (t[3] >> 4), ((t[3] & 0xf) << 4) | t[2]]); ti += 1; continue
        k = min(t[2], 127, r - 1)
        if r - (1 + k) == 1: k -= 1
        lits = take(k); out.append(k); out += lits
    return bytes(out)

# ---------------------------------------------------------------- container checksums (type-4 header)
def payload_sum(raw, length):        # u32 @0x20c = ~sum(bit-inverted payload bytes)
    return (~sum(255 - x for x in raw[PAYLOAD:PAYLOAD + length])) & 0xffffffff

def check(raw):
    length = struct.unpack('<I', raw[0x240:0x244])[0]
    tlen, tsum = struct.unpack('<II', raw[0x248:0x250])
    t0 = PAYLOAD + length
    ok_p = struct.unpack('<I', raw[0x20c:0x210])[0] == payload_sum(raw, length)
    ok_t = tsum == (~sum(raw[t0:t0 + tlen])) & 0xffffffff
    return ok_p and ok_t and t0 + tlen == len(raw), length

# ---------------------------------------------------------------- main
def main(src, dst):
    raw = open(src, 'rb').read()
    if hashlib.sha256(raw).hexdigest() != STOCK_SHA256:
        sys.exit('Input is not the official X-Pro1 3.82 FPUPDATE.DAT (SHA-256 mismatch). Nothing written.')
    ok, length = check(raw)
    if not ok: sys.exit('Container checksum check failed on the stock file. Nothing written.')
    img = bytearray(x ^ 0xff for x in raw)                       # decoded (bit-inverted back) view

    unpacked, packed = struct.unpack('<II', img[BLOB1_HDR:BLOB1_HDR + 8])
    print('decompressing blob 1 ...')
    blob = bytearray(lz_decode(img, BLOB1_HDR + 20, BLOB1_HDR + packed, unpacked))

    for pid, old, new in PARAMS:                                # tuning values, both copies
        old, new = bytes.fromhex(old), bytes.fromhex(new)
        a, m = TUNING + pid, MIRROR - BLOB1_BASE + pid
        if img[a:a + len(old)] != old or blob[m:m + len(old)] != old:
            sys.exit(f'Unexpected stock value at parameter {pid:#06x}. Nothing written.')
        img[a:a + len(new)] = new; blob[m:m + len(new)] = new

    c = CURVE_SLOT - BLOB1_BASE                                 # tone curve
    if blob[c:c + 4].hex() != CURVE_OLD_FIRST4:
        sys.exit('Unexpected tone-curve table layout. Nothing written.')
    blob[c:c + 72] = bytes.fromhex(CURVE_NEW)

    print('re-compressing blob 1 (about 10-30 s) ...')
    enc = lz_encode(bytes(blob)); total = len(enc) + 20
    if total > BLOB1_END - BLOB1_HDR: sys.exit('Compressed blob 1 does not fit its partition. Nothing written.')
    img[BLOB1_HDR:BLOB1_END] = struct.pack('<5I', unpacked, total, -(-total // 0x4000), 0x4000, 4) + enc \
                               + bytes(BLOB1_END - BLOB1_HDR - total)
    if lz_decode(img, BLOB1_HDR + 20, BLOB1_HDR + total, unpacked) != bytes(blob):
        sys.exit('Self-check failed: re-compressed blob 1 does not decode back. Nothing written.')

    out = bytearray(x ^ 0xff for x in img)
    out[0x20c:0x210] = struct.pack('<I', payload_sum(out, length))
    if not check(out)[0]: sys.exit('Self-check failed: checksums. Nothing written.')
    digest = hashlib.sha256(out).hexdigest()
    if digest != RESULT_SHA256:
        sys.exit(f'Self-check failed: output SHA-256 {digest} is not the tested build. Nothing written.')
    open(dst, 'wb').write(out)
    print(f'wrote {dst}\nSHA-256 {digest} (matches the build tested on a camera)')

if __name__ == '__main__':
    if len(sys.argv) != 3: sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
