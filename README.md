# Fujifilm X-Pro1: Classic Chrome patch and firmware research

This repository holds three things:

1. **A ROM dump card** in [`romdump/`](romdump/), for research. It starts the camera from an SD card with one extra
   read-only USB command, so you can copy the 16 KiB boot ROM to a PC. Nothing is written to the camera. How-to:
   [`romdump/README.md`](romdump/README.md).
2. **A Classic Chrome patch** for the X-Pro1 (firmware 3.82). It replaces the **PRO Neg. Hi** film simulation with
   Classic Chrome, using Fujifilm's own data from the X-E2. The script is in [`public/`](public/); full instructions
   are in [`public/README.md`](public/README.md).
   **New (SD boot, 2026-11-13):** Classic Chrome as its **own 11th film simulation**, with the X-E2's icon and name,
   keeping all ten stock ones. See [SD card: Classic Chrome as its own film simulation](#sd-card-classic-chrome-as-its-own-film-simulation).
3. **Reverse-engineering tools** in [`re/`](re/). They cover:
   - **SD dual boot:** start a modified firmware from the SD card without writing the camera's flash.
   - **USB debug firmware:** read and write camera memory from a PC.
   - **Live editing:** change image-processing parameters and UI colours while the camera runs.

> **Warning: unofficial, experimental, at your own risk.** Flashing modified firmware can brick a camera. Everything
> here has been tested on **one** camera. No Fujifilm firmware is distributed. You need your own copy of the official
> X-Pro1 3.82 `FPUPDATE.DAT` (SHA-256 `709e26f6dd77e922660010628fb20937b269be871b188b8810eb2cb4d5d33236`).

## Status

| Part | State |
|---|---|
| Classic Chrome patch **v2** (labelled 3.83) | **Flashed and working** on the test camera. In-camera RAW conversion uses it. The camera still reports Ver3.82 |
| SD dual boot | **Working** (2026-11-11). Firmware started from the card, photo EXIF "Ver3.89" (a marker only the SD-booted firmware writes). Used repeatedly since |
| SD card with Classic Chrome v3 + green UI (`--crumbs --uiswap --cc`) | **Working for colour** (2026-11-12): an in-camera RAW conversion from the SD-booted firmware matches the v3 values. Menu name and green accent after SD boot: emulator-checked, not yet confirmed on the camera |
| SD card: Classic Chrome as an **11th FILM SIMULATION entry** (`--crumbs --uiswap --cc --fsim11`) | **Working** (2026-11-13): entry with the X-E2 icon + CLASSIC CHROME below SEPIA, selectable, shown on the shooting-menu line; Classic Chrome look. Not yet in Q menu, bracketing, RAW conversion, EXIF. Details: [`re/FINDINGS.md`](re/FINDINGS.md) |
| SD card: the new entry with **its own look data, PRO Neg. Hi back to stock** (`… --fsim11 --cclook`) | **Built and emulator-proven** (2026-11-13, `re/build/sdchain_cc11own_green/`): colour mode 1 renders from its own presets and tone family, PRO Neg. Hi is Fujifilm's original again. Applied live on the camera; photo comparison pending |
| USB debug firmware (label 3.85) | Flashed and working: memory peek / poke / call over USB (PTP) |
| ROM dump card (`romdump/`) | **Working** (2026-11-12): SD dual boot + read-only USB PEEK; boot ROM dumped (sha256 7dc7e332…) without flashing |
| Live tuning over USB | Working: parameter changes take effect on the next shot or in-camera RAW conversion |
| Live UI recolouring over USB | Working: swapping red and green in the UI graphics turns the menu accent green |
| Classic Chrome **v3 candidate** (`re/tools/build_cc3.py`) | Built, **not flashed**: chroma matched to an X-T20 photo, menu entry renamed CLASSIC CHROME. Confirmed via SD boot. Open: v3 mutes reds much more than Fuji's X-E2 data (×0.63 vs ×0.87 of PROVIA); a colour-chart comparison with the X-T20 comes first |

## Classic Chrome patch (quick start)

```
python3 public/xpro1_cc_patch.py FPUPDATE.DAT patched/FPUPDATE.DAT
```

1. Copy `patched/FPUPDATE.DAT` to a card formatted in the camera.
2. Hold **DISP/BACK** while switching on, then confirm the update.
3. Choose **PRO Neg. Hi** to get Classic Chrome. The menu, icon and EXIF still say "PRO Neg. Hi".

The script accepts only the official 3.82 file, checks every value it changes, and refuses to write anything that is
not byte-identical to the expected build. The output is labelled **3.83**, because the camera only accepts updates
newer than the installed version. To roll back, use `--stock` to make a relabelled copy of the official firmware.
Risks, rollback and what exactly changes: [`public/README.md`](public/README.md).

## SD dual boot (experimental)

The X-Pro1's boot ROM loads two files from a FAT32 card when **Fn + command-dial press** are held at power-on (after
taking the battery out and back in):

