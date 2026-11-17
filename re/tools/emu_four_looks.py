"""Compare the actual 3.93 camera code and its emitted settings with native manual setup."""

import argparse
import hashlib
import struct
from pathlib import Path

import four_looks as build
from four_looks import cclook, fw, ui
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm_const import (
    UC_ARM_REG_CPSR,
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_R4,
    UC_ARM_REG_SP,
    UC_CPU_ARM_CORTEX_R5,
)

END, STACK = 0x1FF0000, 0x1EE0000
SOURCE, FRAME, COMMAND = 0x9CB2FC, 0x1D00000, 0x1DB0000
MODES = (0, 3, 1, 8, 9, 10, 7, 11, 12, 5, 6, 2, 4)


def pack(*v):
    return struct.pack(f"<{len(v)}I", *(x & 0xFFFFFFFF for x in v))


class Body:
    def __init__(self, image, sections):
        self.image = image
        cpu = self.cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        cpu.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_R5)
        cpu.mem_map(0, 0x2000000)
        for addr, buf in zip((ui.B1_BASE, ui.B2_BASE, ui.M41_BASE), sections):
            cpu.mem_write(addr, bytes(buf))
        db = self.image[cclook.DB_FILE : cclook.DB_FILE + cclook.DB_LEN]

        def tuning(uc, addr, size, user):
            uc.reg_write(UC_ARM_REG_R0, db[uc.reg_read(UC_ARM_REG_R0)])
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        cpu.hook_add(UC_HOOK_CODE, tuning, begin=0x857BE0, end=0x857BE0)

    def call(self, addr, *args, until=END):
        cpu = self.cpu
        cpu.reg_write(UC_ARM_REG_CPSR, 0x1D3)
        cpu.reg_write(UC_ARM_REG_SP, STACK)
        cpu.reg_write(UC_ARM_REG_LR, END)
        for i, v in enumerate(args):
            cpu.reg_write(UC_ARM_REG_R0 + i, v & 0xFFFFFFFF)
        cpu.emu_start(addr, until, count=400000)
        assert cpu.reg_read(UC_ARM_REG_PC) == until, hex(addr)
        return cpu.reg_read(UC_ARM_REG_R0)

    def write(self, addr, *v):
        self.cpu.mem_write(addr, pack(*v))

    def word(self, addr):
        return int.from_bytes(self.cpu.mem_read(addr, 4), "little")

    def settings(self, mode, baseline):
        self.cpu.mem_write(SOURCE, baseline)
        self.call(0x77DDD8, mode)

    def manual(self, mode, red, blue, colour_row, high_row, shadow_row, sharp_row):
        # Menu row 0 = HIGH (+2), row 4 = LOW (-2) for these four controls.
        for key, row, setter in (
            (0x130, 0, 0x77D330),
            (0x48, colour_row, 0x77D594),
            (0x4A, high_row, 0x77DF38),
            (0x4B, shadow_row, 0x77DF58),
            (0x49, sharp_row, 0x77D4D4),
        ):
            self.call(setter, self.call(0x78A9EC, key, row, 0, 3))
        # Same setter sequence as 0x7869a4 after the on-camera WB fine-tune UI.
        for axis, key, value in ((0, 0x4E, red), (1, 0x4F, blue)):
            step = self.call(0x78A9EC, key, 9 - value, 0, 3)
            for group in (0, 8, 9):
                self.call(0x77DE38, step, group, axis)
        self.call(0x77DDD8, mode)

    def render(self):
        source = bytes(self.cpu.mem_read(SOURCE, 0x46C))
        self.write(COMMAND, SOURCE, 0)
        # Run actual event producer until the task-ID lookup after its copy.
        self.call(0xF79410, COMMAND, until=0xF7944C)
        packet_addr = 0x120220C
        assert self.word(STACK - 4 - 0x20) == packet_addr
        packet = bytes(self.cpu.mem_read(packet_addr, 0x46C))
        compact = []
        for src in (SOURCE, packet_addr):
            self.cpu.mem_write(FRAME, bytes([0xED]) * 0x218)
            self.call(0x9B7254, FRAME, src, 0)
            compact.append(bytes(self.cpu.mem_read(FRAME, 0x218)))
        assert bytes(self.cpu.mem_read(SOURCE, 0x46C)) == source
        return packet, compact


