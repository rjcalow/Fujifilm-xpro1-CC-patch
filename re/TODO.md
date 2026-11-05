# TODO: X-Pro1 Classic Chrome (next sessions)

Status (2026-11-04): Classic Chrome extracted from the X-E2; the PRO Neg Hi swap is built and statically verified
(`build/ccswap_candidate/`). **Not flashed. Rule: dual-boot from SD before any flash.**

## NOW (after flash, 2026-11-05)
- [x] Public package: `public/README.md` + `public/xpro1_cc_patch.py` (reproduces the tested build exactly).
- [x] Candidate flashed; camera boots/shoots → checksum + hardware LZ decode confirmed on camera.
- [x] Same-camera test: CC look IS applied (PRO Neg Hi slot −18–21% sat vs PROVIA on warm/green; blues unchanged).
- [ ] Reduce blue/cyan saturation via the 3×3 blue row (preset 5); user picks the strength; rebuild, verify, reflash.
- [ ] Tone check: same scene, MANUAL exposure + fixed WB (Daylight), PROVIA vs PRO Neg Hi(CC), to see the curve #38 shadows.

## 0. Update-mode experiments (safe: always cancel at the confirmation screen)
- [x] Update mode = hold DISP/BACK + power ON (confirmed on camera). fujimod.com: X-Pro1 not supported.
- [ ] Bad-checksum test (`build/test_bad_checksum/`): error screen or confirmation screen? Record the versions shown.
- [ ] If the test file gives an error: try the CC candidate (cancel at confirmation). Reaching confirmation = checksum accepted.
- [ ] Optional lower-risk first flash: build a tuning-only variant (75 tuning bytes + checksum, blob1 untouched =
      no re-compression). Colour matrices only: keep PRO Neg Hi tone IDs as-is (curve #38 isn't present without blob1).

## 1. Dual boot (do first)
- [ ] Find the X-Pro1 SD-boot button combination (Fuji service manual "SD_BOOT"; or try combos at power-on.
      X-E2 = command dial press + Fn7, X-T1 = AE-L + Fn1).
- [ ] fujimod's site refuses the X-Pro1. Alternative: re-implement the EXR Pro SD_BOOT files ourselves (`ffsys.bin`,
      `ffboot.bin`, `ffuser.bin`) from fujimod's open-source `crates/recovery` (exr*.rs, rom_sd.rs) and its xpro1-382
      recipe, with our edits in the RAM image: no recompression, no checksum.
- [ ] Find what fills the tuning DB at RAM 0x40d3b580 (flash 0xae0000 or the blob1 mirror 0x812470?).
      This tells whether our tuning edits take effect in dual boot and after a flash.

## 2. Close remaining unknowns (static, no camera)
- [ ] X-Pro1 updater: does it verify the whole file before erasing? Does it accept the same version (3.82)?
- [ ] Meaning of X-Pro1 `+200` / X-E2 `+0x10c` (colour space?). Replace the approximate alt 3×3 matrix.
- [ ] Decompressor: X-Pro1 (EXR Pro) page rule unmeasured. Keep `lzenc_chunked.py`; re-check if fujimod measures it.

## 3. On camera (only after dual boot works)
- [ ] Shoot the same scene in PROVIA vs PRO Neg Hi (= CC). Check the tone curve, then tune the derived matrices if colours are off.
- [ ] Only then consider flashing `build/ccswap_candidate/FPUPDATE.DAT` (keep the stock file for rollback).

## Later / optional
- [ ] Real 14th film sim (Strategy B, `classic_chrome/CLASSIC_CHROME.md` §4); needs the UI resource DB format (menu, icon).
- [ ] X-E1 (same EXR Pro) may take the same patch with its own offsets.
- [ ] Make `tools/cc_port.py` / `build_ccswap.py` take input paths (they assume the scratch layout `work/`, `x4/`).
- [ ] Share findings with fujimod / FujiHack Discord (type-4 checksum, page-alignment observation, CC tables)? User's call.

Setup reminders: Ghidra 12.2 + JDK 25 need re-downloading (`tools/README_ghidra.md`); decompiled C is in
`decompiled/*.c.gz`; unpack with `tools/unpack.sh`; verify builds with `tools/verify_ccswap.py`.
