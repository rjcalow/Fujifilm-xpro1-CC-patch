# USB debug firmware for the X-Pro1: Classic Chrome v2 + three PTP vendor operations (read/write/call memory).
# usage: build_ptpdebug.py <v2 FPUPDATE.DAT (sha 0df1cefe…)> <out/FPUPDATE.DAT> [--version 3.85]
#
# PTP dispatcher (blob2 FUN_00f4521c): opcode high byte selects a handler table, low byte indexes it:
#   0x10xx → 0xf4c028[0..0x1c], 0x90xx → 0xf4c09c[0..0x1d], 0x98xx → 0xf4c114[0..0x0b]; 0xf4bff0 = "not supported".
# Handlers are called as h(phase, request): phase 1 = command received; a data-in operation copies the request into
# the data container 0x11f3bc8 (FUN_00f45510), gets a buffer from the storage callbacks (*(0x11f3bb0)+0x1c, kind 7;
# pointer → container+0x24, length → +0x28), fills it and sends it (FUN_00f44ca8(container, 0)); the next call
# (phase != 1) sends the response (FUN_00f459dc(request, container, status) + FUN_00f44ca8). Same pattern as
# GetStorageIDs (0xf4a840). Operations without data respond in the first call (CloseSession 0xf4bf58).
# Request: +0 opcode (u16), +4 session id, +8 transaction id, +0x10.. parameters 1-5. Session open: [0x11f3c2c] != 0.
#
# New operations (slots 0x10..0x12 of the 0x90xx table, all "not supported" in stock 3.82):
#   0x9010 PEEK  p1 = address (word aligned), p2 = length (≤ 0x10000, rounded down to words) → data phase, word reads
#   0x9011 POKE  p1 = address, p2 = 32-bit value → writes one word (dsb)
#   0x9012 CALL  p1 = function address, p2 = r0 → blx; r0 result stored at RESULT (read it with PEEK)
# Code space: the nine "not supported" stubs 0xf45a58..0xf45c08 (referenced only from the 0x10xx table). Their nine
# table entries are pointed at the generic 0xf4bff0 (same 0x2005 answer); the stubs are then overwritten.
import hashlib, os, struct, sys
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'public'))
import xpro1_cc_patch as P

V2_SHA256 = '0df1cefec2a9188c'                              # prefix of the flashed v2 file (labelled 3.83)
B2_HDR, B2_END, B2_BASE = 0x24025c, 0x46025c, 0xe0ec80
TABLE10, TABLE90, GENERIC = 0xf4c028, 0xf4c09c, 0xf4bff0
STUBS = [0xf45bd8, 0xf45ba8, 0xf45b78, 0xf45b48, 0xf45b18, 0xf45ae8, 0xf45ab8, 0xf45a88, 0xf45a58]
CAVE, CAVE_END = 0xf45a58, 0xf45c08
CONT, STATUS, SESSION, CB = 0x11f3bc8, 0x11f3c30, 0x11f3c2c, 0x11f3bb0
F_COPYREQ, F_SEND, F_RESP = 0xf45510, 0xf44ca8, 0xf459dc
OPS = {0x9010: 'peek', 0x9011: 'poke', 0x9012: 'call'}
MAXLEN = 0x10000


def handlers(base=CAVE, ops=('peek', 'poke', 'call'), limit=CAVE_END):
    """Assemble the handlers at base (default: all three into the blob2 cave); returns (code, {name: address}, and
    'result' when CALL is included). romdump/build_dumpcard.py assembles PEEK alone into the loader filler."""
    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)
    imm = lambda r, v: f'movw {r}, #{v & 0xffff}\n    movt {r}, #{v >> 16}'
    respond = f'''
    mov r0, r4
    {imm('r1', CONT)}
    bl {F_RESP:#x}
    {imm('r0', CONT)}
    mov r1, #0
    bl {F_SEND:#x}'''
    session = f'''
    {imm('r3', SESSION)}
    ldr r3, [r3]
    cmp r3, #0'''
    blocks = {}
    blocks['peek'] = f'''
    push {{r4, r5, r6, r7, fp, lr}}
    mov r4, r1
    cmp r0, #1
    bne peek_resp
    {session}
    movw r5, #0x2001
    movweq r5, #0x2003
    {imm('r3', STATUS)}
    str r5, [r3]
    mov r0, r4
    {imm('r1', CONT)}
    bl {F_COPYREQ:#x}
    movw r3, #0x2001
    cmp r5, r3
    bne peek_send
    ldr r6, [r4, #0x10]
    ldr r0, [r4, #0x14]
    cmp r0, #{MAXLEN:#x}
    movhi r0, #{MAXLEN:#x}
    bic r0, r0, #3
    {imm('r1', CONT + 0x24)}
    mov r2, #0
    mov r3, #7
    {imm('r12', CB)}
    ldr r12, [r12]
    ldr r12, [r12, #0x1c]
    blx r12
    bic r0, r0, #3
    {imm('r1', CONT)}
    str r0, [r1, #0x28]
    ldr r2, [r1, #0x24]
peek_copy:
    subs r0, r0, #4
    blo peek_send
    ldr r3, [r6], #4
    str r3, [r2], #4
    b peek_copy
peek_send:
    {imm('r0', CONT)}
    mov r1, #0
    bl {F_SEND:#x}
    pop {{r4, r5, r6, r7, fp, pc}}
peek_resp:
    mov r0, r4
    {imm('r1', CONT)}
    {imm('r2', STATUS)}
    ldr r2, [r2]
    bl {F_RESP:#x}
    {imm('r0', CONT)}
    mov r1, #0
    bl {F_SEND:#x}
    pop {{r4, r5, r6, r7, fp, pc}}'''
    blocks['poke'] = f'''
    push {{r4, r5, fp, lr}}
    mov r4, r1
    {session}
    movw r2, #0x2003
    beq poke_r
    ldr r0, [r4, #0x10]
    ldr r1, [r4, #0x14]
    str r1, [r0]
    dsb
    movw r2, #0x2001
poke_r:
    {respond}
    pop {{r4, r5, fp, pc}}'''
    blocks['call'] = f'''
    push {{r4, r5, fp, lr}}
    mov r4, r1
    {session}
    movw r2, #0x2003
    beq call_r
    ldr r0, [r4, #0x14]
    ldr r12, [r4, #0x10]
    blx r12
    adr r1, result
    str r0, [r1]
    movw r2, #0x2001
call_r:
    {respond}
    pop {{r4, r5, fp, pc}}
result:
    .word 0'''
    code = b''; at = {}
    for name, src in blocks.items():
        if name not in ops: continue
        a = base + len(code); at[name] = a
        part = bytes(ks.asm(src, a)[0])
        code += part + bytes(-len(part) % 8)
    if 'call' in at: at['result'] = at['call'] + len(bytes(ks.asm(blocks['call'], at['call'])[0])) - 4
    assert base + len(code) <= limit, f'handlers {len(code)} B do not fit the {limit - base} B space'
    return code, at


