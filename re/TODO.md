# TODO: X-Pro1 Classic Chrome (next sessions)

Status (2026-11-09): **v2 flashed and working** (PRO Neg Hi slot = Classic Chrome, chroma-gain fix active; camera
still reports Ver3.82). **SD dual boot paused**: ROM + stub + stock loader work, section 0 stops before blob1 (no CPU
exception); every remaining unknown is in the boot ROM. See `FAILURES.md` ("Where it stands", "Next step").
Details: `NOTES.md` (sessions 2026-11-06 to 2026-11-09) and `classic_chrome/CLASSIC_CHROME.md`.
Environment: `sh re/tools/setup_work.sh` (venv `~/.venvs/xpro1-re`, extracted firmware in `re/work/`).

## NOW
- [x] (2026-11-11) **SD dual boot works**: `build/sdchain_poweron/` (FAILURES E25). Fn + dial press at power-on → screen
      comes up by itself, RAM marker Ver3.89 present.
- [x] EXIF "Ver3.89" confirmed: `samples/DSCF2758.JPG` / `.RAF` (2026-11-11 12:39).
- [x] (2026-11-11) Menu accent red → green found live (FAILURES E27: R/G swap of every UI colour record).
- [ ] **Green-UI SD card** `build/sdchain_green/` (ffboot 276f1752…): power-on card + UI colour swap at stage B,
      emulated (byte-exact vs the live-tested swap). Test: Fn + dial press boot → menu accent green, photo EXIF Ver3.89.
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
- [ ] **Colour-accuracy test, live**: X-T20 genuine Classic Chrome reference vs X-Pro1 conversions; adjust
      cc3x3 / cc2x2 with `tune.py setmat`, convert the same RAW in camera, `compare_jpeg.py`. Flash only the final values.
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
- [ ] Where the tuning DB (RAM 0x40d3b580) is filled from at run time: flash 0xae0000 via the block reader (likely) or the
      blob1 mirror 0x812470. Decides whether SD-booted tuning edits need a flash-read redirect (fujimod has none for EXR Pro).
- [ ] How C_JIG (factory adjustment mode) is entered, to tell it apart from the ROM mode for certain.
- [ ] Meaning of X-Pro1 `+200` / X-E2 `+0x10c` (colour space?). Replace the approximate alt 3×3, and port the alt-path 2×2
      (table 0xf2dea8, Neg Hi still preset 10 = stock) if it is the Adobe RGB path.
- [ ] Our own EXR SD loader (fujimod's has no licence, so it cannot ship in `public/`).

## Update-mode experiments (safe: always cancel at the confirmation screen)
- [x] Update mode = hold DISP/BACK + power ON (confirmed on camera).
- [ ] Bad-checksum test (`build/test_bad_checksum/`, relabel it 3.83 first): error screen or confirmation screen?

## Later / optional
- [ ] Real 14th film sim (Strategy B, `classic_chrome/CLASSIC_CHROME.md` §4); needs the UI resource DB format (menu, icon).
- [ ] X-E1 (same EXR Pro) may take the same patch with its own offsets (fujimod has an xe1-271 recipe too).
- [ ] Make `tools/cc_port.py` / `build_ccswap.py` take input paths (they assume the old scratch layout `work/`, `x4/`).
- [ ] Share findings with fujimod / FujiHack (version-check / "stock updater acceptance", SD trigger from the service
      manual, type-4 checksum, CC tables)? User's call.

Setup reminders: Ghidra 12.2 + JDK 25 need re-downloading (`tools/README_ghidra.md`); decompiled C is in
`decompiled/*.c.gz`; unpack with `tools/unpack.sh`; verify builds with `tools/verify_ccswap.py`; capstone is not
installed system-wide (use a venv).
