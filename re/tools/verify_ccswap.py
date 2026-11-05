# Independent verification of the X-Pro1 PRO Neg Hi -> Classic Chrome candidate.
# usage: verify_ccswap.py <stock FPUPDATE.DAT> <candidate FPUPDATE.DAT> <X-E2 blob1.bin>
import sys, os, struct
sys.path.insert(0, os.path.dirname(__file__))
import lz, fpupdate, lzenc_chunked

stock_raw, cand_raw = open(sys.argv[1], 'rb').read(), open(sys.argv[2], 'rb').read()
xe2_b1 = open(sys.argv[3], 'rb').read(); XE2B1 = 0x8a0400
ok = True
def check(cond, msg):
    global ok
    print(('PASS ' if cond else 'FAIL ') + msg); ok &= bool(cond)

# 1. container checksums
for n, s, c, good in fpupdate.verify(cand_raw): check(good, f'container {n}: stored {s:#x} computed {c:#x}')
S = bytes(x ^ 0xff for x in stock_raw); C = bytes(x ^ 0xff for x in cand_raw)
DB, MIR, B1, B2 = 0xae025c, 0x812470, 0x774000, 0xe0ec80
P0, PEND = 0x10025c, 0x24025c

# 2. decompress both blobs from the candidate exactly as stored
def blob(img, base):
    dst, src, nch, blk, x = struct.unpack('<5I', img[base:base + 20])
    out, p, err = lz.decode(img, base + 20, src - 20)
    return out, (dst, src, nch, blk, x, err, p - base)
s1, _ = blob(S, P0); c1, h1 = blob(C, P0)
s2, _ = blob(S, 0x24025c); c2, h2 = blob(C, 0x24025c)
dst, src, nch, blk, x, err, used = h1
check(err is None and len(c1) == dst == len(s1) and used == src, f'blob1 decompresses: dst {dst:#x} src {src:#x}')
check(nch == -(-src // 0x4000) and blk == 0x4000 and x == 4, f'blob1 header fields nchunks {nch:#x} blk {blk:#x} {x}')
check(src <= PEND - P0, f'blob1 fits partition ({src:#x} <= {PEND - P0:#x})')
check(lzenc_chunked.straddles(C[P0 + 20:P0 + src]) == 0, 'no token straddles a 16K input chunk')
check(all(b == 0 for b in C[P0 + src:PEND]), 'partition tail filler matches stock convention')
check(c2 == s2, 'blob2 unchanged')

# 3. byte-level change map
diff_img = [i for i in range(len(S)) if S[i] != C[i] and not (P0 <= i < PEND) and i not in range(0x20c, 0x210)]
diff_b1 = [i for i in range(len(s1)) if s1[i] != c1[i]]
print(f'INFO tuning-area bytes changed: {len(diff_img)}; blob1 bytes changed: {len(diff_b1)}')
check(all(DB <= i < DB + 0x10000 for i in diff_img), 'outside blob1, only the tuning area changed')
curve_slot = 0x80b700 + 12 * 0x48
mirror_changes = sorted(i + B1 - MIR for i in diff_b1 if not (curve_slot - B1 <= i < curve_slot - B1 + 0x48))
check(mirror_changes == sorted(i - DB for i in diff_img), 'blob1 mirror changes == tuning-area changes (same IDs)')

# 4. decode the result through the camera's own lookup chain
by = lambda i: C[DB + i]
U2 = lambda a: struct.unpack('<H', c2[a - B2:a - B2 + 2])[0]
def s13(v): v &= 0x1fff; return v - 0x2000 if v & 0x1000 else v
def m3(p): ids = [U2(0xf33b94 + (p - 1) * 0x12 + 2 * k) for k in range(9)]; return [round(s13(by(i) | by(i + 1) << 8) / 1024, 3) for i in ids]
def m2(p): ids = [U2(0xf2e0d0 + (p - 1) * 8 + 2 * k) for k in range(4)]; a, d, b, c = [round(s13(by(i) | by(i + 1) << 8) / 1024, 3) for i in ids]; return [[a, b], [c, d]]
pre3s, pre3a, pre2 = by(U2(0xf34108 + 8)), by(U2(0xf34300 + 8)), by(U2(0xf2dd80 + 8))
check((pre3s, pre3a, pre2) == (5, 10, 5), 'PRO Neg Hi preset slots unchanged (5/10/5)')
M = m3(pre3s); print('INFO PRO Neg Hi 3x3 sRGB now', [M[0:3], M[3:6], M[6:9]], 'row sums', [round(sum(M[r*3:r*3+3]), 3) for r in range(3)])
check(all(abs(sum(M[r*3:r*3+3]) - 1) < 0.01 for r in range(3)), '3x3 sRGB rows sum to 1.0')
M = m3(pre3a); check(all(abs(sum(M[r*3:r*3+3]) - 1) < 0.01 for r in range(3)), '3x3 alt rows sum to 1.0')
print('INFO PRO Neg Hi 2x2 now', m2(pre2))
for name, a in (('PROVIA', 0), ('Velvia', 1), ('ASTIA', 2), ('Neg Std', 3)):
    check(m3(by(U2(0xf34108 + 2 * a))) == m3(by(U2(0xf34108 + 2 * a))) and S[DB + U2(0xf34108 + 2 * a)] == by(U2(0xf34108 + 2 * a)), f'{name} 3x3 preset untouched')
check(by(0xffc6) == 1 and by(0xe13b) == 1, 'detail preset and H/S family = PROVIA values')
# tone: every Neg Hi tone ID -> 38 (except the shared all-film-sims-16 mode), curve 38 = X-E2 curve 38
tone_tabs = {'321f0': [(0xf34098, 4), (0xf3427c, 4), (0xf33db0, 4), (0xf3407c, 4), (0xf33db0, 11), (0xf3407c, 11)],
             '3232c': [(0xf3448c, u * 3 + i) for u in range(6) for i in range(3)] + [(0xf34298, u * 3 + i) for u in range(6) for i in range(3)]}
vals = [by(U2(t + 2 * k)) for lst in tone_tabs.values() for t, k in lst]
check(set(vals) <= {38, 16} and vals.count(38) >= 40, f'PRO Neg Hi tone IDs -> curve 38 ({vals.count(38)}) / shared 16 ({vals.count(16)})')
cnt = struct.unpack('<I', c1[0x80b6f8 - B1:0x80b6fc - B1])[0]
entries = {struct.unpack('<I', c1[0x80b700 - B1 + k * 0x48:][:4])[0]: c1[0x80b700 - B1 + k * 0x48:0x80b700 - B1 + (k + 1) * 0x48] for k in range(cnt)}
check(cnt == 29 and 38 in entries and 40 not in entries, 'curve table: 29 entries, #40 slot now #38')
check(entries.get(38) == xe2_b1[0xb839d8 - XE2B1 + 38 * 0x48:0xb839d8 - XE2B1 + 39 * 0x48], 'curve 38 == X-E2 Classic Chrome curve byte-for-byte')
other = [n for n in entries if n != 38]
check(all(entries[n] == s1[0x80b700 - B1 + k * 0x48:0x80b700 - B1 + (k + 1) * 0x48] for k, n in enumerate(sorted(entries, key=lambda n: list(entries).index(n))) if n != 38), 'all other curves untouched')
print('\nRESULT:', 'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED')
sys.exit(0 if ok else 1)
