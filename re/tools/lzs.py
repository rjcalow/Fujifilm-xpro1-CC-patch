# Tiny LZ for the SD bootstrap (decoder in sdboot_chain.py, a few ARM instructions).
# Stream of tokens, each starting with a u16 LE header:
#   0x0000                 end of stream
#   0x8000 | n  (n < 2^15) n literal bytes follow
#   n (1..2^15-1), then u16 distance d (1..65535): copy n bytes from out[-d] (overlap allowed)
import struct

def encode(data, min_match=4, max_chain=64):
    n = len(data); out = bytearray(); lit = bytearray(); i = 0; heads = {}
    def flush():
        nonlocal lit
        for k in range(0, len(lit), 0x7fff):
            part = lit[k:k + 0x7fff]; out.extend(struct.pack('<H', 0x8000 | len(part))); out.extend(part)
        lit = bytearray()
    while i < n:
        best = (0, 0)
        if i + min_match <= n:
            key = data[i:i + 3]
            for j in reversed(heads.get(key, [])[-max_chain:]):
                d = i - j
                if d > 0xffff: break
                l = 0
                while i + l < n and l < 0x7fff and data[j + l] == data[i + l]: l += 1
                if l > best[0]: best = (l, d)
                if l == 0x7fff: break
        if best[0] >= min_match:
            flush(); out.extend(struct.pack('<HH', best[0], best[1]))
            for k in range(best[0]):
                if i + k + 3 <= n: heads.setdefault(data[i + k:i + k + 3], []).append(i + k)
            i += best[0]
        else:
            if i + 3 <= n: heads.setdefault(data[i:i + 3], []).append(i)
            lit.append(data[i]); i += 1
    flush(); out.extend(b'\0\0')
    return bytes(out)

def decode(stream):
    out = bytearray(); p = 0
    while True:
        h, = struct.unpack('<H', stream[p:p + 2]); p += 2
        if h == 0: return bytes(out)
        if h & 0x8000:
            k = h & 0x7fff; out += stream[p:p + k]; p += k
        else:
            d, = struct.unpack('<H', stream[p:p + 2]); p += 2
            for _ in range(h): out.append(out[-d])