def patch_blob2(b2):
    """b2: decompressed blob2 (bytearray). Returns info dict."""
    w = lambda a: struct.unpack('<I', b2[a - B2_BASE:a - B2_BASE + 4])[0]
    put = lambda a, v: b2.__setitem__(slice(a - B2_BASE, a - B2_BASE + 4), struct.pack('<I', v))
    # 1. the nine stub entries of the 0x10xx table → generic "not supported"
    slots = [TABLE10 + 4 * i for i in range(0x1d) if w(TABLE10 + 4 * i) in STUBS]
    assert sorted(w(s) for s in slots) == sorted(STUBS), 'stub table entries differ from 3.82'
    refs = [a for a in range(B2_BASE, B2_BASE + len(b2) - 3, 4) if w(a) in STUBS]
    assert sorted(refs) == sorted(slots), f'stubs referenced elsewhere: {[hex(a) for a in refs]}'
    for s in slots: put(s, GENERIC)
    # 2. handlers into the cave
    code, at = handlers()
    b2[CAVE - B2_BASE:CAVE - B2_BASE + len(code)] = code
    # 3. vendor table slots
    for op, name in OPS.items():
        slot = TABLE90 + 4 * (op & 0xff)
        assert w(slot) == GENERIC, f'{op:#x} slot is not free'
        put(slot, at[name])
    return {'handlers': {k: hex(v) for k, v in at.items()}, 'stub_slots': [hex(s) for s in slots],
            'cave_bytes': len(code)}


def build(src, dst, version='3.85'):
    raw = open(src, 'rb').read()
    assert hashlib.sha256(raw).hexdigest().startswith(V2_SHA256), 'input is not the flashed Classic Chrome v2 file'
    ok, length = P.check(raw); assert ok, 'container checksums'
    img = bytearray(x ^ 0xff for x in raw)
    unpacked, packed = struct.unpack('<II', img[B2_HDR:B2_HDR + 8])
    print('decompressing blob 2 ...')
    b2 = bytearray(P.lz_decode(img, B2_HDR + 20, B2_HDR + packed, unpacked))
    stock_b2 = bytes(b2)
    info = patch_blob2(b2)
    changed = [i for i in range(len(b2)) if b2[i] != stock_b2[i]]
    print('blob 2 patch:', info, f'{len(changed)} bytes changed in {B2_BASE + changed[0]:#x}..{B2_BASE + changed[-1]:#x}')
    print('re-compressing blob 2 (a minute or two) ...')
    enc = P.lz_encode(bytes(b2)); total = len(enc) + 20
    assert total <= B2_END - B2_HDR, 'blob 2 does not fit its partition'
    img[B2_HDR:B2_END] = struct.pack('<5I', unpacked, total, -(-total // 0x4000), 0x4000, 4) + enc \
                         + bytes(B2_END - B2_HDR - total)
    assert P.lz_decode(img, B2_HDR + 20, B2_HDR + total, unpacked) == bytes(b2), 'blob 2 round trip'
    out = bytearray(x ^ 0xff for x in img)
    out[0x204:0x20c] = struct.pack('<II', 3, 0x83)                # restore the label the v2 file had, then relabel
    out[0x20c:0x210] = struct.pack('<I', P.payload_sum(out, length))
    major, minor = P.parse_version(version)
    out[0x204:0x20c] = struct.pack('<II', major, minor)
    assert P.check(out)[0], 'checksums'
    # everything outside blob 2's partition and the header label/checksum must equal the v2 input
    diff = [i for i in range(len(raw)) if raw[i] != out[i] and not (B2_HDR <= i < B2_END) and not (0x204 <= i < 0x210)]
    assert not diff, f'unexpected changes outside blob 2: {diff[:8]}'
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    open(dst, 'wb').write(out)
    print(f'wrote {dst} labelled {version}, SHA-256 {hashlib.sha256(out).hexdigest()}')
    return bytes(b2)


if __name__ == '__main__':
    a = sys.argv[1:]; ver = '3.85'
    if '--version' in a: k = a.index('--version'); ver = a[k + 1]; del a[k:k + 2]
    build(a[0], a[1], ver)
