"""SD dual-boot output: ffsys.bin + ffboot.bin for the card root (same container as tools/build_sdchain.py --crumbs).

ffboot.bin = the boot stub (re/sdchain, built to re/work/chain/chain_crumbs.bin) + the stock boot loader with the
SD-boot chain patched in (chain.py: power-on fix, Ver3.89 EXIF marker, optional green UI accent, stage B),
the run-time hooks for tuning values and texts (hooks.py), and the card engine's tables and hooks (card.py).
The camera boots it with Fn + command-dial press at power-on; flash is never written.
"""
import hashlib, os, struct, zlib
from classic_chrome.engine.firmware import RE, FFSYS_SHA256
from classic_chrome.engine import chain

STUB_DEFAULT = os.path.join(RE, 'work', 'chain', 'chain_crumbs.bin')
STUB_SHA256 = '19069ea86759aa2dcd7a6a3eeaa15f516ce5778d34a4ad8e3fd92141e15c519d'   # camera-tested build


def build(fw, card, green=True, stub_path=STUB_DEFAULT):
    """Returns ({'ffsys.bin': bytes, 'ffboot.bin': bytes}, info)."""
    from classic_chrome.features.texts import lang
    card.check(fw)
    stub = open(stub_path, 'rb').read()
    if hashlib.sha256(stub).hexdigest() != STUB_SHA256:
        print(f'note: boot stub {stub_path} is not the camera-tested build')
    assert struct.pack('<2I', 0xfff44024, 0xfff44028) in stub, 'needs the chain_crumbs.bin stub (-DCRUMBS)'

    L = bytearray(fw.loader)

    def extra(L, asm, bl):                           # card engine after cchook's hooks, in the free filler
        used = max(i for i in range(0xa400, 0xc000) if L[i] != 0xff)
        return card.install(L, asm, bl, used + 1)

    info = chain.patch(L, fw.section0, uiswap=green, cc_img=fw.img, extra=extra,
                        cc_lang=lang(fw, card.texts()), cc_db=card.tuning(fw))
    loader = bytes(L)

    c = zlib.compressobj(9, zlib.DEFLATED, -15, 9); payload = c.compress(loader) + c.flush()
    st = bytearray(stub)
    m = bytes(st).find(struct.pack('<I', 0x4e494843)); cfg = m - 0x14
    assert m > 0 and bytes(st).count(struct.pack('<I', 0x4e494843)) == 1 and st[cfg:m] == bytes(20), 'stub config block'
    st += bytes(-len(st) % 4)
    off = len(st); total = off + len(payload); total += -total % 4
    struct.pack_into('<5I', st, cfg, total, off, len(payload), len(loader), zlib.crc32(loader) & 0xffffffff)
    ffboot = bytes(st) + payload + bytes(total - off - len(payload))
    assert len(ffboot) < 0x10000, f'ffboot {len(ffboot)} bytes: the boot ROM reads only 16 bits of the length'

    ffsys = bytearray(fw.ffsys)
    assert hashlib.sha256(ffsys).hexdigest() == FFSYS_SHA256
    ffsys[16:20] = struct.pack('<I', 0x301)          # parameter block: boot from SD
    return {'ffsys.bin': bytes(ffsys), 'ffboot.bin': ffboot}, info
