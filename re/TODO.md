# TODO: X-Pro1 Classic Chrome (next sessions)

Status (2026-11-12): **v2 flashed; v3 candidate (X-T20-fitted chroma + menu name CLASSIC CHROME) runs from the SD
card and is confirmed by a conversion**; reds still need a genuine reference before flashing v3.
Earlier status (2026-11-09): **v2 flashed and working** (PRO Neg Hi slot = Classic Chrome, chroma-gain fix active; camera
still reports Ver3.82). **SD dual boot paused**: ROM + stub + stock loader work, section 0 stops before blob1 (no CPU
exception); every remaining unknown is in the boot ROM. See `FAILURES.md` ("Where it stands", "Next step").
Details: `NOTES.md` (sessions 2026-11-06 to 2026-11-09) and `classic_chrome/CLASSIC_CHROME.md`.
Environment: `sh re/tools/setup_work.sh` (venv `~/.venvs/xpro1-re`, extracted firmware in `re/work/`).

## NOW
- [x] (2026-11-12) **v3 runs from the SD card**: card `build/sdchain_cc_green/` (ffboot 8436762b…). DSCF2763 (CC slot,
      DSCF2730.RAF) fits the v3 2x2 (`ccfit.py`, Δab 0.54; v2 2.27). The first card (18ec6554…) missed the start-up
      tuning load (DSCF2759 = v2). 2x2 axis order [Cr, Cb] confirmed by the same data.
- [ ] After an SD boot: does the menu say CLASSIC CHROME and is the menu accent green? (Language hook and UI swap
      are emulator-checked only.)
