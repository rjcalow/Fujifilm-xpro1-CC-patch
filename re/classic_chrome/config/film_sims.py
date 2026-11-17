"""Film simulations the converter can add, and the line-up that puts them on a card.

A record describes only the film simulation itself. The numbers the firmware needs (menu row, stored menu value,
MODE_FSIM, colour mode, RAW CONVERSION film code) are assigned by `lineup()` from the free pools, so a card is
just an ordered list of keys and every menu is generated from it:

    lineup(['classic_chrome', 'superia', 'reggie', 'kodachrome'])

Kinds:
  * look: renders differently, needs one of the three spare MODE_FSIMs (2, 4, 6) and a colour mode. Classic Chrome
    has data of its own (looks.OwnLook, colour mode 1, MODE_FSIM 6); other looks borrow stock selections
    (`look` = 3x3 index, 2x2 index, tone family and tone code) and get colour mode 8, then 9.
  * recipe: renders with a base film simulation (a look in the line-up or a stock one) and overrides white balance
    shift, Color, Highlight, Shadow and Sharpness for the picture (recipes.py). Needs no MODE_FSIM.

Capacity (FINDINGS.md §11): 16 stored menu values (stock uses 10) → at most 6 new entries; MODE_FSIM 0–12 with 2, 4,
6 spare → at most 3 looks; colour modes 1, 8, 9.

Names: an entry with text IDs (Classic Chrome: 819 / 1215 repointed in all 35 languages) uses them; the others are
drawn from their ASCII name (menus.py). Icons: Classic Chrome's own glyph (text 1215), the others borrow the icon of
a stock row (`icon_row`) in the shooting menu and in RAW CONVERSION alike.
Superia 400 and the two recipes come from PR #3 (simonjardine, public/FOUR_LOOKS.md).
"""
from dataclasses import dataclass, field, replace

STOCK_ROW = {'provia': 0, 'velvia': 1, 'astia': 2, 'pro_neg_std': 7, 'pro_neg_hi': 8, 'sepia': 9}   # menu rows
STOCK_FSIM = {'provia': 0, 'velvia': 3, 'astia': 1, 'pro_neg_std': 11, 'pro_neg_hi': 12, 'sepia': 5,
              'monochrome': 7}
STOCK_RAW_CODE = {0: 0, 3: 5, 1: 3, 11: 6, 12: 7}    # MODE_FSIM → RAW CONVERSION film code (PROVIA, Velvia, ASTIA, Neg)

# free pools, in the order they are handed out (Classic Chrome's numbers first: they are the camera-tested ones)
POOL_STORED = [13, 14, 15, 10, 9, 8]
POOL_FSIM_CC, POOL_FSIM = 6, [2, 4, 6]
POOL_CM = [8, 9]
POOL_RAW_CODE = list(range(8, 0x40))


@dataclass(frozen=True)
class FilmSim:
    key: str                  # command-line name
    name: str                 # menu text, ASCII, at most 15 characters
    kind: str                 # 'look' or 'recipe'
    icon_row: int = None      # stock menu row whose icons it borrows (None: own icon text, Classic Chrome)
    name_id: int = None       # Classic Chrome: UI text IDs repointed to `name` / `icon`
    icon_id: int = None
    icon: str = None          # glyph for icon_id (must exist in the X-Pro1 font)
    look: dict = None         # look borrowing stock selections: idx3, idx2, family, code (looks.py)
    recipe: dict = field(default=None, compare=False)   # recipe overrides (recipes.py)
    base: str = None          # recipe: key of a look in the line-up or of a stock film simulation
    # assigned by lineup()
    row: int = None
    stored: int = None
    mode_fsim: int = None
    colour_mode: int = None
    rawconv_code: int = None

    @property
    def is_recipe(self): return self.kind == 'recipe'

    @property
    def own_data(self): return self.key == 'classic_chrome'

    def icons(self, shooting_a, shooting_b, raw):
        """(icon A, icon B, RAW CONVERSION icon) text IDs, given the stock tables (10 entries each)."""
        if self.icon_row is None: return self.icon_id, self.icon_id, self.icon_id
        return shooting_a[self.icon_row], shooting_b[self.icon_row], raw[self.icon_row]


