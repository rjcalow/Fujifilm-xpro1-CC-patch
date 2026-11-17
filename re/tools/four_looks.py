"""Build the four-look X-Pro1 release from official 3.82 in memory."""

import hashlib
import re
import struct

import build_cc3
import cchook
import cclook
import fsim11 as ui
import uitext
from build_cc3 import P as fw
from build_cc3 import uiname
from keystone import KS_ARCH_ARM, KS_MODE_ARM, Ks

RESULT_SHA256 = "540766f06bc19f059013a65b3e5efb398abf5f457f780bd7b1bf192ed4d17aef"
INVERT = bytes(reversed(range(256)))
NAME = "SUPERIA 400"
TONE = 26  # Stock PRO Neg. Std tone curve


MENU, CODE, TABLES = 0x779ADC, 0x7778FC, 0x777BC4
SHARED = 0x77604C
REFERENCES = {MENU: 0x775D78, CODE: 0x77A470, TABLES: 0x77AC40}


def pack(*values):
    return struct.pack(f"<{len(values)}I", *values)


def repack(img, header, end, blob):
    data = fw.lz_encode(bytes(blob))
    size = len(data) + 20
    assert size <= end - header
    img[header:end] = (
        pack(len(blob), size, (size + 16383) // 16384, 16384, 4) + data
    ).ljust(end - header, bytes(1))
    assert fw.lz_decode(img, header + 20, header + size, len(blob)) == blob


def colour_plan(db):
    # ASTIA's two RGB matrices for skin tones; use the 3.92 body's actual coefficients.
    # The new chroma matrix starts at PROVIA, with slightly stronger cool colours.
    plan = {}

    def put(offset, data):
        for i, value in enumerate(data, offset):
            if db[i] != value:
                plan[i] = (db[i], value)

    for dest, src in ((17, 3), (18, 8)):
        start = cclook.ID_3X3(src)
        put(cclook.ID_3X3(dest), db[start : start + 18])
    start = cclook.ID_2X2(1)
    coefs = [v - 8192 if v & 4096 else v for v in struct.unpack_from("<4H", db, start)]
    # Storage order Cr<-Cr, Cb<-Cb, Cr<-Cb, Cb<-Cr. Zero chroma stays neutral.
    coefs[0] = round(coefs[0] * 1.04)
    coefs[1] = round(coefs[1] * 1.12)
    put(cclook.ID_2X2(12), struct.pack("<4H", *(v & 8191 for v in coefs)))
    selectors = {
        0xDD26: 17,
        0xDD8E: 17,
        0xDD5E: 17,
        0xE4A0: 12,
        cclook.SEL_ALT3: 18,
        cclook.SEL_ALT2: 12,
    }
    selectors.update({0x10101 + 0x30 * r: 12 for r in range(4)})
    selectors.update(dict.fromkeys(cclook.FAM5_IDS, TONE))
    for addr, value in selectors.items():
        put(addr, bytes([value]))
    return plan


def language(img):
    entries, template = ui.lang(img)
    data = bytearray(template)
    encoded = (NAME + "\0").encode("utf-16le")
    assert len(encoded) <= 32
    data[cchook.T_PLAIN : cchook.T_PLAIN + 32] = encoded.ljust(32, bytes(1))
    return entries, bytes(data)


def prepare_base(raw):
    if not __debug__:
        raise ValueError("Run without -O so all firmware layout checks are enabled")
    if hashlib.sha256(raw).hexdigest() != fw.STOCK_SHA256:
        raise ValueError(
            "Expected the official Fujifilm X-Pro1 3.82 FPUPDATE.DAT (SHA-256 mismatch)"
        )
    if not fw.check(raw)[0]:
        raise ValueError("Stock firmware checksum is invalid")
    img = bytearray(raw.translate(INVERT))
    blob1, blob2, module = map(bytearray, ui.check(img))
    fits = {i: (old, new) for i, old, new in build_cc3.PARAMS3}

    def tuning(offset, old, new):
        for buf, at in (
            (img, fw.TUNING + offset),
            (blob1, fw.MIRROR - ui.B1_BASE + offset),
        ):
            assert buf[at : at + len(old)] == old and len(old) == len(new), hex(offset)
            buf[at : at + len(new)] = new

    for i, old, replacement in fw.PARAMS:
        if i in fits:
            v2, v3 = fits[i]
            assert replacement == v2
            replacement = v3
        tuning(i, bytes.fromhex(old), bytes.fromhex(replacement))
    for i, previous, gain in ((0xC88C, 40, 48), (0xC8A5, 64, 120), (0xC8A7, 64, 120)):
        tuning(i, bytes([previous]), bytes([gain]))
    curve = fw.CURVE_SLOT - ui.B1_BASE
    assert blob1[curve : curve + 4].hex() == fw.CURVE_OLD_FIRST4
    blob1[curve : curve + 72] = bytes.fromhex(fw.CURVE_NEW)
    assert uiname.patch_image(img) == 35
    apply_superia(img, blob1, blob2, module)
    return img, blob1, blob2, module


def apply_superia(img, blob1, blob2, module):
    base1, base2 = ui.B1_BASE, ui.B2_BASE
    original = bytes(blob1), bytes(blob2), bytes(module)

    def replace(buf, offset, old, new):
        assert len(old) == len(new) and buf[offset : offset + len(old)] == old, hex(
            offset
        )
        buf[offset : offset + len(old)] = new

    # Intern three identical read-only option lists. Their original menus now
    # share the exact original 19 choices and terminator at SHARED.
    choices = b"".join(pack(i, 0) for i in (*range(19), ui.END))
    assert (
        len(choices) == 160 and blob1[SHARED - base1 : SHARED - base1 + 160] == choices
    )
    for addr, ref in REFERENCES.items():
        assert blob1[addr - base1 : addr - base1 + 160] == choices
        for displacement in range(0, 160, 4):
            needle = pack(addr + displacement)
            hits = [
                m.start() + base1
                for m in re.finditer(re.escape(needle), original[0])
                if m.start() % 4 == 0
            ]
            assert hits == ([ref] if displacement == 0 else [])
            assert all(needle not in buf for buf in original[1:])
        replace(blob1, ref - base1, pack(addr), pack(SHARED))

    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)

    def asm(src, addr):
        return bytes(ks.asm(src, addr)[0])

    layout = {
        "A": CODE,
        "B": CODE + 16,
        "C": CODE + 32,
        "T1": CODE + 48,
        "T2": CODE + 68,
        "ALT3": TABLES,
        "ALT2": TABLES + 16,
    }
    layout["end"] = max(layout.values()) + 128
    fragments = cclook.blobs(layout, asm)
    for addr, old, new in cclook.words(layout, asm):
        replace(blob2, addr - base2, pack(old), pack(new))
    fragments[MENU] = b"".join(pack(i, 0) for i in (*ui.STOCK_ROWS, 10, ui.END))
    icons = {"A": MENU + 96, "B": CODE + 100}
    for key, src in ui.ICON_SRC.items():
        offset = src - ui.M41_BASE
        fragments[icons[key]] = bytes(module[offset : offset + 40]) + pack(ui.ICON_ID)
    used = set()
    for addr, data in fragments.items():
        assert any(
            start <= addr and addr + len(data) <= start + 160 for start in REFERENCES
        )
        region = set(range(addr, addr + len(data)))
        assert not used.intersection(region)
        used.update(region)
        blob1[addr - base1 : addr - base1 + len(data)] = data
    for addr, old, new in [(ui.ROW10, ui.END, 13), (ui.ROW10 + 8, ui.END, 6)] + [
        (a, v, MENU) for a, v in ui.NODES
    ]:
        replace(blob1, addr - base1, pack(old), pack(new))
    for addr, old, new in ui.MOD41:
        replace(
            module,
            addr - ui.M41_BASE,
            pack(old),
            pack(icons[new] if isinstance(new, str) else new),
        )
    db = img[cclook.DB_FILE : cclook.DB_FILE + cclook.DB_LEN]
    for i, (old, new) in colour_plan(db).items():
        replace(img, cclook.DB_FILE + i, bytes([old]), bytes([new]))
        replace(blob1, fw.MIRROR - base1 + i, bytes([old]), bytes([new]))
    entries, template = language(img)
    for lang in range(35):
        offset = uitext.FILE0 + lang * uitext.BLOCK
        for addr, old, new in entries[lang * 2 : lang * 2 + 2]:
            replace(img, offset + addr - uitext.RAM, pack(old), pack(new))
        tail = offset + cchook.TAIL
        replace(img, tail, bytes([255]) * len(template), template)


