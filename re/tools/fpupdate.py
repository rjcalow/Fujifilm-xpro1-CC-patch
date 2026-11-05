# Fujifilm FPUPDATE/FWUP container helpers (EXR / X-Processor generation).
#
# Layout (verified on X-Pro1 FPUPDATE.DAT, X-E2 FWUP0004.DAT, X-Pro2 FWUP0008.DAT):
#   0x000..0x1ff  model ID list (ASCII-hex) etc.        plain
#   0x204         u32 version major, 0x208 u32 version minor
#   0x20c         u32 PAYLOAD CHECKSUM = ~sum(bytes of the bit-inverted payload) mod 2^32
#   0x240         section table: u32 L (payload length), u32 L, then per trailer {u32 len, u32 cksum}
#                 (X-Pro2 has a second trailer as {u32 offset, u32 len, u32 cksum})
#   0x25c         payload, L bytes, stored bit-inverted (flash image from flash offset 0)
#   0x25c+L       trailer section(s), plain; each cksum = ~sum(raw bytes) mod 2^32
import struct

def read_layout(raw):
    h = struct.unpack('<32I', raw[0x200:0x280])
    L = h[16]
    trailers = [(h[18], h[19])]
    if h[21] not in (0, 0xffffffff):
        trailers.append((h[21], h[22]))
    return L, trailers

def payload_checksum(raw, L):
    return (~sum(255 - x for x in raw[0x25c:0x25c + L])) & 0xffffffff

def verify(raw):
    """Return list of (name, stored, computed, ok)."""
    L, trailers = read_layout(raw)
    res = [('payload @0x20c', struct.unpack('<I', raw[0x20c:0x210])[0], payload_checksum(raw, L))]
    pos = 0x25c + L
    for i, (ln, ck) in enumerate(trailers):
        res.append((f'trailer{i}', ck, (~sum(raw[pos:pos + ln])) & 0xffffffff)); pos += ln
    res.append(('size', len(raw), pos))
    return [(n, s, c, s == c) for n, s, c in res]

def pack(not_image, template_raw):
    """Build a raw update file from a fully bit-inverted image (as produced by unpack.sh) and fix the checksum.
    Only the payload is taken from not_image; header and trailers must be unchanged."""
    raw = bytearray(x ^ 0xff for x in not_image)
    assert raw[:0x20c] == template_raw[:0x20c] and raw[0x210:0x25c] == template_raw[0x210:0x25c], 'header changed'
    L, trailers = read_layout(raw)
    assert raw[0x25c + L:] == template_raw[0x25c + L:], 'trailer changed'
    raw[0x20c:0x210] = struct.pack('<I', payload_checksum(raw, L))
    return bytes(raw)
