#!/usr/bin/env python3
"""Convert the official X-Pro1 3.82 firmware into an SD-boot card with extra film simulations.

    ~/.venvs/xpro1-re/bin/python re/classic_chrome/convert.py FPUPDATE.DAT OUTDIR [options]

Default: Classic Chrome as an 11th film simulation, with its own look, in the shooting menu and the playback RAW
CONVERSION menu, green menu accent. Output: OUTDIR/ffsys.bin, OUTDIR/ffboot.bin (card root) and OUTDIR/README.md.

options:
  --lineup KEYS      the new entries, comma-separated, in menu order (rows 10, 11, ...); every menu (shooting
                     menu and its line, RAW CONVERSION) and every firmware number is generated from it
                     (config/film_sims.py: lineup). At most 6 entries, at most 3 of them looks. --list shows the keys.
  --sim KEY / --add KEYS   older form: --lineup KEY,KEYS (default classic_chrome)
  --peaking          stronger white focus peaking (PR #3: HIGH gain 64 → 120)
  --four-looks       = --lineup classic_chrome,superia,reggie,kodachrome --peaking
  --look own|borrow  own: Classic Chrome data of its own, PRO Neg. Hi back to stock (default)
                     borrow: use PRO Neg. Hi's slot, which the flashed v2 fills with Classic Chrome data
  --no-rawconv       leave the RAW CONVERSION menu stock (default: every entry gets a row; a recipe converts with its base)
  --no-green         keep the stock red menu accent
  --flash FILE       firmware in the camera's flash (default re/build/ptpdebug_385/FPUPDATE.DAT, the v2 build)
  --stub FILE        boot stub (default re/work/chain/chain_crumbs.bin; build: re/sdchain/build.sh)
  --list             list the film simulations and features
  --verify           after building, run the emulator checks and the known-good comparison (verify.py)

Package re/classic_chrome/: engine/ (firmware input, patch engine, SD-boot chain, run-time hooks, card files),
config/ (film simulations, tuning values), features/ (menus, RAW conversion, texts, looks), validate/ (emulator
checks and known-good builds; run them with --verify or verify.py).
Nothing is flashed; the card runs everything in RAM. Recipe for more film simulations: FINDINGS.md §9.
"""
import hashlib, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))   # re/
from classic_chrome.engine.firmware import Firmware, DEFAULT_FLASH
from classic_chrome.engine.card import Card
from classic_chrome.engine import sdcard
from classic_chrome.config.film_sims import SIMS, FOUR_LOOKS, lineup
from classic_chrome.features.menus import FilmSimMenu
from classic_chrome.features.rawconv import RawConversion
from classic_chrome.features.looks import LOOKS
from classic_chrome.features.recipes import Recipes
from classic_chrome.features.peaking import Peaking

FEATURES = {'menu': 'FILM SIMULATION entry in the shooting menu (+ shooting-menu line)',
            'rawconv': 'row in the playback RAW CONVERSION menu',
            'look': 'own look data (or borrowed from PRO Neg. Hi)',
            'green': 'green menu accent',
            'recipes': 'recipe entries: base film simulation + WB shift, Color, Highlight, Shadow, Sharpness',
            'peaking': 'stronger white focus peaking'}


def opt(args, name, default=None):
    if name in args:
        k = args.index(name); v = args[k + 1]; del args[k:k + 2]; return v
    return default


def flag(args, name):
    if name in args: args.remove(name); return True
    return False


def lineup_keys(opts):
    """(keys, peaking) from converter options (used by verify.py too)."""
    o = list(opts)
    val = lambda name, default: o[o.index(name) + 1] if name in o else default
    four = '--four-looks' in o
    if '--lineup' in o: keys = [k for k in val('--lineup', '').split(',') if k]
    elif four: keys = list(FOUR_LOOKS)
    else: keys = [val('--sim', 'classic_chrome')] + [k for k in val('--add', '').split(',') if k]
    return keys, four or '--peaking' in o