OPTIONS, TEXT, STYLE, HANDOFF, LABELS, ROWS = (
    0x77A014,
    0x777CC4,
    0x77644C,
    0x778E74,
    0x77A87C,
    0x77B9C8,
)
# Intern byte-identical read-only menu option vectors; verify their only references below.
SPACE = {
    OPTIONS: (200, 0x77667C, 0x775CC8),
    TEXT: (256, 0x77904C, 0x777750),
    STYLE: (160, SHARED, 0x776B50),
    HANDOFF: (160, SHARED, 0x778500),
    LABELS: (160, SHARED, 0x774710),
    ROWS: (160, SHARED, 0x7797D0),
}
NAMES = (b"REGGIE'S PORTRA", b"KODACHROME II")
NAME_PTR = TEXT + 64
DRAW = TEXT + 112
COPY = HANDOFF
PROJECT = HANDOFF + 32
CAPTURE = STYLE
TONES = LABELS + 104
# This call copies 0x46c bytes into the outgoing settings message (0x20c).
# Other copies serve as restore points. In particular 0xfa5b28 copies WB
# back from one such block. Those blocks must retain the original settings.
COPY_SITES = (0xF79434,)


def sections(image):
    result = []
    for header in (0x10025C, 0x24025C):
        size, length = struct.unpack_from("<II", image, header)
        result.append(
            bytearray(fw.lz_decode(image, header + 20, header + length, size))
        )
    result.append(bytearray(image[ui.M41_FILE : ui.M41_FILE + 0x9A9A0]))
    return result


