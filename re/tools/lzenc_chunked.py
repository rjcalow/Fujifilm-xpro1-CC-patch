# Fuji LZ encoder that respects the camera's 16 KB input-chunk rule.
#
# Stock Fuji streams never let a token straddle a 0x4000 boundary, counted from the start of the 20-byte blob
# header (0 straddles in ~1.3M tokens). Every boundary is hit exactly, without zero-length filler tokens.
# This encoder produces greedy tokens first, then lays them out so that:
#   * no token crosses a chunk boundary,
#   * a chunk never ends with exactly 1 free byte (it couldn't be filled without a zero-literal token).
# Token format: 0nnnnnnn = n literal bytes (n 1..127); 1ddddddd ddddllll = copy l (1..15) from distance d (1..2047).
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

def _greedy_tokens(data):
    """Return [('L', start, n) | ('M', start, l, d)] covering data."""
    toks = []; i = 0; n = len(data); idx = {}; lit_start = None
    while i < n:
        best_l = 0; best_d = 0
        if i + 3 <= n:
            for j in reversed(idx.get(bytes(data[i:i+3]), [])[-32:]):
                d = i - j
                if d > 2047: break
                l = 0
                while l < 15 and i + l < n and data[j + l] == data[i + l]: l += 1
                if l > best_l: best_l, best_d = l, d
                if l == 15: break
        if best_l >= 3:
            if lit_start is not None: toks.append(['L', lit_start, i - lit_start]); lit_start = None
            toks.append(['M', i, best_l, best_d])
            for k in range(best_l):
                if i + k + 3 <= n: idx.setdefault(bytes(data[i+k:i+k+3]), []).append(i + k)
            i += best_l
        else:
            if i + 3 <= n: idx.setdefault(bytes(data[i:i+3]), []).append(i)
            if lit_start is None: lit_start = i
            i += 1
    if lit_start is not None: toks.append(['L', lit_start, n - lit_start])
    return toks

def encode(data, header_len=20, chunk=0x4000):
    data = bytes(data); toks = _greedy_tokens(data); out = bytearray(); ti = 0
    def rr(): return chunk - ((header_len + len(out)) % chunk)
    def take(k):
        """Consume the next k output bytes from the token queue (front parts), return them as literal bytes."""
        nonlocal ti
        got = bytearray()
        while k and ti < len(toks):
            t = toks[ti]; avail = t[2]; use = min(k, avail)
            got += data[t[1]:t[1] + use]
            t[1] += use; t[2] -= use; k -= use        # matches keep their distance: remainder is still a valid copy
            if t[2] == 0: ti += 1
        return got
    while ti < len(toks):
        t = toks[ti]; r = rr()
        if r == 3:                                     # only a 2-byte literal run fills exactly 3 bytes
            lits = take(2); out.append(len(lits)); out += lits; continue
        if t[0] == 'M':                                # 2-byte token; r==2 fills exactly, r>=4 leaves >=2
            l, d = t[2], t[3]
            out += bytes([0x80 | (d >> 4), ((d & 0xf) << 4) | l]); ti += 1; continue
        n = min(t[2], 127, r - 1)
        if r - (1 + n) == 1: n -= 1                    # never leave exactly one byte in a chunk
        lits = take(n); out.append(n); out += lits
    return bytes(out)

def straddles(stream, header_len=20, chunk=0x4000):
    pos = 0; bad = 0
    while pos < len(stream):
        size = 2 if stream[pos] & 0x80 else 1 + stream[pos]
        a = header_len + pos; b = a + size - 1
        if a // chunk != b // chunk: bad += 1
        pos += size
    return bad
