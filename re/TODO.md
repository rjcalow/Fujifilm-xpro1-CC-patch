# TODO: X-Pro1 Classic Chrome (next sessions)

Status (2026-11-06): **v2 flashed and working** (PRO Neg Hi slot = Classic Chrome, chroma-gain fix active; camera still
reports Ver3.82). Full audit of colour-mode parameters done: v2 is a complete port of the X-E2's CC settings.
**SD dual-boot files built and verified (`build/sdboot_v2/`), not yet tried: waiting for a FAT32 card.**
Details for everything below: `NOTES.md` (sessions 2026-11-06) and `classic_chrome/CLASSIC_CHROME.md`.

## NOW
- [ ] **SD dual-boot test** (no flash write). Needs a FAT32 card: a ≤32 GB SDHC card, or a spare 64 GB card formatted
      FAT32 on the PC (`mkfs.vfat -F 32`; don't format it in the camera, which makes SDXC cards exFAT). Card root:
      `ffsys.bin`, `ffboot.bin`, `ffuser.bin` from `build/sdboot_v2/`, no `FPUPDATE.DAT`. Battery out/in, hold
      shutter + UP, power ON. Success = camera starts and photos show EXIF "Ver3.89" (marker). Blank screen = ROM did not
      take the files (note LED colour); hang = battery pull. Check the card on the PC before inserting it.
- [ ] Confirm the shutter + UP mode is the boot ROM (already seen: blank screen after battery cycle). Note LED colour; with
      USB connected, `lsusb` should show a bare boot-ROM device, not a normal Fujifilm (04cb) device or the C_JIG mode.
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