def apply_recipes(b1, b2, module):
    regions = ((ui.B1_BASE, b1), (ui.B2_BASE, b2), (ui.M41_BASE, module))

    def locate(addr):
        for base, data in regions:
            if 0 <= addr - base < len(data):
                return data, addr - base
        raise ValueError(hex(addr))

    def read(addr, count):
        buf, i = locate(addr)
        return bytes(buf[i : i + count])

    def replace(addr, old, new):
        assert len(old) == len(new) and read(addr, len(old)) == old, hex(addr)
        buf, i = locate(addr)
        buf[i : i + len(new)] = new

    original = tuple(bytes(buf) for _, buf in regions)
    for addr, (size, peer, ref) in SPACE.items():
        assert read(addr, size) == read(peer, size) and read(
            addr + size - 8, 8
        ) == pack(ui.END, 0)
        for offset in range(0, size, 4):
            token = pack(addr + offset)
            hits = [
                m.start() + base
                for (base, _), blob in zip(regions, original)
                for m in re.finditer(re.escape(token), blob)
                if m.start() % 4 == 0
            ]
            assert hits == ([] if offset else [ref]), (hex(addr + offset), hits)
        replace(ref, pack(addr), pack(peer))
    used = set()

    def put(addr, data):
        assert any(
            start <= addr and addr + len(data) <= start + n
            for start, (n, _, _) in SPACE.items()
        ), hex(addr)
        span = set(range(addr, addr + len(data)))
        assert used.isdisjoint(span), hex(addr)
        used.update(span)
        replace(addr, read(addr, len(data)), data)

    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)

    def asm(code, addr):
        return bytes(ks.asm(code, addr)[0])

    def patch(addr, old, new):
        replace(addr, asm(old, addr), asm(new, addr))

    def imm(reg, addr):
        return f"movw {reg}, #{addr & 65535}; movt {reg}, #{addr >> 16}"

    conv = 0x78F168
    assert read(conv + 132, 12) == pack(0xFFFF, 0xFFFF, 0xFFFF)
    put(
        OPTIONS,
        read(conv, 132) + pack(14, ui.END, 2, 15, ui.END, 4, 0xFFFF, 0xFFFF, 0xFFFF),
    )
    replace(0x78BA10 + 0x3D * 4, pack(conv), pack(OPTIONS))
    for addr, _ in ui.NODES:
        replace(addr, pack(MENU), pack(ROWS))
    put(ROWS, b"".join(pack(v, 0) for v in (*ui.STOCK_ROWS, 10, 11, 12, ui.END)))
    for old, new, refs in (
        (MENU + 96, LABELS, (0x14299FC, 0x142BD98)),
        (CODE + 100, LABELS + 52, (0x1429A00, 0x142BD9C)),
    ):
        badges = read(old, 44)
        put(new, badges + badges[32:36] + badges[28:32])
        for ref in refs:
            replace(ref, pack(old), pack(new))
    for table in (0x1474E7C, 0x1474E3C):
        replace(table + 2, b"\0", bytes([11]))
        replace(table + 4, bytes([5]), bytes([12]))
    put(TEXT, read(0x1483C20, 44) + pack(NAME_PTR, NAME_PTR + 24))
    put(NAME_PTR, NAMES[0].ljust(24, b"\0") + NAMES[1] + b"\0")
    patch(0x147C748, "cmp r4,#10", "cmp r4,#12")
    patch(0x147C750, imm("r3", 0x1483C20), imm("r3", TEXT))
    patch(0x147C798, "bl 0x1433604", f"bl {DRAW}")
    put(
        DRAW,
        asm(
            f"""
        {imm("ip", NAME_PTR)}
        cmp r2,ip
        addne ip,ip,#24
        cmpne r2,ip
        bne 0x1433604
        push {{r4,r5,r6,lr}}
        mov r4,r2
        mov r5,r1
        movw r0,#{ui.NAME_ID}
        bl 0x148c0a0
        mov r1,r0
        sub r2,r5,#1
        add r2,r2,r2,lsl #1
        lsl r2,r2,#3
        mov r0,r4
        movw r3,#0xffff
        sub sp,sp,#8
        str r3,[sp]
        bl 0x14328fc
        add sp,sp,#8
        pop {{r4,r5,r6,pc}}
    """,
            DRAW,
        ),
    )

    # Two paths consume the same settings. Style only the destination of each
    # native copy. Red and blue are signed values in separate full words.
    # The copy of the engine settings contains three WB shift pairs (the stock
    # manual-set routine at 0x7869a4 refreshes all three). The compact
    # projection receives just the pair for the effective WB mode.
    def profile(addr, fsim, wb, shifts, color, hi, lo, sharp):
        code = [
            f"ldr r1,[r0,#{fsim}]",
            "cmp r1,#2",
            "cmpne r1,#4",
            "bxne lr",
            "cmp r1,#2",
        ]

        def load(cond, n):
            return f"mov{cond} r2,#{n}" if n >= 0 else f"mvn{cond} r2,#{~n}"

        # Values below are the native menu encodings for each recipe.
        for reggie, koda, offsets in [
            (12, 11, [fsim]),
            (0, 0, [wb]),
            (2, 1, shifts[0]),
            (-4, -2, shifts[1]),
            (7, 9, [color]),
            (3, 1, [hi]),
            (3, 0, [lo]),
            (0, 4, [sharp]),
        ]:
            if reggie == koda:
                code.append(load("", reggie))
            else:
                code.extend((load("eq", reggie), load("ne", koda)))
            code.extend(f"str r2,[r0,#{o}]" for o in offsets)
        code.append("bx lr")
        return asm("\n".join(code), addr)

    put(
        CAPTURE,
        profile(
            CAPTURE,
            0x128,
            0xD0,
            ([0xDC, 0xE4, 0xEC], [0xE0, 0xE8, 0xF0]),
            0x130,
            0x3C4,
            0x3C8,
            0x110,
        ),
    )
    # Call the original memcpy; retain its return registers.
    put(
        COPY,
        asm(
            f"""
        push {{r4,lr}}
        mov r4,r0
        bl 0x966f88
        push {{r0-r3,ip,lr}}
        mov r0,r4
        bl {CAPTURE}
        pop {{r0-r3,ip,lr}}
        pop {{r4,pc}}
    """,
            COPY,
        ),
    )
    for site in COPY_SITES:
        assert read(site - 4, 4) == asm("movw r2,#0x46c", site - 4)
        patch(site, "bl 0x966f88", f"bl {COPY}")
    # All three direct callers of the compact capture-settings exporter
    # can also supply the original UI structure without taking a copy first.
    # Tail-branch preserves its return value and restores the stock frame.
    tail = ROWS + 112
    patch(0x9B7610, "pop {r4,r5,fp,pc}", f"b {tail}")
    put(
        tail,
        asm(
            f"push {{r0,lr}}; mov r0,r5; bl {PROJECT}; pop {{r0,lr}}; pop {{r4,r5,fp,pc}}",
            tail,
        ),
    )
    put(
        PROJECT,
        profile(PROJECT, 0x100, 0xEC, ([0xF0], [0xF4]), 0xFC, 0x1E8, 0x1EC, 0xF8),
    )
    # The normal still JPEG record also has a direct mode setter. This is
    # needed for callers that carry a named mode through to the last stage.
    put(
        TONES,
        asm(
            """
        cmp r1,#2
        cmpne r1,#4
        bne 0xf38a00
        cmp r1,#2
        moveq r1,#12
        movne r1,#11
        moveq r2,#3
        movne r2,#1
        str r2,[r0,#0xbc]
        movne r2,#0
        str r2,[r0,#0xc0]
        b 0xf38a00
    """,
            TONES,
        ),
    )
    patch(0xF39144, "bl 0xf38a00", f"bl {TONES}")


def encode(img, blob1, blob2, module):
    repack(img, fw.BLOB1_HDR, fw.BLOB1_END, blob1)
    repack(img, fw.BLOB1_END, ui.M41_FILE, blob2)
    img[ui.M41_FILE : ui.M41_FILE + len(module)] = module
    data = img.translate(INVERT)
    fw.relabel(data, fw.parse_version("3.93"))
    length = struct.unpack_from("<I", data, 0x240)[0]
    struct.pack_into("<I", data, 0x20C, fw.payload_sum(data, length))
    if not fw.check(data)[0] or hashlib.sha256(data).hexdigest() != RESULT_SHA256:
        raise ValueError("Generated image does not match the camera-tested 3.93 build")
    return data


def build(raw):
    image, blob1, blob2, module = prepare_base(raw)
    apply_recipes(blob1, blob2, module)
    return encode(image, blob1, blob2, module)
