"""Read-only access to the official X-Pro1 3.82 update file (and the flashed firmware the card runs on).

Everything a feature module needs to check a stock word before it plans a change: the decoded update image, the
decompressed code images blob1 / blob2, the menu modules 0x41 / 0x44, the tuning area and the language blocks.
Addresses are RAM addresses, as in FINDINGS.md / NOTES.md; `word(addr)` finds the image that holds an address.
"""
import hashlib, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RE = os.path.normpath(os.path.join(HERE, '..', '..'))              # re/
sys.path.insert(0, os.path.join(RE, '..', 'public'))
import xpro1_cc_patch as _lz                                       # Fujifilm method-4 LZ decoder (public/)

OFFICIAL_SHA256 = '709e26f6dd77e922660010628fb20937b269be871b188b8810eb2cb4d5d33236'
LOADER_SHA256 = 'ff31ef67c7b024a33ea3757cbff3d9564618c9660a90bbbbfecffaf6a31f24a7'
FFSYS_SHA256 = '83a3fc5e9e88e6eda0dacb8657cb4c8a83163f2df846bff250b53368e28c9a24'
DEFAULT_FLASH = os.path.join(RE, 'build', 'ptpdebug_385', 'FPUPDATE.DAT')   # what the test camera has in flash

B1_FILE, B1_BASE = 0x10025c, 0x774000                              # LZ-compressed in the file
B2_FILE, B2_BASE = 0x24025c, 0xe0ec80
LOADER_FILE, LOADER_LEN = 0x4025c, 0x40000                         # stock boot loader (RAM 0)
SEC0_FILE, SEC0_LEN = 0x8025c, 0xd7a0                              # section 0 (RAM 0x40000)
DB_FILE, DB_LEN, DB_RAM = 0xae025c, 0xb3700, 0x40d3b580            # tuning area: value(ID) = DB[ID]
# menu modules: plain in the file, streamed to RAM later; (file offset, RAM base, length, first init function)
MODULES = {0x41: (0x46025c, 0x1420000, 0x9a9a0, 0x1430170),        # menu screens
           0x44: (0x60025c, 0x15c0000, 0xe0000, 0x15c05ec)}        # playback / RAW-conversion request builder


class Firmware:
    def __init__(self, path, flash=DEFAULT_FLASH):
        raw = open(path, 'rb').read()
        if hashlib.sha256(raw).hexdigest() != OFFICIAL_SHA256:
            sys.exit(f'{path}: not the official X-Pro1 3.82 FPUPDATE.DAT (SHA-256 mismatch). Nothing written.')
        self.path, self.flash_path = path, flash
        self.img = bytes(x ^ 0xff for x in raw)                    # the file stores the payload bit-inverted
        self._b1 = self._b2 = self._flash = None
        assert hashlib.sha256(self.loader).hexdigest() == LOADER_SHA256, 'boot loader differs from 3.82'

    # ---- images
    def _unlz(self, at):
        size, packed = struct.unpack('<II', self.img[at:at + 8])
        return _lz.lz_decode(self.img, at + 20, at + packed, size)

    @property
    def blob1(self):
        if self._b1 is None: self._b1 = self._unlz(B1_FILE)
        return self._b1

    @property
    def blob2(self):
        if self._b2 is None: self._b2 = self._unlz(B2_FILE)
        return self._b2

    def module(self, m):
        f, _, n, _ = MODULES[m]
        return self.img[f:f + n]

    loader = property(lambda s: s.img[LOADER_FILE:LOADER_FILE + LOADER_LEN])
    section0 = property(lambda s: s.img[SEC0_FILE:SEC0_FILE + SEC0_LEN])
    tuning = property(lambda s: s.img[DB_FILE:DB_FILE + DB_LEN])
    ffsys = property(lambda s: s.img[0x25c:0x25c + 512])

    @property
    def flash_img(self):
        """Decoded image of the firmware in the camera's flash (the card's tuning hooks expect its values)."""
        if self._flash is None:
            if not os.path.exists(self.flash_path):
                sys.exit(f'{self.flash_path}: flashed firmware file not found (--flash).')
            self._flash = bytes(x ^ 0xff for x in open(self.flash_path, 'rb').read())
        return self._flash

    @property
    def flash_tuning(self):
        return self.flash_img[DB_FILE:DB_FILE + DB_LEN]

    # ---- words by RAM address
    def _where(self, addr):
        for data, base in ((self.blob1, B1_BASE), (self.blob2, B2_BASE)):
            if base <= addr < base + len(data): return data, base
        for f, base, n, _ in MODULES.values():
            if base <= addr < base + n: return self.img[f:f + n], base
        raise ValueError(f'{addr:#x}: not in blob1, blob2 or a known module')

    def word(self, addr):
        data, base = self._where(addr)
        return struct.unpack_from('<I', data, addr - base)[0]

    def words(self, addr, n):
        return [self.word(addr + 4 * i) for i in range(n)]

    def expect(self, addr, old, what=''):
        """Refuse to plan a change to a word that is not the expected stock word."""
        got = self.word(addr)
        if got != old:
            raise AssertionError(f'{addr:#x}{" (" + what + ")" if what else ""}: stock word {got:#010x}, expected {old:#010x}')
