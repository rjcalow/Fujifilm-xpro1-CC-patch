"""Film simulations the converter can add, one record each (ADDING_FILM_SIMS.md §1 lists the free numbers).

Three kinds:
  * a **look** of its own (Classic Chrome, Superia 400): its own MODE_FSIM and colour mode, rendered by looks.py;
  * a **recipe** (Reggie's Portra, Kodachrome II): a menu entry that renders with a base film simulation's
    MODE_FSIM and overrides white balance shift, Color, Highlight, Shadow and Sharpness for the picture
    (recipes.py). It needs no MODE_FSIM of its own: the converter tells it apart by the stored menu value.
Superia 400 and the two recipes come from PR #3 (simonjardine, public/FOUR_LOOKS.md), adapted to the SD card.

Names: the first entry (row 10) uses a repointed UI text ID (texts.py, all 35 languages); further rows are drawn
from an ASCII string by menus.py (as PR #3 does; the same string in every language). Icons reuse icon text IDs.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FilmSim:
    key: str                  # command-line name
    name: str                 # menu text, ASCII, at most 15 characters
    mode_fsim: int            # MODE_FSIM it renders with (own number for a look, the base's for a recipe)
    stored: int               # value saved for setting 0x3d (4 bits; stock uses 0-7, 11, 12)
    row: int                  # FILM SIMULATION menu row (stock rows 0..9)
    icon_ab: tuple            # icon text IDs for the two FILM SIMULATION records (pop-up list, menu line)
    name_id: int = None       # row 10 only: UI text ID repointed to `name`
    icon_id: int = None       # row 10 only: UI text ID repointed to `icon`
    icon: str = None          # row 10 only: glyph for icon_id (must exist in the X-Pro1 font)
    rawconv_code: int = None  # RAW CONVERSION film code (Classic Chrome: 8, as the X-E2)
    colour_mode: int = None   # look only: colour mode for mode_fsim (blob2 table 0xf396b0)
    look: dict = None         # look only, beyond Classic Chrome: how its colour mode borrows stock data (looks.py)
    recipe: dict = field(default=None, compare=False)   # recipe only: overrides (recipes.py)

    @property
    def is_recipe(self): return self.recipe is not None


CLASSIC_CHROME = FilmSim(
    key='classic_chrome', name='CLASSIC CHROME', mode_fsim=6, stored=13, row=10, icon_ab=(1215, 1215),
    name_id=819, icon_id=1215, icon='', rawconv_code=8, colour_mode=1)

# PR #3's Superia 400: ASTIA's 3x3 matrices, PRO Neg. Std's tone, PROVIA's 2x2 / detail / chroma gain / H-S family.
# (PR #3 also boosts the 2x2 by 4 % / 12 %; that needs a second 2x2 preset and selector and is left out for now.)
SUPERIA = FilmSim(
    key='superia', name='SUPERIA 400', mode_fsim=2, stored=14, row=11, icon_ab=(809, 808),    # ASTIA's icons
    colour_mode=8, look=dict(idx3=2, idx2=0, family=3, code=0xfc))     # 3x3 index of ASTIA, tone of PRO Neg. Std

# PR #3's recipes, values in the camera's native encodings (wb 0 = AUTO; color/hi/lo/sharp = conversion-table codes)
REGGIE = FilmSim(
    key='reggie', name="REGGIE'S PORTRA", mode_fsim=6, stored=15, row=12, icon_ab=(1215, 1215),   # on Classic Chrome
    recipe=dict(wb=0, red=2, blue=-4, color=7, hi=3, lo=3, sharp=0))
KODACHROME = FilmSim(
    key='kodachrome', name='KODACHROME II', mode_fsim=11, stored=10, row=13, icon_ab=(822, 821),    # on PRO Neg. Std
    recipe=dict(wb=0, red=1, blue=-2, color=9, hi=1, lo=0, sharp=4))

SIMS = {s.key: s for s in (CLASSIC_CHROME, SUPERIA, REGGIE, KODACHROME)}
FOUR_LOOKS = [CLASSIC_CHROME, SUPERIA, REGGIE, KODACHROME]

STOCK = {
    'mode_fsim': {0, 1, 3, 5, 7, 8, 9, 10, 11, 12},
    'stored': {0, 1, 2, 3, 4, 5, 6, 7, 11, 12},
    'row': set(range(10)),
    'rawconv_code': {0, 3, 5, 6, 7},
}


def validate(sims):
    seen = {}
    rows = sorted(s.row for s in sims)
    assert rows == list(range(10, 10 + len(sims))), 'new rows must follow the stock ones: 10, 11, ...'
    looks = {s.mode_fsim for s in sims if not s.is_recipe}
    for s in sims:
        assert len(s.name) <= 15 and s.name.isascii(), f'{s.key}: name must be ASCII, at most 15 characters'
        assert 0 <= s.mode_fsim <= 12, f'{s.key}: MODE_FSIM 13+ needs three firmware range checks widened'
        assert 0 <= s.stored <= 15
        if s.row == 10:
            assert s.name_id and s.icon_id and s.icon and len(s.icon) == 1, 'row 10 uses repointed text IDs'
        if s.is_recipe:
            assert s.mode_fsim in STOCK['mode_fsim'] | looks, f'{s.key}: base MODE_FSIM {s.mode_fsim} not available'
            fields = ('mode_fsim', 'stored', 'row')
        else:
            assert s.mode_fsim not in STOCK['mode_fsim'], f'{s.key}: MODE_FSIM {s.mode_fsim} is a stock one'
            fields = ('mode_fsim', 'stored', 'row', 'rawconv_code')
        for f in fields:
            v = getattr(s, f)
            if v is None or (f == 'mode_fsim' and s.is_recipe): continue
            assert v not in STOCK.get(f, ()), f'{s.key}: {f} {v} is used by a stock film simulation'
            assert (f, v) not in seen, f'{s.key}: {f} {v} also used by {seen[(f, v)]}'
            seen[(f, v)] = s.key