- [ ] **Colour-chart test before flashing v3** (reds are the open question: v3 gives ×0.63 of PROVIA's red chroma,
      Fuji's X-E2 data ×0.87). Needs a ColorChecker-type chart (24 patches; a clone is fine for this method).
      1. Same light (daylight, overcast ideal), chart filling the middle third, both cameras, RAW + JPEG,
         WB fixed (Daylight or a custom WB off the grey patch), Colour 0 / Highlight 0 / Shadow 0, DR100.
      2. X-T20: convert its RAW in camera as PROVIA and as Classic Chrome. X-Pro1: same RAW as PROVIA and CC slot.
      3. Per patch, compare the CC/PROVIA change on each camera (the ratio cancels the sensor differences).
         Same change → port correct; different → refit the 2x2 (and 3x3 if hue shifts differ) to the X-T20's
         change, try live with `tune.py setmat`, convert again, flash only the final values.
      Tool still to write: patch extraction for a 4×6 chart from four corner clicks, then the ratio fit (ccfit.py's
      pipeline model). Without a chart: a varied colourful scene (fruit, packaging, a magazine page) in daylight
      works for the same ratio method; a chart shown on a screen is a weaker fallback.
- [x] (2026-11-11) **SD dual boot works**: `build/sdchain_poweron/` (FAILURES E25). Fn + dial press at power-on → screen
      comes up by itself, RAM marker Ver3.89 present.
- [x] EXIF "Ver3.89" confirmed: `samples/DSCF2758.JPG` / `.RAF` (2026-11-11 12:39).
- [x] (2026-11-11) Menu accent red → green found live (FAILURES E27: R/G swap of every UI colour record).
- [ ] Narrow the swap to the menu accent only (bisect the records with `uicolor.py set --from/--skip/--limit`), and
      try a darker menu background the same way.
- [ ] Production SD card: quiet stub + loader_hook with the power-on snapshot fix (no traps/checkpoints) and the real
      patch table (Classic Chrome variants) instead of the marker; then document the procedure in `public/`.
- [x] (superseded, FAILURES F21) **SD-boot breadcrumb test** (`build/sdchain_crumbs/`, FAT32 card): Fn + dial press boot → wait 30 s → shutter
      (normal boot, keep the battery in) → USB → `sdcrumbs.py read --save re/work/crumbs_1.bin`. Question: does DRAM
      survive, and if so where does the SD-booted firmware stop and in what hardware state.
- [x] (2026-11-10) Flashed, PEEK works, ROM dumped (sha256 = fujimod's). Was: flash `build/ptpdebug_385/FPUPDATE.DAT` (v2 + USB peek/poke/call, label 3.85;
      header check `0300 0000 8500 0000`). Then `~/.venvs/xpro1-re/bin/python re/tools/ptpdebug.py info` and
      `... dumprom rom.bin` (compare sha256 with fujimod's 7dc7e332…).
- [x] (2026-11-11) Live tuning works (FAILURES E24); `re/tools/tune.py` built and tested on the camera.
- [ ] **LUT test** (10 min): USB → `tune.py lut luts/ColorReps-classic-chrome.cube` → unplug → convert one RAW as
      PROVIA, PRO Neg Hi, PRO Neg Std → compare (expected ΔE ~3 to the real LUT applied to the PROVIA JPEG).
- [ ] (superseded by the colour-chart test in NOW) Colour-accuracy test, live: X-T20 reference vs X-Pro1 conversions.
- [ ] Analyse the boot ROM: SD-boot path and what it leaves behind, mount + file API (FAILURES E20), the pending abort.
- [ ] Optional, zero risk (user's call): ask fujimod's maintainer for the EXR ROM image or its mount address.
- [x] Section 0 analysed (no hardware waits, exceptions = silent hang); exception-trap card → no exception (F18);
      checkpoint card unreadable (F19); warm-resume idea ruled out statically (F20). No more LED tests.
- [ ] Ratio test for colour accuracy (camera RAW conversion keeps everything else fixed):
      X-Pro1: DSCF2723 RAW → PROVIA, Color 0 (the PRO Neg Hi/CC version is DSCF2743).
      X-T20: a red subject (+ some green/blue) → in-camera RAW conversion as PROVIA and as Classic Chrome, Color 0, same WB.
      Compare CC/PROVIA per hue on each camera. Matches → port accurate; differs → per-hue correction targets.
- [ ] Only after the ratio test: decide whether reds/blues need correcting. Hand-tuning the 3×3 is a deliberate
      deviation from Fuji's X-E2 data, not a port; use SD boot to try variants without flashing.
- [ ] Tone check: same scene, manual exposure + Daylight WB, PROVIA vs PRO Neg Hi(CC), to see curve #38's shadows.

- [ ] Extended Highlight/Shadow (NOTES 2026-11-12, "Highlight / Shadow tone mapped"): pick the slot mapping, then a
      live test: POKE rewritten curves into blob1 RAM 0x8098e0, convert one RAW at H/S −2 / 0 / +2, compare L* by band.
      Open: is a gain above 5604 accepted (register width)?

## Done 2026-11-06
- [x] Reds too strong on v1: chroma-gain preset (ID 0xe4ec, `FUN_00f2c8fc`) was Neg Hi's (up to ×1.15); X-E2 CC uses PROVIA's.
      Audit of every colour-mode lookup on both cameras found nothing else. v2 = v1 + that byte.
- [x] Updater version check mapped (`FUN_00ee5010`): file header 0x204/0x208 must be newer than the installed version
      (blob1 0x857af0: DB[0x204..0x206] if DB[0x206]==0xff, else built-in 3.82). Builds are labelled 3.83 (header is
      outside the checksums). Rollback file: stock relabelled 3.84 (`build/rollback_stock_384/`).
      The first "still refused" was the old v1 file on the card, not the check.
- [x] v2 flashed (SHA 0df1cefe…, label 3.83); EXIF still "Ver3.82" (built-in version, as predicted).
      Same RAW, v1 vs v2: chroma ×0.956, no hue/tone change; in-camera RAW conversion uses the patched tuning.
- [x] SD boot: fujimod xpro1-382 recipe reproduced (`tools/build_sdboot.py`; all regions match its hashes; loader audited).
      Trigger candidate from the service manual p.3-12: power ON holding shutter + UP (camera shows a blank screen).
      Firmware has no reference to the boot-ROM mode (it lives in the 16 KiB mask ROM); found the factory C_JIG mode
      and a standby routine using SRAM 0xfff00800.

Versions/rollback rules (no official downgrade or re-install; label 3.83+; rollback = stock relabelled): see
`NOTES.md` → "Firmware versions, downgrades and rollback".

## Open questions (static, no camera)
- [x] (2026-11-12) The tuning DB (RAM 0x40d3b580) is filled from flash 0xae0000 at run time (blob1 0x857e44 → 0x863940),
      not from the blob1 mirror. SD-booted tuning edits hook that call (`tools/cchook.py`).
- [ ] How C_JIG (factory adjustment mode) is entered, to tell it apart from the ROM mode for certain.
- [ ] Meaning of X-Pro1 `+200` / X-E2 `+0x10c` (colour space?). Replace the approximate alt 3×3, and port the alt-path 2×2
      (table 0xf2dea8, Neg Hi still preset 10 = stock) if it is the Adobe RGB path.
- [ ] Our own EXR SD loader (fujimod's has no licence, so it cannot ship in `public/`).

## Update-mode experiments (safe: always cancel at the confirmation screen)
- [x] Update mode = hold DISP/BACK + power ON (confirmed on camera).
- [ ] Bad-checksum test (`build/test_bad_checksum/`, relabel it 3.83 first): error screen or confirmation screen?

## Later / optional
- [ ] Real 14th film sim (Strategy B, `classic_chrome/CLASSIC_CHROME.md` §4); needs the UI resource DB format (menu, icon).
      (2026-11-12 night) Started: use the hidden fsim 6 / colour mode 1 slot (NOTES, last session). Next: decode the
      film-sim menu list (shooting menu + Q menu) and the cm→index patches; test on an SD card (USB mode unloads settings).
      (late night) Data side mapped (property 0x3d, conversion row 10 free, six value lists). Open: how a menu screen
      draws item k (text/icon) — find the screen-resource format; then build the SD card.
      (2026-11-13) 11th menu row works on the camera (blank). Everything known + free space: `FINDINGS.md`.
- [x] (2026-11-13) **SD card with Classic Chrome as its own entry works on the camera**: `build/sdchain_cc11_green/`
      ffboot 1923db4f… (icon + name in the pop-up and on the shooting-menu line, Classic Chrome look borrowed from
      PRO Neg. Hi's slot). On the user's card.
- [x] (2026-11-13) Own look data for film sim 6 + PRO Neg. Hi back to stock: `tools/cclook.py`, card
      `build/sdchain_cc11own_green/` (ffboot 2edd070e…), emulator ALL OK, applied live. **Photos pending** (FINDINGS §7.1).
- [ ] New entry in Q menu, bracketing, shooting-screen indicator, EXIF FilmMode (FINDINGS §7.3).
- [x] (2026-11-15) Camera test of `build/sdchain_cc11rc_green/`: CLASSIC CHROME in the shooting menu and the
      playback RAW CONVERSION menu, conversion works (user). FINDINGS §6d.
- [ ] **Test Classic Chrome accuracy** (card `sdchain_cc11rc_green`): same scenes (colour chart or red/green/blue
      subjects, skin, sky, foliage), manual exposure, Daylight WB, Color 0, Tone 0. Reference: X-T20 / X-E2 in Classic
      Chrome. X-Pro1: shoot RAW, in-camera RAW conversion as CLASSIC CHROME and as PROVIA. Compare CC/PROVIA per hue on
      each camera (the ratio cancels sensor differences) and tone (shadows, curve 38). Only then decide on corrections.
- [ ] **ACROS** as a 12th film simulation (roadmap; recipe in ADDING_FILM_SIMS.md). Numbers: MODE_FSIM 2 or 4, a
      colour mode from 8/9, stored value from 8/9/10/14/15, menu row 11 (tables copied with 12 rows), RAW-conversion
      film code 9, text IDs + a glyph in the font for the icon. Look: ACROS is monochrome — start from MONO's
      colour mode / tone family (6) and donate a tone curve slot (X-T2/X-Pro2 ACROS curve + grain-free), check
      whether MONO's +Ye/R/G filter variants (MODE_FSIM 8–10) can be shared. Sources: X-T2 firmware tables.
      (2026-11-16) X-Pro2 researched, FINDINGS §10: ACROS = colour modes 10–13, same table/curve format as the
      X-Pro1, plus an ACROS-only per-ISO processing stage the X-Pro1 lacks → ACROS-style sim feasible, exact copy not.
      Next: decode the X-Pro2 tone selection (ACROS curve numbers), diff ACROS vs MONO tables.
- [ ] X-E1 (same EXR Pro) may take the same patch with its own offsets (fujimod has an xe1-271 recipe too).
- [ ] Make `tools/cc_port.py` / `build_ccswap.py` take input paths (they assume the old scratch layout `work/`, `x4/`).
- [ ] Share findings with fujimod / FujiHack (version-check / "stock updater acceptance", SD trigger from the service
      manual, type-4 checksum, CC tables)? User's call.

Setup reminders: Ghidra 12.2 + JDK 25 need re-downloading (`tools/README_ghidra.md`); decompiled C is in
`decompiled/*.c.gz`; unpack with `tools/unpack.sh`; verify builds with `tools/verify_ccswap.py`; capstone is not
installed system-wide (use a venv).
- [x] (2026-11-17, menus + pictures OK) Camera test of `re/build/sdchain_fourlooks_green/` (4261ad85…) and the fixed default card
      `re/build/sdchain_cc11wb_green/` (72d00748…): rows 10–13, names, icons, WHITE BALANCE AUTO row without a name,
      a picture per entry (FINDINGS §11). Then: Superia's 2x2 boost (second 2x2 preset + selector), RAW CONVERSION
      rows for the new entries.
- [ ] Camera test of `re/build/sdchain_fourlooks_rc_green/` (28479b21…): RAW CONVERSION shows all four entries; converting with
      each gives the expected look (recipes = their base). FINDINGS §11b.
- [ ] Card module for EXIF FilmMode + RAW CONVERSION starting entry (FINDINGS §12.3 c): per look FilmMode (Classic
      Chrome 0x600, borrowed looks a private value), both module-0x44 parsers extended from the line-up; emulator
      check of both parsers; camera test (new pictures open on their entry).
- [ ] **Focus-peaking menu with stronger / bolder options** (user, 2026-11-17). Today `--peaking` fixes the HIGH level's
      gains (tuning bytes 0xc88c 40→48, 0xc8a5 / 0xc8a7 64→120, features/peaking.py, from PR #3). Goal: keep HIGH / LOW
      stock and add rows to the MF ASSIST peaking menu, e.g. HIGHER and MAX, each with its own gain (and outline width,
      if a parameter for it exists). To find first: the peaking setting's menu node / list / conversion table (as for
      FILM SIMULATION, FINDINGS §3), where the selected level picks the tuning IDs (0xc88c / 0xc8a5 / 0xc8a7 and their
      LOW counterparts), and whether outline width or colour is a separate parameter. Then a features/ module driven
      like the line-up (levels as data), live test over USB first.
