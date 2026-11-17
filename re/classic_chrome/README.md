# Classic Chrome converter (SD-boot card)

`convert.py` turns the official X-Pro1 3.82 `FPUPDATE.DAT` into an SD dual-boot card that adds film simulations
to the camera, with the menus corrected. The card patches the camera's RAM at every boot; **nothing is written to
flash**. It is the base for further firmware changes: each change is a separate module.

```
~/.venvs/xpro1-re/bin/python re/classic_chrome/convert.py FPUPDATE.DAT out/ --verify   # Classic Chrome, checked
~/.venvs/xpro1-re/bin/python re/classic_chrome/convert.py --list                  # film simulations and features
```

Default output (camera-confirmed 2026-11-15, ffboot `6693177b…`): CLASSIC CHROME as an 11th FILM SIMULATION entry
with the X-E2 icon and name, its own look data (PRO Neg. Hi back to stock), shown on the shooting-menu line and in
the playback RAW CONVERSION menu, green menu accent. Options: `--look borrow`, `--no-rawconv`, `--no-green`,
`--flash FILE`, `--stub FILE` (see `convert.py`). The card expects the camera's flash to hold the v2 build
`re/build/ptpdebug_385` and checks its tuning values before every write.

Copy `ffsys.bin` and `ffboot.bin` to the root of a FAT32 card, `sync`, check the sums, unmount. Boot: battery out and
in, hold **Fn + press the command dial** while switching on.

## Layout

| Part | Files | Job |
|---|---|---|
| command line | `convert.py`, `verify.py` | build a card (`--verify` checks it); check any built card |
| **engine** | `engine/firmware.py` | reads the official file (refuses anything else): blob1, blob2, modules, words by RAM address |
| | `engine/card.py` | patch engine: collects every feature's changes, writes the run-time tables and hooks |
| | `engine/chain.py` | SD-boot chain in the stock loader: power-on fix, EXIF marker, green accent, stage B (camera-tested) |
| | `engine/hooks.py` | run-time hooks for tuning values and texts (camera-tested) |
| | `engine/sdcard.py` | card files: stub + patched loader → `ffboot.bin`, `ffsys.bin` |
| **config** | `config/film_sims.py` | one `FilmSim` record per added film simulation; clash check against the stock ones |
| | `config/cc_values.py` | Classic Chrome v3 tuning values (2x2 chroma matrix) |
| **features** (menu/UI hooks, look) | `features/menus.py` | shooting menu: FILM SIMULATION entry, icon, row limit, shooting-menu line |
| | `features/rawconv.py` | playback RAW CONVERSION menu: row, name, icon, film code, module 0x44 mapping |
| | `features/texts.py` | menu texts in all 35 languages (unused text IDs repointed) |
| | `features/looks.py`, `cc_look.py` | how the new film simulation renders: own Classic Chrome data, or PRO Neg. Hi's slot |
| **validate** | `validate/emu_chain.py`, `emu_card.py`, `emu_look.py` | emulator checks with the real firmware code (unicorn) |
| | `validate/card_map.py` | the addresses and values the checks expect, taken from the feature modules |
| | `validate/regression.py` | known-good builds by options |

`re/tools/` keeps the research and live (USB) tools. The old names `tools/crumbs.py` and `tools/cchook.py` still
import (they point here), so `romdump/`, `build_sdchain.py` and the live tools are unchanged; `tools/cclook.py` is
the live test of the own look, using `features/cc_look.py`. The data and research notes in this folder
(`CLASSIC_CHROME.md`, `cc_port_data.json`, …) describe the Classic Chrome port itself.

## How a module plugs in

A feature is an `engine.card.Part`. It checks the stock words it will change (`check`), reserves room for its own data and
stubs (`allocate`, `write`) and returns its changes sorted by where they live; the engine turns them into tables
that the card applies at the right moment, each entry only if the stock word is still there:

| Method | Lives in | Applied |
|---|---|---|
| `markers()` | blob1 (tables, menu lists, pointers) | stage B, before blob1 runs |
| `module_words()` | menu modules 0x41 / 0x44 | just before the module's first init runs |
| `blob2_words()` | blob2 (pipeline code, tables) | before blob2 starts |
| `texts()` | language blocks | every time a language block is loaded |
| `tuning(fw)` (look) | tuning area | every time the tuning area is loaded |

A new menu (Q menu, bracketing, …) is a new `Part` (in `features/`) added to `Card(base, extensions, look)` in `convert.py`. A new
film simulation is a new `FilmSim` in `config/film_sims.py` plus its look; the steps, free numbers and checks are in
`re/FINDINGS.md` §9 and `re/ADDING_FILM_SIMS.md`. Known limits, each asserted in the code: one new film simulation
per card (row 10 is the only free menu row; a second needs the setting table moved), at most three repointed texts
(`features/texts.py`), and `OwnLook` holds Classic Chrome's data only.

## Checks before a card goes on the camera

1. `convert.py FPUPDATE.DAT OUT --verify` (or `verify.py FPUPDATE.DAT OUT [options]` for a card built earlier):
   the three emulator checks and the known-good comparison must end with ALL OK. Known builds
   (`validate/regression.py`): default `6693177b…` (camera-confirmed), `--no-rawconv` `8d8364dc…`,
   `--look borrow` `127c321c…`, `--no-green` `b8547c4b…`. A change meant to alter a card updates them (and NOTES.md);
   a new feature gets its own option, off until camera-tested, and its own checks in `validate/`.
2. Card write: copy, `sync`, unmount, remount, re-check sums, unmount.
