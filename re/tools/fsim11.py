"""Compatibility module: the names of the former tools/fsim11.py, served from the converter package
(re/classic_chrome/), for scripts written against it (re/tools/four_looks.py, PR #3).

The SD card is built by re/classic_chrome/convert.py; nothing here builds a card. Values are taken from the feature
modules (menus.py, film_sims.py) so they cannot drift; the module-0x41 list keeps the old 'A' / 'B' placeholders
for the two copied icon tables.
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, os.path.join(HERE, '..', '..', 'public'))
from classic_chrome.engine import card as _card
from classic_chrome.engine.firmware import B1_BASE, B2_BASE, MODULES
from classic_chrome.config.film_sims import CLASSIC_CHROME as _SIM
from classic_chrome.features import menus as _m, looks as _l, texts as _t

END = _card.END
ROW10 = _m.CONV + 12 * _SIM.row
NODES = _m.NODES
STOCK_ROWS = _m.STOCK_ROWS
SITE_INIT, BLX_R3 = _card.SITE_INIT, _card.BLX_R3
SITE_B2, START_B2 = _card.SITE_B2, _card.START_B2
M41_FILE, M41_BASE, _, MOD41_INIT = MODULES[0x41]
NAME_ID, ICON_ID = _SIM.name_id, _SIM.icon_id
ICON_SRC = {k: src for k, (src, _) in _m.ICON_TABS.items()}
FSIM2CM, CM_OLD, CM_NEW = _l.FSIM2CM + 4 * (_SIM.mode_fsim - 1), _SIM.colour_mode, _l.BorrowLook.CM_NEW
MOD41 = ([(_m.NAME_TAB + 4 * _SIM.row, 0, NAME_ID), (_m.ROW_CAP, 0xe3540009, 0xe3540000 | _SIM.row)]
         + [(f, src, k) for k, (src, fields) in _m.ICON_TABS.items() for f in fields]
         + [(0x1474e80, 0x05000905, 0x050a0905), (0x1474e40, 0x05000905, 0x050a0905)])   # fsim 6 → row 10
TEXTS = {NAME_ID: _SIM.name, ICON_ID: _SIM.icon}


def lang(img):
    """(entries, tail template) for the language hook: text 819 / 1215 in all 35 languages (as before)."""
    class _Fw: pass
    fw = _Fw(); fw.img = img
    return _t.lang(fw, TEXTS)


def check(img):
    """The stock words the 11th entry changes, checked in a decoded 3.82 image; returns (blob1, blob2, module 0x41)."""
    import xpro1_cc_patch as P
    w = lambda b, base, a: struct.unpack_from('<I', b, a - base)[0]
    u1, p1 = struct.unpack('<II', img[0x10025c:0x100264]); b1 = P.lz_decode(img, 0x10025c + 20, 0x10025c + p1, u1)
    u2, p2 = struct.unpack('<II', img[0x24025c:0x240264]); b2 = P.lz_decode(img, 0x24025c + 20, 0x24025c + p2, u2)
    m41 = img[M41_FILE:M41_FILE + MODULES[0x41][2]]
    assert [w(b1, B1_BASE, ROW10 + 4 * i) for i in range(3)] == [END] * 3, 'row 10 not empty'
    for a, lst in NODES:
        assert w(b1, B1_BASE, a) == lst
        assert [w(b1, B1_BASE, lst + 4 * i) for i in range(22)] == sum(([r, 0] for r in STOCK_ROWS + [END]), [])
    assert w(b1, B1_BASE, SITE_INIT) == BLX_R3
    assert w(m41, M41_BASE, M41_BASE) == MOD41_INIT and w(m41, M41_BASE, M41_BASE + 4) == 0, 'module 0x41 init list'
    for a, old, _ in MOD41: assert w(m41, M41_BASE, a) == old, hex(a)
    assert w(b2, B2_BASE, FSIM2CM) == CM_OLD
    return b1, b2, m41