def main():
    if not __debug__:
        raise ValueError("Run without -O so the emulator checks are enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    base_image, *base_sections = build.prepare_base(args.stock.read_bytes())
    dat = args.candidate.read_bytes()
    assert fw.check(dat)[0] and hashlib.sha256(dat).hexdigest() == build.RESULT_SHA256
    image = dat.translate(build.INVERT)
    ref = Body(base_image, base_sections)
    test = Body(image, build.sections(image))
    assert struct.unpack_from("<II", dat, 0x204) == fw.parse_version("3.93")
    for start, end in ((0x25C, 0x10025C), (ui.M41_FILE + 0x9A9A0, len(dat))):
        assert image[start:end] == base_image[start:end]
    assert (
        ref.image[cclook.DB_FILE + 0xC8A5] == ref.image[cclook.DB_FILE + 0xC8A7] == 120
    )
    # On-screen indicators: native UI maps first shift to literal R (x axis),
    # second to B (y axis). Check both end-to-end through its packet layout.
    assert (
        test.cpu.mem_read(0x143D694, 2) == b"R\0"
        and test.cpu.mem_read(0x1427958, 2) == b"B\0"
    )
    for addr, _ in ui.NODES:
        assert test.cpu.mem_read(test.word(addr), 112) == b"".join(
            pack(i, 0) for i in (*ui.STOCK_ROWS, 10, 11, 12, ui.END)
        )
    for row, mode in enumerate(MODES):
        stored = test.call(0x78A9EC, 0x3D, row, 0, 1)
        assert test.call(0x78A9EC, 0x3D, stored, 1, 3) == mode
        assert test.call(0x78A9EC, 0x3D, mode, 3, 0) == row
        test.call(0x793814, 0x3D, stored, 0, test.call(0x792FE4))
        assert test.call(0x793048, 0x3D, 0) == stored
        test.call(0x786524)
        assert test.word(SOURCE + 0x128) == mode
    # Preserve existing glyph IDs and exercise native name queuing for both new rows.
    for i, label in enumerate(build.NAMES):
        test.cpu.reg_write(UC_ARM_REG_R4, 11 + i)
        test.call(0x147C748, until=0x147C75C)
        token = test.cpu.reg_read(UC_ARM_REG_R4)
        test.write(0x130000 + ui.NAME_ID * 10, 64)
        test.call(build.DRAW, 0xFFFFFFEC, 3 + i, token, until=0x1488808)
        glyphs = struct.unpack(
            f"<{len(label) + 1}H", test.cpu.mem_read(0x12B99BE, (len(label) + 1) * 2)
        )
        assert bytes(g - 0xE100 for g in glyphs[:-1]) == label and glyphs[-1] == 0
    for group in (0, 8, 9):
        baseline = bytearray(0x46C)
        for offset, v in (
            (0xD0, group),
            (0x130, 8),
            (0x110, 2),
            (0x3C4, 1),
            (0x3C8, 4),
            (0x218, 3),
            (0x12C, 2),
            (0xDC, -6),
            (0xE0, 5),
            (0xE4, 6),
            (0xE8, -5),
            (0xEC, 4),
            (0xF0, -3),
            (0x230, 0x1DE8000),
            (0x41C, 0x9876),
        ):
            baseline[offset : offset + 4] = pack(v)
        for mode in (12, 2, 6, 4, 11, 2, 4, 12, *MODES[:11]):
            test.settings(mode, bytes(baseline))
            ref.settings(mode, bytes(baseline))
            if mode == 2:
                ref.manual(12, 2, -4, 0, 3, 3, 4)
            if mode == 4:
                ref.manual(11, 1, -2, 4, 1, 0, 0)
            packet, compact = test.render()
            manual, control = ref.render()
            assert packet == manual and compact == control, (mode, group)
            assert compact[0] == compact[1]
            assert compact[0][-4:] == b"\xed" * 4
            # Run the actual UI snapshot copy into the display structure.
            test.write(0x9D59E4, 0x120220C)
            display = 0x128B054
            test.call(0xF7B75C, display + 0x584, until=0xF7B924)
            if mode in (2, 4):
                assert (test.word(display + 0x608), test.word(display + 0x60C)) == (
                    (2, 0xFFFFFFFC) if mode == 2 else (1, 0xFFFFFFFE)
                )
    # Compare actual chroma matrices and highlight/shadow register gains with native
    # base modes. Colour processing in the ISP and the sensor are outside Unicorn.
    for mode, base, h, s in (
        (2, 12, 3, 3),
        (4, 11, 1, 0),
        (12, 12, 2, 2),
        (6, 6, 2, 2),
    ):
        for column in (3, 4, 5, 6):
            results = []
            for machine, engine, hi, lo, native_mode in (
                (test, mode, 2, 2, False),
                (ref, base, h, s, True),
            ):
                c = machine.cpu
                c.mem_write(FRAME, bytes(0x400))
                machine.write(FRAME + 0xBC, hi, lo)
                machine.write(FRAME + 0x118, column)
                machine.call(0xF38A00 if native_mode else build.TONES, FRAME, engine)
                machine.call(0xF32C08, FRAME, FRAME + 0x200)
                cm = machine.word(FRAME + 0xC4)
                curves = bytes(c.mem_read(FRAME + 0x22A, 38))
                channels = []
                for alt in (0, 1):
                    machine.write(FRAME + 0xC8, alt)
                    machine.call(0xF32FCC, COMMAND, FRAME)
                    mat = bytes(c.mem_read(COMMAND, 18))
                    machine.call(0xF2D404, COMMAND, 0, cm, alt, 0)
                    channels.append((mat, bytes(c.mem_read(COMMAND, 16))))
                results.append((cm, curves, channels))
            assert results[0] == results[1], (mode, column)
    print(
        "PASS: packaged 3.93 checksum; boot sections, tuning/peaking, language blocks; 13 native stored selections and two menu names."
    )
    print(
        "PASS: complete native shooting message and capture projection match manually selected recipes; consecutive ordinary/recipe modes; three incoming WB modes; red and blue label order."
    )
    print(
        "PASS: real JPEG matrix selection in both colour spaces and all 19 tone gains in four columns match their native base/adjustment references."
    )


if __name__ == "__main__":
    main()