def build_card(sims, look, rawconv, peaking):
    from classic_chrome.features.looks import OwnLook, BorrowLook
    cc = next((s for s in sims if s.own_data), None)
    extras = [s for s in sims if not s.is_recipe and not s.own_data]
    if look == 'borrow':
        assert cc and not extras, '--look borrow: Classic Chrome only, no other looks'
        lk = BorrowLook(cc)
    else:
        lk = OwnLook(cc, extras) if (cc or extras) else None
    menu = FilmSimMenu(sims)
    recipes = [s for s in sims if s.is_recipe]
    parts = ([RawConversion(sims, menu)] if rawconv else []) + ([Recipes(recipes)] if recipes else []) \
        + ([Peaking()] if peaking else [])
    return Card(menu, parts, lk)


def main(args):
    if flag(args, '--list'):
        print('film simulations:')
        for s in SIMS.values():
            how = f'recipe on {s.base}' if s.is_recipe else ('look (own data)' if s.own_data else 'look (borrowed selections)')
            print(f'  {s.key:16} {s.name:16} {how}')
        print('numbers for the four-looks line-up (assigned by config.lineup):')
        for s in lineup(FOUR_LOOKS):
            print(f'  row {s.row}  {s.key:16} stored {s.stored:2}  MODE_FSIM {s.mode_fsim:2}  RAW code {s.rawconv_code}'
                  + (f'  colour mode {s.colour_mode}' if s.colour_mode is not None else ''))
        for k, v in FEATURES.items(): print(f'  feature {k:8} {v}')
        return
    look = opt(args, '--look', 'own')
    flash = opt(args, '--flash', DEFAULT_FLASH); stub = opt(args, '--stub', sdcard.STUB_DEFAULT)
    rawconv = not flag(args, '--no-rawconv'); green = not flag(args, '--no-green'); verify = flag(args, '--verify')
    keys, peaking = lineup_keys(sys.argv[1:])
    for name in ('--lineup', '--add', '--sim'): opt(args, name)
    flag(args, '--four-looks'); flag(args, '--peaking')
    opts = [a for a in sys.argv[1:] if (a not in args or a.startswith('--')) and a not in ('--verify',)]
    if len(args) != 2 or look not in LOOKS: sys.exit(__doc__)
    src, out = args
    try:
        sims = lineup(keys)
    except AssertionError as e:
        sys.exit(f'line-up {keys}: {e}')

    fw = Firmware(src, flash)
    card = build_card(sims, look, rawconv, peaking)
    files, info = sdcard.build(fw, card, green=green, stub_path=stub)

    os.makedirs(out, exist_ok=True)
    sums = []
    for n, b in files.items():
        open(os.path.join(out, n), 'wb').write(b); h = hashlib.sha256(b).hexdigest(); sums.append(f'    {h}  {n}')
        print(f'wrote {n} {len(b)} bytes sha256 {h}')
    e = info['extra']
    print(f"card: {e['markers']} blob1 words, module words {e['module_words']}, {e['blob2_words']} blob2 words, "
          f"filler {e['filler'][0]:#x}-{e['filler'][1]:#x}")
    feats = [f"{', '.join(s.name for s in sims)} in the shooting menu", f"look: {look}"] \
        + (['all of them in RAW CONVERSION'] if rawconv else []) + (['white focus peaking'] if peaking else []) \
        + (['green menu accent'] if green else [])
    open(os.path.join(out, 'README.md'), 'w').write(f'''# SD dual-boot card: {", ".join(feats)}

Built with `re/classic_chrome/convert.py FPUPDATE.DAT OUTDIR{''.join(' ' + a for a in opts)}` from the official
X-Pro1 3.82 FPUPDATE.DAT. Expects the camera's flash to hold `{os.path.basename(os.path.dirname(flash))}/FPUPDATE.DAT`
(the v2 build with USB debug); the card checks its tuning values before every write.

{chr(10).join(sums)}

Use: FAT32 card, copy both .bin files to the root, `sync`, check the sha256 sums, unmount.
Battery out and in, hold **Fn + press the command dial** while switching on. Nothing is written to flash.
Before booting without the card, select a stock film simulation in the shooting menu.
''')


    if verify:
        from classic_chrome import verify as V
        print('verifying ...')
        if not V.run(src, out, opts, flash): sys.exit(1)


if __name__ == '__main__':
    main(sys.argv[1:])