CLASSIC_CHROME = FilmSim(key='classic_chrome', name='CLASSIC CHROME', kind='look',
                         name_id=819, icon_id=1215, icon='')
# ASTIA's 3x3 matrices (index 2), PROVIA's 2x2 (0), PRO Neg. Std's tone (family 3, code 0xfc); PR #3's +4 % / +12 %
# 2x2 boost needs a second 2x2 preset and selector index and is left out for now
SUPERIA = FilmSim(key='superia', name='SUPERIA 400', kind='look', icon_row=STOCK_ROW['astia'],
                  look=dict(idx3=2, idx2=0, family=3, code=0xfc))
# recipe values in the camera's native encodings (wb 0 = AUTO; color / hi / lo / sharp = conversion-table codes)
REGGIE = FilmSim(key='reggie', name="REGGIE'S PORTRA", kind='recipe', base='classic_chrome',
                 recipe=dict(wb=0, red=2, blue=-4, color=7, hi=3, lo=3, sharp=0))
KODACHROME = FilmSim(key='kodachrome', name='KODACHROME II', kind='recipe', base='pro_neg_std',
                     icon_row=STOCK_ROW['pro_neg_std'], recipe=dict(wb=0, red=1, blue=-2, color=9, hi=1, lo=0, sharp=4))

SIMS = {s.key: s for s in (CLASSIC_CHROME, SUPERIA, REGGIE, KODACHROME)}
FOUR_LOOKS = ['classic_chrome', 'superia', 'reggie', 'kodachrome']


def lineup(keys):
    """The card's entries, in menu order, with every number assigned. Refuses what does not fit."""
    keys = list(keys)
    assert keys, 'empty line-up'
    assert len(set(keys)) == len(keys), 'a film simulation appears twice'
    unknown = [k for k in keys if k not in SIMS]
    assert not unknown, f'unknown film simulation(s) {unknown}; known: {sorted(SIMS)}'
    assert len(keys) <= len(POOL_STORED), f'at most {len(POOL_STORED)} new entries (16 stored menu values, 10 stock)'
    sims = [SIMS[k] for k in keys]
    looks = [s for s in sims if not s.is_recipe]
    assert len(looks) <= 3, 'at most 3 looks (MODE_FSIM 2, 4, 6 are the only spare ones)'
    assert sum(1 for s in looks if not s.own_data) <= len(POOL_CM), f'at most {len(POOL_CM)} borrowed looks'
    fsims = [f for f in POOL_FSIM if not (f == POOL_FSIM_CC and any(s.own_data for s in looks))]
    cms = list(POOL_CM); codes = list(POOL_RAW_CODE)
    out, by_key = [], {}
    for n, s in enumerate(sims):
        a = dict(row=10 + n, stored=POOL_STORED[n], rawconv_code=codes.pop(0))
        if not s.is_recipe:
            a['mode_fsim'] = POOL_FSIM_CC if s.own_data else fsims.pop(0)
            a['colour_mode'] = 1 if s.own_data else cms.pop(0)
        out.append(replace(s, **a)); by_key[s.key] = out[-1]
    for k, s in enumerate(out):                       # recipes render with their base's MODE_FSIM (and its icon)
        if not s.is_recipe: continue
        if s.base in by_key:
            assert not by_key[s.base].is_recipe, f'{s.key}: base {s.base} is a recipe'
            b = by_key[s.base]
            out[k] = replace(s, mode_fsim=b.mode_fsim,
                             **({} if s.icon_row is not None or b.icon_row is None and b.icon_id is None else
                                dict(icon_row=b.icon_row, icon_id=b.icon_id)))
        else:
            assert s.base in STOCK_FSIM, f'{s.key}: base {s.base} is neither in the line-up nor a stock film simulation'
            out[k] = replace(s, mode_fsim=STOCK_FSIM[s.base])
        assert out[k].icon_row is not None or out[k].icon_id is not None, f'{s.key}: no icon'
    named = [s for s in out if s.name_id]
    for s in out:
        assert len(s.name) <= 15 and s.name.isascii(), f'{s.key}: name must be ASCII, at most 15 characters'
        assert s.icon_id is None or s in named or any(n.icon_id == s.icon_id for n in named), \
            f'{s.key}: uses icon text {s.icon_id}, which only exists when its owner is in the line-up'
    return out