* `ffsys.bin`: the stock parameter block from the update file.
* `ffboot.bin`, up to 64 KiB: our chain stub plus the stock boot loader, compressed.

The stub runs in this order:
1. It unpacks the stock loader to address 0 and drains an abort the ROM leaves pending.
2. It starts the stock loader, which loads the firmware from flash as usual.
3. A hook at the loader's final jump patches the firmware in RAM before it starts.

The flash is never written. Switching on without the key combination boots the normal firmware.

**The bug that blocked it until 2026-11-11:** the firmware decides at start-up why it was switched on, using a GPIO
bit the loader records. That bit is only set for a moment after power-on. The SD path reaches the loader seconds
later, so the firmware decided the start was invalid and switched the camera off. The hook now corrects the recorded
value. Details: [`re/FAILURES.md`](re/FAILURES.md) (E25, F21).

Building a card (Linux, needs the research environment below):

```
sh re/tools/setup_work.sh                     # venv + extracted firmware in re/work/ + compiled stubs
PY=~/.venvs/xpro1-re/bin/python
$PY re/tools/build_sdchain.py FPUPDATE.DAT re/work/chain/chain_crumbs.bin re/build/mycard --crumbs [--uiswap]
$PY re/tools/emu_crumbs.py FPUPDATE.DAT re/build/mycard/ffboot.bin re/work      # emulator checks, must say ALL OK
```

Copy `ffboot.bin` and `ffsys.bin` to the root of a FAT32 card and verify their checksums. Then unmount the card;
don't power off the reader. `--uiswap` swaps red and green in every UI colour at boot, which makes the menu
accent green. `--cc` adds the Classic Chrome v3 candidate values and the menu name CLASSIC CHROME (emulator check:
`re/tools/emu_cchook.py`; not yet booted on the camera).

### SD card: Classic Chrome as its own film simulation

```
$PY re/tools/build_sdchain.py FPUPDATE.DAT re/work/chain/chain_crumbs.bin re/build/sdchain_cc11_green --crumbs --uiswap --cc --fsim11
$PY re/tools/emu_fsim11.py FPUPDATE.DAT re/build/sdchain_cc11_green/ffboot.bin re/work FLASHED_FIRMWARE.DAT   # ALL OK
$PY re/tools/emu_crumbs.py FPUPDATE.DAT re/build/sdchain_cc11_green/ffboot.bin re/work                       # ALL OK
```

Camera-tested build: ffboot.bin `1923db4f…`, ffsys.bin `7661dadc…` (2026-11-13). After an SD boot the FILM
SIMULATION menu has an 11th entry, **CLASSIC CHROME** with the X-E2's icon, below SEPIA, and the shooting-menu line
shows that icon when it is selected. It uses a film-simulation slot the firmware has but never offered (number 6).
PRO Neg. Hi keeps its name. Everything is applied in RAM at the moment each piece of data is loaded: the settings
tables at boot, the menu module when it is streamed in, the colour-mode table before the main firmware starts, and
the menu text on every language load. The icon is already in the X-Pro1's font, unused.

* With `--fsim11` alone the look is borrowed from the Classic Chrome data that the flashed v2 keeps in PRO Neg. Hi's
  slot, so PRO Neg. Hi also looks like Classic Chrome. **With `--cclook` as well** (`re/tools/cclook.py`), the new
  entry gets its own data (the X-E2 matrices in free presets 17/18, the v3 chroma matrix in preset 12, the X-E2
  tone curve through a tone family donated by SEPIA, whose curves are PROVIA's) and PRO Neg. Hi goes back to
  stock. That takes 20 patched words in the image pipeline's selection code (each a fallback instruction turned
  into a call to a 4-instruction stub) and 161 tuning bytes; `re/tools/emu_cclook.py` runs the real selection
  functions for every colour mode and variant. Build: `re/build/sdchain_cc11own_green/` (README there).
