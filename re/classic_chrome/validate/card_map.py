"""Addresses and expected values of the Classic Chrome card, for the emulator checks (emu_card.py, emu_look.py).

Taken from the feature modules, so the checks follow the code that builds the card. Module-level constants are
image-independent; for_image(img) adds the ones that need the stock image (module 0x41 words, language entries).
"""
import struct
from types import SimpleNamespace
from classic_chrome.engine import card as _card
from classic_chrome.engine.firmware import B2_BASE, MODULES
from classic_chrome.config.film_sims import lineup
SIM = lineup(['classic_chrome'])[0]
from classic_chrome.features import menus as _m, rawconv as _r, looks as _l, texts as _t

END = _card.END
SITE_INIT, SITE_B2, START_B2 = _card.SITE_INIT, _card.SITE_B2, _card.START_B2
M41_FILE, M41_BASE, _, MOD41_INIT = MODULES[0x41]
M44_FILE, M44_BASE, _, MOD44_INIT = MODULES[0x44]
ROW10 = _m.CONV + 12 * SIM.row
STOCK_ROWS = _m.STOCK_ROWS
NAME_ID, ICON_ID = SIM.name_id, SIM.icon_id
FSIM2CM, CM_OLD = _l.FSIM2CM + 4 * (SIM.mode_fsim - 1), SIM.colour_mode
RC_NODE, RC_ROWS, RC_CODES = _r.NODE, _r.ROWS, _r.CODES
RC_NAME_TAB, RC_ICON_TAB, RC_ICON_FIELD = _r.NAME_TAB, _r.ICON_TAB, _r.ICON_FIELD
RC_CAP, RC_MOVW, RC_MOVT = _r.CAP, _r.MOVW, _r.MOVT
RC_APPLY, RC_CUR = _r.APPLY, _r.CUR
RC_M44, RC_M44_CONT, RC_M44_REQ = _r.M44, _r.M44_CONT, _r.M44_REQ


def for_image(img):
    """Namespace with the constants above plus MOD41 (address, stock, new or 'A'/'B' for the copied icon tables)
    and lang(img) (language-hook entries), for the image the card is built from."""
    m41 = img[M41_FILE:M41_FILE + MODULES[0x41][2]]
    w = lambda a: struct.unpack_from('<I', m41, a - M41_BASE)[0]
    mod41 = [(_m.NAME_TAB + 4 * SIM.row, 0, SIM.name_id), (_m.ROW_CAP, 0xe3540009, 0xe3540000 | SIM.row)]
    for k, (src, fields) in _m.ICON_TABS.items(): mod41 += [(f, src, k) for f in fields]
    for t in _m.ROW_MAPS:
        a = (t + SIM.mode_fsim) & ~3; k = (t + SIM.mode_fsim) & 3; old = w(a)
        mod41.append((a, old, old & ~(0xff << 8 * k) | SIM.row << 8 * k))
    ns = SimpleNamespace(**{k: v for k, v in globals().items() if k.isupper()})
    ns.MOD41 = mod41
    ns.lang = lambda image: _t.lang(SimpleNamespace(img=image), {SIM.name_id: SIM.name, SIM.icon_id: SIM.icon})
    return ns
