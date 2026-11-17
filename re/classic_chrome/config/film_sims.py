"""Film simulations the converter can add, one record each.

A new film simulation needs a fresh value in every field (ADDING_FILM_SIMS.md §1 lists what is free and why).
Stock values are in STOCK so `validate()` can refuse clashes before anything is built.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class FilmSim:
    key: str            # command-line name
    name: str           # menu text (ASCII, at most 15 characters: one 0x20-byte UTF-16 slot, texts.py)
    icon: str           # one glyph that exists in the X-Pro1 font (e.g. U+F2B9, the X-E2 Classic Chrome icon)
    mode_fsim: int      # firmware film-simulation number (MODE_FSIM, 0..12; free: 2, 4, 6)
    stored: int         # value saved for setting 0x3d (4 bits; free: 8, 9, 10, 13, 14, 15)
    row: int            # FILM SIMULATION menu row (stock rows 0..9)
    name_id: int        # UI text IDs repointed to `name` / `icon` (must be unused in all 35 languages)
    icon_id: int
    rawconv_code: int   # film code stored by the RAW CONVERSION menu (stock 0, 3, 5, 6, 7; X-E2: 8 = Classic Chrome)
    colour_mode: int    # colour mode the image pipeline uses for mode_fsim (table blob2 0xf396b0)


CLASSIC_CHROME = FilmSim(
    key='classic_chrome', name='CLASSIC CHROME', icon='',
    mode_fsim=6, stored=13, row=10, name_id=819, icon_id=1215, rawconv_code=8, colour_mode=1)

SIMS = {s.key: s for s in (CLASSIC_CHROME,)}

STOCK = {   # values the ten stock film simulations use
    'mode_fsim': {0, 1, 3, 5, 7, 8, 9, 10, 11, 12},
    'stored': {0, 1, 2, 3, 4, 5, 6, 7, 11, 12},
    'row': set(range(10)),
    'rawconv_code': {0, 3, 5, 6, 7},
}


def validate(sims):
    seen = {}
    for s in sims:
        assert len(s.name) <= 15 and s.name.isascii(), f'{s.key}: name must be ASCII, at most 15 characters'
        assert len(s.icon) == 1 and 0xe000 <= ord(s.icon) < 0xf900, f'{s.key}: icon must be one private-use glyph'
        assert 0 <= s.mode_fsim <= 12, f'{s.key}: MODE_FSIM 13+ needs three firmware range checks widened'
        assert 0 <= s.stored <= 15 and s.rawconv_code <= 0xff
        for f in ('mode_fsim', 'stored', 'row', 'rawconv_code', 'name_id', 'icon_id'):
            v = getattr(s, f)
            assert v not in STOCK.get(f, ()), f'{s.key}: {f} {v} is used by a stock film simulation'
            assert (f, v) not in seen, f'{s.key}: {f} {v} also used by {seen[(f, v)]}'
            seen[(f, v)] = s.key