* Not covered yet: Q menu, film-simulation bracketing, RAW conversion, shooting-screen indicator, EXIF film mode.
* Before switching on **without** the card, select a stock film simulation: the flash firmware has no menu row for
  the new value.

How it was found (menu tables, free slots, where the text and icons come from): [`re/FINDINGS.md`](re/FINDINGS.md).

## USB debug firmware and live editing

`re/tools/build_ptpdebug.py` makes a v2 firmware with three extra vendor PTP operations: 0x9010 PEEK, 0x9011 POKE
and 0x9012 CALL. It is labelled 3.85 and flashed like any update. With it installed and the camera on USB:

| Tool | What it does |
|---|---|
| `ptpdebug.py` | `info`, `peek`, `poke`, `call`, `dumprom` (the 16 KiB boot ROM) |
| `tune.py` | show / set / restore image-processing parameters by ID, colour matrices as numbers, load a 3D LUT's best fit |
| `uicolor.py` | list / set / `swaprg` / restore the UI's vector-graphic colours |
| `uiname.py` | show / set / restore the menu name of the PRO Neg. Hi slot (default CLASSIC CHROME) |
| `fsimslot.py` | live test of the 11th film-simulation entry: `apply [--own]` / `restore` / `status` (includes one code poke) |
| `cclook.py` | live: Classic Chrome's own look data for colour mode 1 and PRO Neg. Hi back to stock: `apply` / `restore` / `status` |
| `uitextmark.py`, `uitext.py` | label UI text IDs live to see what a screen draws; print UI text by ID in any language |
| `ccfit.py` | offline: which chroma matrix produced a Classic Chrome-slot JPEG (needs a PROVIA conversion of the same RAW) |
| `dramdump.py`, `dramtest.py` | dump all 256 MB of DRAM (47 s); test whether DRAM survives a restart |
| `sdcrumbs.py` | read the SD-boot progress notes left in DRAM |

All edits are RAM-only. Switching off and on keeps them (the camera only goes to standby). Removing the battery
restores everything.

## Research environment

* Linux, Python 3.
* `sh re/tools/setup_work.sh` creates the venv `~/.venvs/xpro1-re` (capstone, keystone-engine, unicorn, ziglang,
  numpy) and extracts the firmware into `re/work/`.
* For the USB tools: `~/.venvs/xpro1-re/bin/pip install pyusb`. If you get "Resource busy", the desktop's gphoto
  service is holding the camera.
* `re/work/`, `re/build/`, firmware files and photos are git-ignored. Nothing derived from Fujifilm's firmware is
  committed.

## Repository layout

| Path | Contents |
|---|---|
| `public/` | The Classic Chrome patch script and its user README |
| `romdump/` | ROM dump card: builder, USB dump client and how-to ([`romdump/README.md`](romdump/README.md)) |
| `re/FINDINGS.md` | Adding film simulations: menu model, free slots, where names and icons come from, camera tests |
| `re/NOTES.md` | Session notes: memory map, formats, every finding with addresses |
| `re/FAILURES.md` | SD-boot failure log, established facts (E1–E27) and working rules. Read before any camera test |
| `re/TODO.md` | Open tasks |
| `re/classic_chrome/` | Classic Chrome port analysis |
| `re/sdchain/` | SD chain stub (C + ARM assembly, built with `zig cc`) |
| `re/tools/` | Builders, emulator tests (unicorn), USB tools |

## Credits

* [fujimod](https://github.com/justjake/fujimod) (FujiHack community): independent documentation of the update
  format and SD boot for many Fujifilm cameras. Its boot-ROM facts helped here. The X-Pro1 SD chain stub and loader
  hook in this repository are separate code.

Fujifilm, X-Pro1, X-E2 and Classic Chrome are trademarks of FUJIFILM Corporation. This project is not affiliated with
or endorsed by Fujifilm.
