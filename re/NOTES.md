# Fujifilm X-Pro1 firmware RE: adding Classic Chrome

Inputs: `../FPUPDATE.DAT` (X-Pro1, target) and `../FWUP0008.DAT` (X-Pro2 v8, reference that has Classic Chrome).
All offsets are file offsets in the NOT-ed image unless marked RAM. Flash offset = file offset − 0x25c (X-Pro1) / − 0x240 (X-Pro2).

## Status
| | |
|---|---|
| Container obfuscation (NOT) | ✅ solved, both models |
| LZ compression (decode + re-encode) | ✅ solved, byte-exact round trip |
| Load/partition tables, all module bases | ✅ both models |
| Film-sim enums, and how Classic Chrome is numbered | ✅ from X-Pro2 debug strings + code |
| LZ repack rule | ✅ stock streams never straddle a 16 KB input chunk (counted from the blob header); tools/lzenc_chunked.py obeys it |
| PRO Neg Hi → Classic Chrome | ✅ v2 flashed and working (2026-11-06): re/build/ccswap_v2/ (label 3.83); v1 = ccswap_candidate |
| Colour-mode parameter audit | ✅ every film-sim lookup checked on both cameras; v2 = complete port of X-E2 CC settings |
| Updater version check | ✅ mapped: header 0x204/0x208 must be newer than built-in 3.82 → label builds 3.83 |
| SD dual boot | ⏸ ROM boot + chain to the stock loader work; section 0 stops before blob1 without an exception. Paused until the boot ROM can be read over USB (`build/ptpdebug_385/`). **Read `FAILURES.md` first** |
| USB debug firmware | 🟡 built + emulated (PTP 0x9010 peek / 0x9011 poke / 0x9012 call), not flashed: waiting for a Mini-USB cable |
| Colour accuracy vs real CC | 🟡 pending ratio test (same RAW, PROVIA vs CC, X-Pro1 vs X-T20) |
| Where the per-film-sim color/tone data lives | ✅ found: Classic Chrome fully extracted from the X-E2 and mapped onto the X-Pro1. See **classic_chrome/CLASSIC_CHROME.md** |
| Outer checksum (X-Pro1 0x20c, 0x24c) | ✅ solved on 3 files: 0x20c = ~Σ(bit-inverted payload [0x25c,0x25c+L)), trailers = ~Σ(raw); see tools/fpupdate.py |

## Tools (`tools/`)
```
sh tools/unpack.sh ../FPUPDATE.DAT out1   # → out1/not.bin, blob1.bin, blob2.bin (model auto-detected)
sh tools/unpack.sh ../FWUP0008.DAT out2
python3 tools/disasm.py out1/blob2.bin 0xe0ec80 out1/blob2.asm   # needs: pip install capstone
```
| file | purpose |
|---|---|
| lz.py / lzenc.py | LZ decoder / greedy encoder |
| extract.py | decompress blobs (auto-detects X-Pro1/X-Pro2, or takes header offsets) |
| disasm.py | capstone linear disassembly to text |
| movwt.py | collect movw/movt constant pairs (find code refs to addresses) |
| findbase.py | guess the load base from string-pointer tables |
| common.py | find long byte runs shared between the two firmwares (excludes code) |
| curves.py | find monotonic u16 arrays (tone-curve candidates; needs numpy) |
| verify_ccswap.py | full static check of a candidate (checksums, LZ, changed bytes, decoded tuning, audit pairs, version label) |
| build_sdboot.py | SD dual-boot files (ffsys/ffboot/ffuser) from an FPUPDATE.DAT + fujimod EXR loader; EXIF marker "Ver3.89" |

## Container format (same on both models)
- 0x000–0x23f plain: u32 4, then ASCII-hex model/component IDs (X-Pro1 `0001024x`, X-Pro2 `0005094x`), then at 0x204
  `u32 ?, u32 ?, u32 checksum?, u32 1` (X-Pro1: `3, 0x82, 0x9763cb14, 1`; X-Pro2: `5, 0x11, 0x050fd40e, 1`).
- 0x240–EOF: payload XOR 0xFF. First words at 0x240 (X-Pro1): `0x2480020, 0x2480020, 0x21c, 0xffffa4b5, …`.
  The checksum scheme is unidentified (not CRC32 or an 8/16/32-bit sum over the obvious ranges).
  Two models are now available to test hypotheses against.
- The payload is a flash image in 0x10000 blocks.

## LZ format
Blob header (5×u32): `dst_size, src_size (incl. header), ceil(src/0x4000), 0x4000, 4`, then tokens:
- `0nnnnnnn` → n literal bytes
- `1ddddddd ddddllll` → copy `l` (1..15) bytes from distance `d` (1..2047)

The decompressed image begins `0, load, size, entry, 0, 0, 0, 0xffffaaaa`, then code (ARMv7, ARM mode).

## X-Pro1 memory map (load table @0xe025c)
| id | file off | RAM | size | contents |
|---|---|---|---|---|
| 0 / 1 | 0x8025c / 0xa025c | 0x40000 / 0xd0000 | 0xd7a0 / 0xd760 | loader stubs |
| 2 | 0xc8025c | 0x130000 | 0x215a54 | **UI resource DB** (layouts/messages, e.g. `MSG_DUMMY_EXAMPLE`; *not* image params) |
| 3 | 0x154025c | 0x510000 | 0x81134 | fonts |
| 4 | 0x10025c (LZ) | 0x774000 | 0x2549c0 | blob1: recording, keys |
| 5 | 0x24025c (LZ) | 0xe0ec80 | 0x3dbb00 | blob2: playback, UI, PictBridge |
| 0x41 | 0x46025c | 0x1420000 | 0x9a9a0 | module with debug film-sim names (file 0x47d95c) |
| 0x42 | 0x50025c | 0x14c0000 | 0x235e0 | module |
| 0x43 | 0x54025c | 0x1500000 | 0xb8d00 | module (RIFF/WAV) |
| 0x44 | 0x60025c | 0x15c0000 | 0xd99a0 | module (SQLite, DCF) |

Other X-Pro1 regions: 0x25c param block; 0x4025c/0x5025c vectors + boot; 0xae025c–0xb3735c small tables
(display gamma @0xaf275c, lens data `FLSNW001`); 0xb6025c/0xbc025c/0xc2025c large LUT-like tables;
0x104025c–0x1491d5c UTF-16 UI strings (~34 languages); 0x1b0025c icons (film-sim names are bitmaps);
0x1c0025c+ about 60 160×120 test JPEGs.

## X-Pro2 memory map (load table @0x120294)
| id | file off | RAM | size | contents |
|---|---|---|---|---|
| 1 | 0x1070240 | 0x1e0000 | 0x43e004 | **UI resource DB** (layouts + ARGB images; counterpart of the X-Pro1's) |
| — | 0xa5f240–0xc17840 | — | — | UI widget layout records (`0xff0003xx` ids, sizes, colors) |
| 2 | 0x1630240 | 0x6f0000 | 0x90330 | fonts |
| 5 | 0x23025c (LZ) | 0xa51000 | 0x3e3000 | blob1: UI + 14k-entry debug symbol/enum string pool (0xca666d–0xcf8958) |
| 6 | 0x41025c (LZ) | 0x1263000 | 0x680000 | blob2: rec control, `reccf*` develop-parameter code |
| 7 | 0x7d0240 | 0x18e3000 | 0x6b0000 | uncompressed ARM, continuation of blob2 |

## X-E2 donor firmware: FWUP0004.DAT (model id `00030071`, already has Classic Chrome)
Same platform generation as the X-Pro1 (EXR-family): same load-table format, flash = file − 0x25c, UI DB at RAM 0x130000.
Load table @0x140270:
| id | flash | RAM | size | contents |
|---|---|---|---|---|
| 0 / 1 | 0x80000 / 0xa0000 | 0x40000 / 0xd0000 | 0xdba0 / 0xdb80 | loader stubs |
| 2 | 0x10a0000 | 0x130000 | 0x2429cc | UI resource DB |
| 3 | 0x1660000 | 0x640000 | 0x84294 | fonts |
| 4 | 0x160000 (LZ @file 0x16025c) | 0x8a0400 | 0x35b4c0 | blob1 (debug symbol pool, `MODE_FSIM_*`, `ICO_FILM_C_CHROME`) |
| 5 | 0x320000 (LZ @file 0x32025c) | 0xf6a9c0 | 0x5ca820 | blob2 |
| 6 | 0x680000 | (same as 5) | | second copy of blob2 region |
| 7 | 0xf40000 | — | 0x20000 | lens data (identical to X-Pro1 flash 0xb20000) |
| 0x48 / 0x4a | | 0x1ce0000 / 0x1d00000 | | modules |
`tools/extract.py` auto-detects the X-E2.

X-E2 `MODE_FSIM_*` = the X-Pro2 list without ACROS: 0 STD … 12 NEGA_COL_2, **13 CLASSIC_CHROME**, NUM = 14.
So the X-Pro1 is presumably 0..12, NUM = 13. The X-E2 has **no** `reccfSetDevelopPara*` / develop-code layer
(that arrived with the X-Processor Pro); on EXR-family bodies film sim is consumed by `MODE_FSIM` index directly.
Classic Chrome UI assets on the X-E2: `ICO_FILM_C_CHROME(_OL)`, `ICO_INFO_FILM_C_CHROME`, `ICO_QUICK_MENU_C_CROME`,
`CONT_FILMSIM_BKT_C_CROME(_W2)`, `PB_RAW_FSIM_C_CROME(_W3)`, `BKUP_FILM_SIM_CLASSIC_CHROME`.

### Classic Chrome extraction: progress (2026-11-04)
**The film-sim enum is identical on the X-Pro1 and X-E2 for 0–12**, and the X-E2 appends 13 = Classic Chrome. Proven by
the EXIF FilmMode (tag 0x1401) mapping in both:
| enum | 0 STD | 1 F1b | 2 F1c | 3 F2 | 4 B&W | 5 SEPIA | 6 CHROME | 7–10 MONO | 11 NEGA1 | 12 NEGA2 | 13 CC |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FilmMode | 0x000 PROVIA | 0x120 ASTIA | 0x000 | 0x200 Velvia | — | — | 0x000 | — | 0x500 ProNeg Std | 0x501 ProNeg Hi | **0x600 Classic Chrome** |
- X-Pro1: a data table `u16[13]` @blob2 **0x1097f6c** (right after the MakerNote version `"0100"` @0x1097f68 and
  `FINE/NORMAL/BASIC` strings). No direct code reference; it's reached relative to a base.
- X-E2: a switch in fn **0x11e48c8** (blob2) on `[settings, #0x51c] - 1`; Classic Chrome → `mov r0,#0x600` @0x11e49d0.
- X-E2 EXIF Saturation (tag 0x1003) fn **0x11e42c8**: 14-case switch on the same field. Bitmask `0x200a` (F1b, F2, CC)
  → 0x8000 "film simulation"; mono → 0x300–0x303; sepia → 0x310.
- **X-E2 settings struct: film sim = field +0x51c** (`+0x4c8` = shooting/scene mode, `+0x518` = another tone setting).
  31 reads in total. Downstream copies that should feed the image pipeline:
  - blob2 0x118aed8 (fn 0x118ad70): → `[r5,#0x228]`, beside `+0x530` and `+0x263c`
  - blob2 0x118d35c (fn 0x118d2d4): → `[r5,#0x24]`, beside `+0x558`, `+0x538`, `+0x610`, likely the develop/IPP parameter block
  - blob2 0x11a64b4 (fn 0x11a6458): → stack frame, with `+0x263c`, `+0x4a4`, `+0x5b8`
  - blob2 0x135c1dc (fn 0x135c16c): → `strh [r2,#0xc]`, with `+0x520/+0x534/+0x538`
  None of these functions reference strings, so this needs interactive data-flow tracing (Ghidra) from those
  destination fields to the table lookups.
- Still not found: the Classic Chrome tone/colour parameter data itself.

**What a port must patch, once the data is found:**
1. Parameter tables indexed by film sim: grow each from 13 to 14 entries, or overwrite an existing entry (e.g. 5 SEPIA).
2. EXIF: X-Pro1 FilmMode table @0x1097f6c (needs 0x600 for CC), plus the Saturation-tag logic.
3. UI: menu/icon/quick-menu entries (X-E2 names: `ICO_FILM_C_CHROME*`, `ICO_QUICK_MENU_C_CROME`, `BKUP_FILM_SIM_CLASSIC_CHROME`).
4. Bounds checks: every `cmp rX,#0xc` / MODE_FSIM_NUM=13 guard on the X-Pro1.
Option 1 alone with overwrite (replace SEPIA) avoids 2–4 entirely: EXIF would still say Sepia.

### X-Pro1 ↔ X-E2 comparison results
- Flash X-Pro1 0xb20000–0xc80000 ≡ X-E2 0xf40000–0x10a0000 (constant delta 0x420000). Lens data identical. The three
  large tables (X-Pro1 flash 0xb60000 / 0xbc0000 / 0xc20000; same sizes in the X-E2) are smooth 2-D u8 maps with
  ~1–3% byte agreement: sensor/lens-shading re-tuning, not film sim.
- Adjustment areas (X-Pro1 flash 0xae0000, X-E2 flash 0xe0000) share only fragments. "Appended record" heuristic hits
  there were lens/AF records (`FF119507`/`FA119507`).
- Blob code is recompiled (only ~600 shared runs). Shared const tables in blob2 (X-Pro1 0x11b64be/0x11c8542/0x11c8e82
  ↔ X-E2 0x14492de/0x145b7ea) are generic math LUTs (e.g. a 10001-entry power curve identical in all three cameras).
- Switches with 13/14 cases on film sim exist (e.g. X-E2 blob1 0x979b78, blob2 0x107c61c), but none is a clean
  table selector, so film-sim parameters are most likely fetched as `table[mode]` (array index, no switch).

## Film simulations
**Internal enum** (X-Pro2 `MODE_FSIM_*` strings @blob1 0xca9604; enum→string fn @0xa59bbc):
0 STD(PROVIA), 1 F1b(ASTIA), 2 F1c, 3 F2(Velvia), 4 B_AND_W, 5 SEPIA, 6 CHROME, 7–10 MONO_N/R/Y/G,
11 NEGA_COL_1(Pro Neg Std), 12 NEGA_COL_2(Pro Neg Hi), **13 CLASSIC_CHROME**, 14–17 ACROS_N/R/Y/G, NUM=18.
Parallel lists: `UI_FILM_SIM_*` @0xcc7844, `BKUP_FILM_SIM_*` @0xcd03e0.

**Develop code**: the film-sim id handed to the image pipeline / RAW develop. Built by
`reccfSetDevelopParaFilmSimulation` (switch @X-Pro2 0x15489cc, stored to struct +0x21d); inverse switch @0x15491d8.

| code | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | **11** | 12 | 13 | 14 | 15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| | PROVIA | Velvia | ASTIA | ProNeg Hi | ProNeg Std | MONO | MONO+Ye | MONO+R | MONO+G | SEPIA | **CLASSIC CHROME** | ACROS | ACROS+Ye | ACROS+R | ACROS+G |

Codes 1–10 are exactly the X-Pro1's ten film sims, and Classic Chrome was appended as 11, so the existing scheme
was extended rather than redesigned. Expect per-film-sim tables with 10 entries (X-Pro1) vs 15 (X-Pro2).

The X-Pro1's `reccf` develop module is a smaller sibling: the shared ±5 switch is @X-Pro1 0x10a6b80 ↔ X-Pro2 0x154600c.
It has no develop-code switch, so the X-Pro1 maps film sim some other way (likely a lookup array).

Other useful X-Pro2 strings: `reccfGetDevelopParaFsim`, `FSIM [%d] : …` (a "BIND" dump of a RAM struct
@blob2 0x13e6500; ISO/RAW/FSIM/WB/CONTRAST/SHARP rows of 11 bytes), `PB_RAW_FSIM_C_CROME` (RAW-convert menu item).

## Shared data between the cameras
- X-Pro1 0xb6–0xc4xxxx tables ↔ X-Pro2 0xf5–0x103xxxx (several 0x9600- and 0x48000-byte identical tables).
- Parameter DBs: many fragments of the X-Pro1 DB reappear, reordered, in the X-Pro2 DB.
- Display gamma: X-Pro1 0xaf275c ↔ X-Pro2 0xd945c. Fonts are shared.
- Film-sim tone curves are not stored as plain monotonic u16 LUTs in either image (checked with curves.py).

## Dead ends (don't repeat)
- Embedded JPEGs: test images, no MakerNote.
- `movw r1,#0x1401` in X-Pro1 blob1 is a property write, not the EXIF FilmMode tag.
- Tag-ID tables 0x0fe9..0x10xx (X-Pro1 blob2 0x11baabc/0x11ca82a, blob1 0x804428) are internal property IDs.
- The develop-param module bases via string voting: noisy. Use the load tables instead.

- Pointer arrays into either DB with 10/13 (X-Pro1) or 15/18 (X-Pro2) entries: none exist. The DB is UI resources anyway.
- s16 3×3 colour matrices with unit row sums (256/1024/2048/4096/8192): none in either image (only byte-pair artefacts),
  so the colour transforms are packed differently or computed at runtime.
- X-Pro2 `BIND` dump (blob2 0x13e6500, RAM struct 0x109ce20+0xbbf0): AE/exposure binding (Shift-JIS AE text), not colour.
- X-Pro1 flash 0xb20000 ↔ X-Pro2 flash 0xf01000 (0x1c396 bytes identical): XF lens falloff/shading profiles.
- X-Pro1 adjustment area flash 0xae0000 is ~69% identical to blob1 data @0x812470 (compiled defaults vs flash copy).
  It shares only small fragments with the X-Pro2 area at flash 0xc0000.

## Porting options (assessed 2026-11-04)
| # | option | risk | effort | notes |
|---|---|---|---|---|
| A | Copy X-Pro2 Classic Chrome tables into the X-Pro1 | brick risk | very high | X-Pro2 = X-Processor Pro + 24 MP X-Trans III; the X-Pro1 = EXR Pro + 16 MP X-Trans I. The tables are not even located yet, and the formats are likely incompatible. Treat the X-Pro2 as a naming map only. |
| B | **Use X-E2 / X-T1 firmware as the reference** | — | medium | Both are EXR Processor II + 16 MP X-Trans II (the X-Pro1/X-E1's direct successors), and both *gained* Classic Chrome in a firmware update (X-E2 v3.00, X-T1 v4.00). Diffing the before/after versions isolates exactly what was added (enum, tables, UI) on a near-identical platform. Strongest path. |
| C | Re-tune an existing X-Pro1 mode (replace SEPIA or PRO Neg Hi) | brick risk | high | Needs the X-Pro1's own film-sim tables located (same open problem as B, single camera). Tune toward CC: low saturation, harder shadows, muted reds/greens, cyan-shifted blues. |
| D | In-camera "recipe" with no firmware change | none | trivial | e.g. PRO Neg Std or PROVIA, Color −2, Shadow +1, Highlight 0/+1, WB shift R+1 B−2. Approximate only. |
| E | Raw workflow | none | low | Shoot RAF and apply a Classic Chrome profile/LUT in a raw converter (e.g. a DCP from an X-Trans II body retargeted to the X-Pro1). Exact colours, but not in-camera JPEG. |

Any firmware path (A–C) still needs: the outer checksum solved, and a repacker verified to round-trip the stock file
byte-for-byte before the first flash.

## Next steps
1. Load X-Pro1 and X-E2 blob1/blob2 into Ghidra at their load addresses (tables above). In the X-E2, follow the
   film-sim setting from its UI/backup symbols (`BKUP_FILM_SIM_*`, `MODE_FSIM_*` enum→string fn) to every
   `ldr …,[base, mode, lsl #n]` access. Those `base` arrays are the per-film-sim tables (expect 14 entries in the X-E2).
   Use Version Tracking/BinDiff to find the same functions in the X-Pro1 (13-entry arrays).
   Cheaper alternative: get X-E2 firmware *before* v3.00 and diff it against this one; the arrays that grow by one
   entry are exactly Classic Chrome.
2. Use that structure to find the X-Pro1's 10-entry equivalent (expect the same record format with one fewer entry).
3. First mod: overwrite SEPIA or PRO Neg Hi with the X-E2 CC entry (adapted if needed). Adding a real 11th menu
   item also needs the UI DB, icon, EXIF and RAW-converter changes.
4. In parallel: solve the outer checksum (now three models to compare) and build/verify a repacker.

## External project: fujimod (github.com/justjake/fujimod), reviewed 2026-11-04 at commit 8589c4b
Open-source tooling (Rust/TS: emulator, USB service protocol, SD recovery cards, firmware library). The actual mod
is closed-source. Releases: two pre-releases, X70 1.10 only (EXR II). Repo topics include `ai-slop`.
Key facts it confirms or adds for the X-Pro1 (`xpro1-382` = firmware 3.82, internal 3.64, SHA-256 709e26f6… = our file):
* **Same layout as ours.** Recovery recipe sections: loader 0x4025c→RAM 0, section table 0xe025c→0x770000,
  stubs →0x40000/0xd0000, UI DB →0x130000, fonts →0x510000, blob1 (method4) →0x774000, blob2 (method4) →0xe0ec80,
  modules →0x1420000, BSS 0x372bc0 / 0x22bb40. Boot ROM 16 KiB @0x80000000, shared with the X10.
* **"method4"** is their name for our LZ (blob header: unpacked, packed, page count, page size 0x4000, method 4).
  On EXR II it is decoded by a **hardware LZ engine** (FFF43000, IRQ 45), which is why no software decoder exists.
  Their engine model buffers tokens split across input pages, rejects zero-length literals, and has a 2048-byte
  history. Their `recompress` does not keep page alignment. Stock X-Pro1 streams never split a token across a page,
  and our encoder keeps that stricter rule (EXR Pro is unverified).
* **Checksums:** complement-of-byte-sum integrity words (decoded vs raw bytes), implemented for type-6 headers only
  (X100V). Our type-4 rule (X-Pro1/X-E2/X-Pro2) is consistent with it and fills that gap.
* **SD boot / dual boot:** the boot ROM loads Fujifilm service `SD_BOOT` files. For EXR/EXR Pro these are `ffsys.bin`
  (512-byte header) + `ffboot.bin` (small loader) + `ffuser.bin` (RAM image). The camera can run firmware from the card
  without writing flash (dual boot), or boot a broken camera to reflash it (recovery). Their README rule:
  *"DO NOT FLASH CUSTOM FIRMWARE TO YOUR CAMERA WITHOUT DUAL BOOTING FIRST."*
  **X-Pro1 status:** recovery `canBuild = false` (missing "version-independent stock updater acceptance"),
  SD-boot button combination unknown (X-E2: command dial press + Fn7; X-T1: AE-L + Fn1), no test/progress records,
  `flash reader contract is not implemented` for exrpro.
* Their closed-source mod adds film sims on supported bodies (ETERNA, Neutral, approximations of Classic Neg.,
  Bleach Bypass, Nostalgic Neg., REALA ACE, plus a card-based FILM EDITOR). The X-Pro1 is not supported.

## Camera-confirmed facts (user, 2026-11-05)
* **Firmware-update mode:** hold DISP/BACK while switching ON → confirmation screen showing the current firmware
  version and the update file. This is stock update mode, **not** SD dual boot (that key combo is still unknown).
* fujimod.com refuses the X-Pro1 ("camera not supported yet"), so dual boot via fujimod is unavailable.
* Next safe experiment: `build/test_bad_checksum/` (stock payload, wrong 0x20c checksum) shows whether the updater checks
  the checksum before the confirmation screen. Always cancel at the confirmation screen.

## Session 2026-11-05: signatures and candidate risk check
* **No firmware signature on the X-Pro1.** The update file is header type 4. Its integrity data is only two additive
  checksums (payload @0x20c, trailer in the section table). The 0x21c-byte trailer is a structured offset table, not a
  signature. No MD5/SHA/CRC constants exist in the boot code, the stubs or either code image. fujimod: only type-8 headers
  (newer bodies) carry an ECDSA DER trailer. A user-supplied quote about "mandatory signed updates" concerns Canon
  DIGIC 9+ and new firmware, and doesn't apply here.
* **Candidate vs stock, region by region** (`build/ccswap_candidate/FPUPDATE.DAT`):
  identical: param block, boot code/vectors, both loader stubs, section/load table, blob2 (compressed and decoded),
  modules, lens/LUT tables, UI DB/fonts/icons/JPEGs, trailer.
  changed: header (3 bytes, checksum), tuning area (75 bytes), blob1 compressed stream (1,237,269 bytes, fully
  re-encoded). Decoded blob1: 128 bytes in 11 runs, 0x80ba60..0x822436 (curve-table slot + tuning mirror), all in
  data (ARM-word density 0.0–0.06). **No executable code changed.**
* **Risk rating: low-to-moderate.** The content is data in the existing formats and ranges. The main risk is packaging:
  the re-encoded blob1 has never been through the camera's hardware LZ engine. A bad decode means the main firmware
  won't boot, the SD updater lives in that firmware, and SD recovery isn't available for the X-Pro1, so it would
  probably mean a service repair.
* **Lower-risk option (not built yet):** a tuning-only variant. It changes only the 75 uncompressed tuning bytes plus
  the checksum, and leaves blob1 exactly as Fuji compressed it. That gives CC colour matrices and repointed tone IDs but
  no curve #38: the IDs must then keep their current values or point at an existing curve, because #38 would not exist.
  It may have no effect if the updater keeps the camera's tuning data.

## Session 2026-11-05: candidate FLASHED (user)
* The user flashed the PRO Neg Hi → Classic Chrome candidate. The camera boots and shoots; EXIF: "X-Pro1 Ver3.82",
  FilmMode "Pro Neg. Hi".
  ⇒ **Confirmed on hardware:** the updater accepts our type-4 checksum, and the EXR Pro hardware LZ engine decodes our
  page-aligned re-encoded blob1 (`lzenc_chunked.py`).
* Samples in `../samples/`: `xpro1 cc 1.JPG` (X-Pro1, PRO Neg Hi slot) vs `xt20  cc 1.JPG` (X-T20, real Classic Chrome;
  X-Processor Pro, so not identical to the X-E2's CC). Same scene, different exposure (+0.3 EV on X-T20), light and framing.
  Measured: overall saturation 0.147 vs 0.114. Blue-grey fence teal sat 0.167 vs grey 0.075 (X-Pro1 blues much stronger).
  Greens/wood/neutrals ≈ equal. X-Pro1 slightly more contrast (σ 0.212 vs 0.191).
* **Not yet confirmed that the CC tuning is applied:** if the updater kept the camera's tuning area, PRO Neg Hi is
  still stock (which would also explain the strong teal). Test: same scene, same settings, PROVIA / PRO Neg Std /
  PRO Neg Hi on the X-Pro1.
* **Swap confirmed active (same-camera test, samples DSCF2696 PROVIA vs DSCF2697 PRO Neg Hi slot, 13 s apart, f/10
  ISO 800, AWB; CC shot +0.4 EV).** The PRO Neg Hi slot is LESS saturated than PROVIA (stock Neg Hi would be more):
  whole image 0.132 vs 0.239, tree −21%, grass −18%, brick −18%, teal fence −7%, green bin −3%, **blue bin +3%**.
  ⇒ warm/green chroma reduced as intended. **Blues/cyans are not muted** (also seen vs X-T20 CC, whose fence is near-grey).
  Tone/shadow depth not judgeable (exposure/AWB differ; contrast σ 0.271 vs 0.283).
* Next tuning step: desaturate blue in the 3×3 sRGB matrix (PRO Neg Hi preset 5, IDs 0xdb4b..) by pulling the blue row
  toward neutral (row sum kept at 1). The 2×2 chroma-axis assignment is still unconfirmed. Awaiting the user's choice of
  strength (half vs full toward X-T20).

## Public release package (2026-11-05): `../public/`
* `public/README.md`: public write-up (status, install, rollback, risks, what changes, technical notes, credits).
* `public/xpro1_cc_patch.py`: standalone patcher, Python 3 standard library only. It embeds just the 64 changed
  parameter values + the 72-byte curve #38 entry (no Fujifilm firmware), requires the official 3.82 file
  (SHA-256 709e26f6…), self-checks, and only writes output identical to the camera-tested build (fb0dc86b…).
  Verified: reproduces `re/build/ccswap_candidate/FPUPDATE.DAT` byte-for-byte in ~14 s; rejects other inputs.
* If the blue tuning (TODO) produces a v2, update PARAMS and RESULT_SHA256 in the script and the README status.

## Session 2026-11-06: updater version check ("LATEST FIRMWARE")
* Header parse `FUN_00f7e05c` → `FUN_010af358` stores into the update state struct (body: RAM 0x9c9828):
  +0x210/+0x214 = file version from header 0x204 (major) / 0x208 (minor, BCD); +0x218/+0x21c = installed version.
* Installed version = blob1 `0x857af0`: if tuning DB[0x206] == 0xff → DB[0x204].DB[0x205], else hard-coded 3, 0x82.
  Our files (stock, v1, v2) have DB[0x204..0x206] = 00 00 00 → 3.82. (If the camera keeps its own copy of that
  calibration-range area, a camera-specific value could apply instead: unverified.)
* Decision `FUN_00ee53f0` (body branch): parse error 3/5 or bad BCD (`FUN_00ee4e94`) → msg 0x57; type error 10 or model
  list mismatch (`FUN_00ee4bf4`) → 0x59; no file → 0x56; **not newer (`FUN_00ee5010`: major >, or = and minor >) → 0x58**.
* ⇒ a 3.82-labelled file is refused on a 3.82 camera; relabelling the header (outside both checksums) to 3.83 should pass.
  First 3.83 attempt reported refused by the user: card contents / on-screen versions not yet confirmed.

## Session 2026-11-06: v2 flashed (user) and checked
* v2 (header 3.83) installed after the card was found to still hold v1. EXIF afterwards: "X-Pro1 Ver3.82" ⇒ the camera
  reports its built-in version, not the file label (as predicted from blob1 0x857af0). Future builds: keep labelling 3.83.
* Same RAW, v1 in-camera JPEG (DSCF2723) vs v2 in-camera RAW conversion (DSCF2743), pixel-aligned (mean |ΔL*| 0.1):
  chroma ×0.956 median (p10 0.90, p90 1.00), no hue or tone change; cap C* 47.8 → 46.0. ⇒ the chroma-gain fix is active
  (this shot used gain column 134/128 = ×1.047) and in-camera RAW conversion uses the same tuning.
* Remaining red strength comes from the ported 3×3/2×2, not from a leftover parameter. Next: measure CC/PROVIA ratios
  per hue on the same RAW (X-Pro1 v2) vs genuine Fuji (X-T20 in-camera RAW conversion, PROVIA vs Classic Chrome).

## Session 2026-11-06: SD dual boot, state of play
* fujimod (HEAD 7a1bb27, 2026-11-06) now has a full **xpro1-382** SD recipe (and xe1-271), for our exact stock file:
  `ffsys.bin` = 512-byte param block (file 0x25c) with word +0x10: 0x300 → 0x301 ("hold power through SD load");
  `ffboot.bin` = their compiled EXR SD loader (1612 bytes, copies itself to SRAM 0xfff00800, loads the OS image with the
  ROM's u16 read ABI: open 0x80001a74, read 0x80001b38, fs 0xfff00000, checks length + CRC32); `ffuser.bin`/`ffimage.bin`
  = RAM image 0x16a0000 bytes: loader @0, section table @0x770000, stubs, UI DB, fonts, blob1/blob2 *decompressed* at
  0x774000/0xe0ec80, modules @0x1420000, BSS zeroed; loader edits 0x46d0/0x46dc/0x46f8/0x486c → `mov r0,#0` and
  section-table +8 := 1 (use preloaded sections). Their tool refuses to build only because of
  "version-independent stock updater acceptance" (their recovery-card policy). That is the version check mapped above.
* fujimod README: on SD boot, reads of update-installed internal storage come from the OS image ("firmware namespace
  appended"), so tuning-area edits should take effect in dual boot; per-camera settings/calibration stay in flash.
* **Trigger:** fujimod knows no SD-boot buttons for any EXR/EXR Pro body. X-Pro1 service manual p.3-12 ("X-PRO1 BOOT
  Mode Setup Screen"): DC coupler CP-W126 + USB cable, "switch camera power ON while pressing the shutter button and up
  key", LED lights green. That is the ROM boot mode, the strongest candidate for SD boot (cf. X-S1 = shutter + Fn1).
* fujimod repo declares no licence: don't vendor its loader binary into this repo; local use only, or write our own.

## Session 2026-11-06: search for boot-ROM service-mode references in the update file
Disassembled all code (loader @0 from file 0x4025c, stubs @0x40000/@0xd0000, blob1, blob2; capstone, linear).
* **No reference to the boot ROM or its workspace anywhere.** No movw/movt, mvn-built or pc-literal address into ROM
  0x80000000–0x80003fff that is used as code/data (all hits are bit masks, PTP/USB codes, or values in register-init
  tables of {value, 0xf000xxxx register} pairs); no access to ROM SRAM workspace 0xfff00000–0xfff007ff. No strings
  ffsys/ffboot/ffuser/SD_BOOT/boot mode. ⇒ The SD/USB boot decision and its button combination live only in the 16 KiB
  mask ROM (not in FPUPDATE.DAT; fujimod sha256 7dc7e332…, shared with X10).
* Loader reset path (0x4000): CPU-mode setup, BSS clear, core check (0x42bc reads a p14 ID register, compares 0x4003),
  MPU regions (0x41e8), main loader 0x47a4: GPIO 0xfff89214 bit2 test (power latch?), flash validity 0x4cbc, section loads
  (the calls fujimod NOPs). Nothing asks how the ROM booted.
* blob2 `FUN_010ae1bc` copies 0x100 bytes of code to SRAM 0xfff00800–0xfff00900 and jumps there: a standby/self-refresh
  routine (DRAM controller 0xfff88xxx, GPIO 0xfff89xxx wake bits; `FUN_010ae124` = ~1 s held-input poll). Not boot mode,
  but shows 0xfff00800+ is free SRAM at runtime (same area fujimod's SD loader uses).
* blob1 state-machine debug names include **C_JIG / S_JIG** (factory adjustment "jig" mode, the USB mode used by the
  X-Pro1_W adjustment software; table 0x77acb4, 153 names). The service manual's "BOOT mode" (shutter + up, USB, green LED,
  [F8] Firmware Download) could be the ROM USB-boot or this firmware JIG mode; the camera test distinguishes them
  (ROM mode: no firmware UI at all; JIG: firmware starts).

## Session 2026-11-06: SD dual-boot files built (`re/tools/build_sdboot.py`)
* Camera test: battery cycle + shutter + UP at power-on → blank screen (boot-ROM mode candidate; LED/USB not yet checked).
* Builder follows fujimod's xpro1-382 recipe; fujimod loader passed by path (sha256 6eeade09…, not vendored). Stock build:
  all 9 regions + ffsys header match the recipe hashes. Loader stage (388 B) audited: SRAM 0xfff00800, ROM open/read
  0x80001a74/0x80001b38, FS 0xfff00000, size + CRC32 checks, jump 0, halt on error; no flash access.
* `re/build/sdboot_v2/`: v2 content + marker (blob1 0x857a98 `mov r3,#'2'` → `#'9'`): photos taken while SD-booted carry
  EXIF "Ver3.89". v2 image differs from stock image only in the 129 blob1 bytes. ffuser 0x16a0000 B, CRC32 0x67d40a2c.
* Tuning DB (RAM 0x40d3b580) is not in the section table and has no direct code reference: filled at run time via the
  flash block reader (fujimod has no EXR Pro flash-read redirect), so in SD boot it most likely comes from flash.
* Card must be FAT (FAT32 / ≤32 GB SDHC); the user's 64 GB card is exFAT.

## Firmware versions, downgrades and rollback (X-Pro1 SD updater) — reference
How the stock updater (DISP/BACK + power ON, `FPUPDATE.DAT` on the card) decides, from blob2/blob1 code (3.82):

**The rule: a file is only accepted if it is strictly newer than the installed version.**
* File version = header 0x204 (major, u32) and 0x208 (minor, u32, BCD: 0x82 = .82). Parsed by `FUN_00f7e05c`, stored by
  `FUN_010af358` into the update state (body: RAM 0x9c9828 +0x210/+0x214). These header bytes are plain and outside both
  checksums (payload sum @0x20c covers 0x25c.., trailer sum covers the trailer), so the label can be changed freely.
* Installed version = blob1 `0x857af0`: if tuning DB[0x206] == 0xff → DB[0x204].DB[0x205], else the built-in constant
  3, 0x82. All our files (stock, v1, v2) have DB[0x204..0x206] = 00 00 00 → built-in 3.82. Stored at +0x218/+0x21c.
* Compare `FUN_00ee5010`: accept if file major > installed major, or majors equal and file minor > installed minor.
  Equal or older → message 0x58, shown as **"LATEST FIRMWARE"**. Same check, separate state, for lens (+0x230 block)
  and a third device type (`_DAT_009cf730` = 0 body / 1 lens / 2 other).
* Before that: BCD sanity `FUN_00ee4e94` (both bytes < 0x9a, low nibble < 10; 0xffffffff/0xffffffff = "no version",
  accepted) → else msg 0x57; parse error 3/5 → 0x57; wrong file type (10) or model list mismatch (`FUN_00ee4bf4`, header
  ASCII-hex model IDs 0001024x) → 0x59; no file parsed → 0x56.
* The version string ("Ver3.82" in EXIF and the version screen) is built by blob1 0x8579e8 from the same source
  (DB override or built-in "3.82"). It is not taken from the update file.

**Consequences**
* **No downgrade and no re-install with official files.** A camera on 3.82 refuses the official 3.82 file ("LATEST
  FIRMWARE") and any older official file. There is no official way back to an earlier firmware.
* **The installed version does not ratchet.** Flashing a file labelled 3.83 still leaves the camera reporting 3.82
  (confirmed: EXIF "Ver3.82" after v2), because the version comes from the firmware's built-in constant, not from the
  header of the last file. So any file labelled 3.83 or higher installs again and again on a 3.82-based camera.
  (A firmware whose built-in constant is higher, e.g. a future patched build that changes 0x857b30/0x857b38, would raise
  the bar for the next file. Don't change the built-in constant.)
* **Rollback to stock = official 3.82 content with a higher label.** `public/xpro1_cc_patch.py --stock FPUPDATE.DAT
  out/FPUPDATE.DAT --version 3.84` writes Fujifilm's file with only header 0x208 changed (`build/rollback_stock_384/`,
  sha256 bcb280fe…874; differs from the official file in that one byte). Untested on camera so far.
* **Older official firmware** (e.g. 3.80) would also need a label above the installed version to go in; its own
  built-in constant would then become the installed version. Not needed or tested.
* **Per-camera override:** if a camera's tuning area ever had DB[0x206] = 0xff (e.g. set by service), its version would
  come from DB[0x204..0x205] instead. Not the case in any update file; a camera with such a value would need a label
  above that number. The update screen shows both versions before anything is written, so check there.
* **Practical:** the "latest firmware" refusal happens before the confirmation screen, so it is always harmless.
  Most "still refused" reports are the wrong file on the card: check header bytes with
  `xxd -s 0x204 -l 8 FPUPDATE.DAT` (3.83 = `0300 0000 8300 0000`) or the SHA-256.
* **fujimod:** this is the "version-independent stock updater acceptance" their X-Pro1/X-E1 recovery recipe lists as
  missing; the header label is the answer for the X-Pro1 (worth sharing).

## Session 2026-11-07: SD boot not working yet → LED diagnostic
* Attempts so far were not valid tests: the first card had 0-byte boot files (copy not flushed), then the files were
  right but the card was exFAT. Valid card prepared: 29 GB FAT32, all three files verified (sha) and synced.
* Result with shutter + UP on that card: blank screen, camera does not appear on USB (no new device in lsusb/dmesg).
  So it's still open whether shutter + UP enters the ROM boot mode on battery, and whether the ROM loads the card.
* fujimod (HEAD 3385650): EXR and EXR Pro share one 16 KiB boot ROM (sha256 7dc7e332…). The **X-S1 (EXR)** SD-boot
  combination is **shutter + Fn1, no USB** ("usb": false). ⇒ For this ROM the trigger is "shutter + one button"; which
  X-Pro1 button sits on the X-S1's Fn1 line is unknown. Candidates: shutter + Fn, shutter + UP (service manual), shutter +
  other selector keys / AE / AF / DRIVE / Q.
* None of the fujimod EXR / EXR Pro recipes has hardware confirmation; their tool refuses to build X-Pro1 cards.
* **LED diagnostic** (`re/tools/build_sdboot_led.py` → `re/build/sdboot_led/`): ffboot.bin = fujimod's 372-byte
  green-led stub (sha256 494964bb…, audited: cpsid; (addr, clear, value) register writes; dsb; wfe loop) configured with
  the X-Pro1 status-LED writes derived as fujimod does from the stock data (blob1 0xd8498 descriptor pair, loader 0x44c0
  port-15 GPIO record): port 15 pin 2 on (active low), pin 0 off; 10 writes to 0xfff893c0–0xfff893d8 only. Green LED at
  power-on with a combination ⇒ the ROM ran code from the card. No ffuser.bin needed.

## Session 2026-11-07: X-Pro1 key wiring from the firmware → SD-boot combination candidate
LED diagnostic card (FAT32, verified) gave no LED with shutter + Fn, shutter + UP, shutter + other keys.
**Key map (blob1, 3.82).** Key-name table 0x776d28.. records {key code, hardware id, name ptr} (12 B; ends {0,0,UNKNOW_KEY}).
Key descriptors 0x85b8xx–0x85bec0, stride 0x1c, record R: R+0 id, R+4 flags, R+8 type, R+0xc channel or
`port<<16|pin`, R+0x10 u16 min / R+0x12 u16 max (ADC window) or R+0x12 active level (GPIO), R+0x14 debounce.
Scanner: blob1 0x85a1ec.. (GPIO: input reg 0xfff89014 + port*0x40; ADC: values array 0x9de7c8).
| input | keys |
|---|---|
| ADC ch6 (ladder) | UP 0x2f1–0x354, DOWN 0x21b–0x291, LEFT 0x155–0x1c7, RIGHT 0x097–0x0fb |
| ADC ch7 (ladder) | VIEW 0x000–0x064, QUICK 0x1e0–0x215, DISP/BACK 0x28b–0x2b9, MENU/OK 0x2de–0x307, AE-L 0x310–0x335 |
| ADC ch3 / ch4 (16 / 13 steps) | shutter-speed dial / exposure-compensation dial (ids 0x31c–0x338) |
| ADC ch1 (3 steps) | focus-mode selector MF / AF-S / AF-C |
| type 0x500 (callbacks 0x8584e8/0x858544/0x8585a0) | DRIVE, AE, AF |
| type 0x400 (0x001c0001, 0x001e0001) | S1 / S2 (shutter half / full) |
| GPIO 0-0 | id 0x30 (unnamed) |
| GPIO 2-10 | POWER switch |
| GPIO 2-12 | PLAY |
| GPIO 4-4 | viewfinder lever (EVF/OVF) |
| GPIO 8-2 | card detect |
| **GPIO 0-10** | **Fn** (`KEY_FMODE`, active low) |
| **GPIO 0-11** | **command-dial press** (`KEY_CMDL_PUSH`, active low) |
| GPIO 15-1 | id 0x2d (unnamed) |
* fujimod measured SD-boot buttons on EXR II bodies are exactly GPIO 0-10 + 0-11: X-E2 command-dial press (0-10) + Fn7
  (0-11); X-T1 AE-L (0-10) + Fn1 (0-11). ⇒ **X-Pro1 candidate: Fn + press the command dial** (no shutter). The X-S1
  (EXR, same ROM as X-Pro1) is listed as shutter + Fn1; its wiring isn't in fujimod's catalog, so it may well be the
  same two GPIO lines. The service-manual "shutter + up" is a different (USB/BOOT) mode or a different line.
* The user's early "Fn + command wheel" try was on an invalid card (exFAT / 0-byte files), so it proves nothing.

## ✅ 2026-11-07: X-Pro1 SD boot CONFIRMED on hardware
* **Combination: Fn + command-dial press, held at power-on** (after a battery out/in), FAT32 card with ffsys.bin (stock
  param block, +0x10 = 0x301) and ffboot.bin = LED stub → the green status LED lights. ⇒ the EXR Pro boot ROM loads and
  runs ffboot.bin from the card. Predicted from the firmware key map (GPIO 0-10 Fn + 0-11 command-dial press, the same
  two lines as the EXR II X-E2/X-T1 SD-boot pairs). Shutter + UP / shutter + Fn / exFAT cards: no boot.
* LED stub config (port 15 pin 2 on, active low) confirmed to drive the green LED.
* Next: full image (ffboot = fujimod EXR loader + ffuser.bin v2 with "Ver3.89" EXIF marker).

## Session 2026-11-07: full image with fujimod's loader → blank; own loader with LED progress
* Full sdboot_v2 card (fujimod loader) with Fn + command-dial press: blank screen, no indication (fujimod's loader
  shows nothing; any error = silent wfi). Unknown which stage failed.
* **Own loader `re/tools/sdloader.py`** (keystone; 604 B; ours, publishable): same ROM ABI as fujimod's (open
  0x80001a74("ffuser.bin"), size at [[0xfff00000]]+0x20, read 0x80001b38(dst, u16 len, &u16 got), 32 KiB chunks to
  0x40000000+, CRC32) plus green LED: ON at entry, TOGGLE every 512 KiB (≈45 toggles for 23.7 MB), OFF at hand-over
  (jump 0). Errors = endless blink code: 1 open failed, 2 file record/size, 3 read failed/short, 4 CRC.
* Emulator test (unicorn; `scratchpad/scripts/emu_sdloader.py`, ROM API faked): success path loads the real 23.7 MB
  ffuser (724 reads, 45 toggles, CRC ok, jump to 0, DRAM == file) and each error path gives its code.
  It caught a keystone bug: a conditional `bleq` to a forward label assembled as a branch to itself; avoid conditional
  bl to forward labels (all 27 branch targets now checked).
* `build_sdboot.py` now uses our loader by default (`--fujimod-loader PATH` for theirs). Card: ffboot.bin = ours
  (sha 3d45e9fe…), ffsys/ffuser unchanged; ffboot_fujimod.bin / ffboot_led.bin kept on the card, unused.

* Probe result (SRAM-placed loader, body 0xfff00800, sp 0xfff01ff8): LED on → off and stays off ⇒ **the ROM open()
  call never returns** (an error return would blink code 1). fujimod's loader has the same layout, which explains its
  silent blank screen. Hypothesis: the EXR ROM keeps file-system state in SRAM above 0xfff00448 (or on its own stack near
  the top of SRAM, which [0xfff00000] may point into), and the loader's SRAM copy / stack corrupt it.
* Next probe (`sdloader.build(..., probe=True, place='dram')`, card ffboot.bin sha dec0e746…): body at DRAM 0x41f00000,
  stack 0x41f80000, no SRAM writes at all. Emulator-tested.

* DRAM-placed probe (no SRAM writes): still on → off, stays off ⇒ ROM open() hangs regardless of SRAM. The ROM file
  API (fujimod's untested EXR ABI: open 0x80001a74(name)) cannot be used as is; without the ROM image we can't fix it.
  (Ideas: wrong address/arguments, card state torn down by the ROM before jumping to ffboot, IRQ vectors at 0 now
  overwritten by ffboot itself.)

## Session 2026-11-07: chain boot (no ROM file API)
Only the ROM's own load of ffboot.bin (≤ 64 KiB, 16-bit length) is known to work. New approach: ffboot.bin carries the
**stock boot loader** (file 0x4025c, 0x40000 B; raw-DEFLATE 30,479 B) plus a 3.5 KiB C stub (`re/sdchain/`: start.S,
main.c with our own inflate, link.ld; cross-compiled with zig cc -target arm-freestanding-eabi -mcpu=cortex_r4).
Stub: relocate to DRAM 0x41f00000, zero .bss at 0x41f60000, stack 0x41f80000, LED on, inflate loader to address 0
(LED toggles per 32 KiB), CRC32 check (code 4) / inflate error (code 5) / bad config (code 6), LED off, jump 0.
The stock loader then loads everything from flash exactly as a normal boot. `re/tools/build_sdchain.py` →
`re/build/sdchain/` (ffboot.bin 33,988 B, sha 6d955511…). Emulator: loader at 0 byte-identical, jump taken, error
codes correct. CPU note: loader uses MPU (c6) and TCM-region (c9) registers ⇒ Cortex-R4-class core.
Next if it boots: hook the loader's final jump (0x405c `mov pc, r3`) to patch blob1 in RAM (CC bytes + "Ver3.89").

* Chain boot on camera (slow-signal build 961bef77…): LED on → flicker (inflate) → steady glow ~1 min (CRC OK; the
  6-phase busy wait took ~60 s ⇒ CPU ≈ 13 MIPS in the ROM's clock setup) → off (jump to the stock loader at 0).
  Camera did not start (blank). So the stub + inflate + CRC work on hardware; the stock loader stalls or fails.
* Loader map: reset 0x4000 → modes 0x4060, stacks 0x40c4 (stack top 0x4000), BSS 0x67e0–0x7280, core id 0x42bc,
  core 0 → GPIO init 0x4f58, MPU 0x41e8, **main 0x47a4** (validity 0x4cbc, hw-ready wait 0x44dc on 0xfffa8000 bit 26,
  section table 0x4668, sections 0x4760, …), then `mov pc, r3` at 0x405c (entry from [0x67e0], r0 = [0x67e4]).
  Error handler 0x450c (resets all GPIO ports, halts). Boot-info words at DRAM 0x400a00f8/0x400a00fc.
* Marker build (`build_sdchain.py --markers`, card ffboot 902a1677…): trampolines at loader 0x9000 (0xff filler):
  main reached → green; loader done → green + orange (pin 0, presumed orange); error handler → orange blinking.

* Marker run: flicker → green glow ~1 min → off, and it **stays off**: the loader never reached main (t_main marker).
  Hypothesis: D-cache. The ROM likely runs with the D-cache on; our inflate writes the loader at 0 into the cache, the
  CRC (data side) passes, but instruction fetch reads stale RAM. Fix: `caches_off()` in the stub (clean+invalidate
  D-cache by set/way from CLIDR/CCSIDR, then clear SCTLR M/C/I, invalidate I-cache) before jumping; glow cut to one
  phase. Emulated on unicorn's Cortex-R5 model: OK. Card ffboot 87019367… (markers included).

* Cache-fix run (87019367…): flicker → off, stays off. Still no main marker. (That build turned the LED off before
  caches_off, so a hang there was indistinguishable.)
* **Trace build** (`build_sdchain.py --trace` → `re/tools/loader_trace.py`; card ffboot d5042070…): stub turns LED off
  after CRC, cleans D-cache, disables MPU/caches, clears SCTLR.V (low vectors), jumps 0. In the loader copy:
  green blinks k = 1..8 before each start-up call (1 modes 0x4060, 2 stacks 0x40c4, 3 core-id after BSS clear, 4 GPIO/
  clock init 0x4f58, 5 core-id, 6 MPU/cache 0x41e8, 7 core-id, 8 main 0x47a4); orange blinks k = 1..7 before main's
  steps (1 validity 0x4cbc, 2 init 0x4c64, 3 hw-ready wait 0x44dc, 4 section table 0x4668, 5 sections 0x4760, 6 0x468c,
  7 0x4ca8); undef/prefetch/data-abort vectors → green/orange alternating; error handler 0x450c → orange blinking;
  final jump → green + orange. Trampolines at 0x9000–0x9360, register save at 0x9f00 (no stack).
  `re/tools/emu_trace.py`: order verified in unicorn (Cortex-R5 model; p14 core id reads 0 there, so cp4 is skipped).
* Tools now in the repo (scratchpad gets wiped): emu_sdchain.py, emu_trace.py, loader_trace.py, build_sdchain.py,
  re/sdchain/*. Toolchain: venv with capstone, keystone-engine, unicorn, ziglang (zig cc as ARM cross-compiler).

* Trace run (d5042070…): **green/orange alternating forever = exception taken** (undef/prefetch/data abort vectors →
  t_crash). Earlier builds kept SCTLR.V=1, so the same exception went to the ROM's high vectors (silent). User did not
  report checkpoint counts before it.
* Suspect: IRQs. The stub ran with the ROM's CPSR (IRQs probably enabled: ROM SD driver); after switching to the
  loader's low vectors any pending IRQ enters the loader's IRQ handler (0xc8) before the loader is set up; the 0.5 s
  checkpoint blinks before 0x4060 (which masks I/F) widen that window. Cold NAND boot hands over with IRQs masked.
* Next build (card a50c7e8e…): stub `cpsid if` before caches_off/hand-over. Crash reporter instead of plain
  alternation: repeating ORANGE × type (1 undef, 2 prefetch abort, 3 data abort), GREEN × last checkpoint
  (CP_LAST at 0x9f40; 1-8 start-up, 9-15 main; none = no green group), BOTH × region of the faulting lr
  (1 loader 0x4000-0x8000, 2 loader 0x20000-0x40000, 3 trampolines, 4 SD stub, 5 loader 0x10000-0x20000, 6 other).
  Reporter turns caches off first so blinks stay countable. `emu_trace.py --report` verifies the encoding.

* IRQ-masked run (a50c7e8e…): user reported "1 green 4 orange" = report cycle ORANGE×3 + GREEN×1 + BOTH×1 (both LEDs
  together look orange) ⇒ **data abort, last checkpoint 1, in loader start-up code**: i.e. inside 0x4060 (CPU modes),
  which has no memory accesses but clears CPSR.A at 0x4070 ⇒ an **asynchronous (imprecise) abort left pending by the
  boot ROM** fires as soon as the loader unmasks it. Explains every chain failure (earlier builds: same abort into the
  ROM's high vectors = silent). A cold NAND boot has nothing pending.
* Next build (card 4ea6db00…): stub `drain_async_abort()` after caches_off: sets an abort-mode stack (0x41f7f000),
  points the loader's data-abort vector literal [0x30] at `absorb_dabt` (start.S: count + DFSR, `subs pc, lr, #8`),
  `cpsie a`, short wait, `cpsid a`, restores [0x30]; if one was drained the LED blinks ORANGE ×2 before the hand-over.
  Stub blink phase shortened to ~2 s. Crash report: region group now LONG blinks of both LEDs, 10-unit pauses.

* Drain run (4ea6db00…): green flicker → **ORANGE ×2 = pending ROM abort drained (diagnosis confirmed on hardware)**
  → then orange flashing in pairs, user count ambiguous ("5-6 times in double"); no green checkpoint reported.
  Blink-counting by eye is now the bottleneck.
* New: **binary crash report + video decoding.** Reporter (loader_trace.py): caches off, then repeating MARK (both
  LEDs long) and words MSB-first, one blink per bit (GREEN 0 / ORANGE 1): type 4b | last checkpoint 8b | async aborts
  absorbed 8b | exception lr 32b | DFSR/IFSR 16b | DFAR/IFAR 32b. Loader data-abort vector now absorbs asynchronous
  aborts (DFSR 0x406/0x408; counted at 0x9f44, resumed with `subs pc, lr, #8`) and only reports precise ones.
  `re/tools/led_video.py <video>` finds the LED, classifies frames (normalised R/G: G = red low, O = red high & green
  < 0.8, B = both high), prints blink groups and decodes the report. Verified end to end with
  `re/tools/synth_led_video.py` (emulated reporter → 30 fps H.264 video → exact report recovered).
  `emu_trace.py --report` checks three fault types + async absorption. Card ffboot ef59c1bc….

## ✅ 2026-11-08: SD chain boot runs the whole stock loader and enters the firmware (video-decoded)
`samples/video.mp4` decoded with led_video.py tracking (LED moves in the handheld video; per-frame peak of
max(R,G)−B): green flicker (inflate) 6–8 s → ORANGE ×2 (pending ROM abort drained) → green checkpoints 1…6 at ROM
speed (GPIO/clock init and MPU setup run fine) → green 7/8 as 0.4 s bursts (≈14× faster after the loader enables
caches) → **orange checkpoints 1…7: validity, init, hw-ready wait, section table, all sections loaded from flash,
0x468c, 0x4ca8** → 72.2 s both LEDs on for 0.1 s (t_final: jump to the firmware) → LED off (firmware re-initialised
GPIO) → LCD stayed dark for the remaining 15 s.
Firmware reads of the boot-info block 0x400a0000: GPIO snapshot used for power-on keys (POWER id 6, PLAY id 0x1e;
blob1 0x85b3xx), port-0 bit 5 (0x85ec44), magic words 'DETS' at +0x40/+0x80 (0x96f014), +0xfc warm flag (blob2
0xf3ca48). Nothing SD-specific found. Prime suspect now: timing (firmware started 72 s after power-on because of the
trace blinking; a power/sub-MCU handshake likely expects ~1 s).
**Production build** (`build_sdchain.py --hook`, stub compiled -DQUIET; card ffboot d9882560…): no delays (LED only
during inflate), drain, hand-over; loader untouched except the final jump → `loader_hook.py` RAM patcher at 0x9000:
for each (addr, old, new) write if *addr == old, DCCMVAC, then ICIALLU, jump. Default patch: Ver3.89 marker (blob1
0x857a98). Emulated: patches only when the old word matches, preserves r0–r6, jumps to the entry.
Card also holds ffboot_trace.bin (trace build) for later diagnosis.

## 2026-11-08: quiet chain boot + shutter wakes the camera; marker not applied → two-stage hook
* Quiet build (d9882560…): green flicker, then dark; **pressing the shutter brought the screen up** and photos were
  taken (DSCF2747–2749), but EXIF said Ver3.82: the Ver3.89 marker did not apply.
* Why: the loader does not jump to blob1. `0x468c` sets the entry [0x67e0] from **section 0's header (entry 0x40020)**
  and the argument [0x67e4] = blob1's entry (0x8554c4). blob1 (section 4) is unpacked by a hardware transfer started in
  `0x4b94` that may still be running when the loader jumps, so at our hook time 0x857a98 was not the expected word and
  the old-value check skipped it. (v2's word there is the stock 0xe3a03032.)
* Section 0 (0x40000, "syslog Ver 2.3"): entry installs its own vectors (low or 0xffff0000 per 0x42c88), clears BSS,
  stack 0x4005a0e0, then main 0x40b64 calls blob1's entry once per phase: `blx r4` with r0 = 0 at **0x40bac**, then 1,
  3, 2 (and 4 on another path), then starts the OS (0x41588).
* `loader_hook.py` now two-stage: stage A at the loader's final jump rewrites section 0's 0x40bac `blx r4` →
  `bl 0x9080` (if unchanged); stage B (0x9080) applies the blob1 patch table (old-value checked, DCCMVAC, ICIALLU)
  and `bx r4`. Emulated with the real section 0: both stages OK, registers/stack preserved. Card ffboot 7372fdf6….
* Open: after SD boot the firmware sits with the screen dark until the shutter is pressed (power-save / wake state?).

* Two-stage build (7372fdf6…): photo DSCF2750 still Ver3.82. EXIF Software string confirmed to come from the patched
  routine: modules 0x151aa34 / 0x163cbd8 / 0x161008c copy "Digital Camera " (0x151aab4 / 0x161122c), append the model
  (0x858298), then `bl 0x8579e8` (fallback branch writes the "3.82" digits; v2 DB[0x206] = 0). So either the patch
  did not apply, or the photos come from a normal flash boot triggered by the shutter press (SD-booted firmware dead).
  (0x857af0's other caller 0xf3db74 builds the USB device descriptor bcdDevice, not EXIF.)
* Diagnostic hook (`loader_hook.patch(diag=True)`, card ffboot 0d625083…): stage A OK → ORANGE flash; stage B all
  patches applied → GREEN long flash; failed check → MARK + 32-bit word found (GREEN 0 / ORANGE 1). Emulated: success
  (O, G, marker applied) and forced mismatch (sent word decodes to the memory value, boot continues).

* Diagnostic hook run (0d625083…): stub green flicker → stage A ORANGE → **no stage B** (no green, no mismatch
  report). Photo DSCF2751 Ver3.82. ⇒ section 0 never reaches the phase-0 call at 0x40bac; the shutter press starts a
  normal flash boot. Section 0's 0x42c88 is the same core-0 check as the loader's (DBGDSAR 0x4003). Hang/crash is in
  0x40460, 0x42810(0), 0x43db4, 0x43fc0 or 0x40d40. **Failure log: `re/FAILURES.md`.**

## Session 2026-11-08: section 0 start-up analysed statically → exception reporter card
* Section 0 emulated (unicorn, real sections at their RAM addresses, 0 aliased to 0x40000000, core-0 check forced) from
  its entry 0x40020 to the phase-0 call 0x40bac: 142k instructions, **no hardware polling at all**, CPSR stays
  0x1d3 (IRQ/FIQ masked). Device accesses: only the interrupt controller 0xfffb3xxx (0x43fc0 → 0x4307c fills 95
  vector slots 0x400+4n = 0x42d10 and priorities 0x800+4n = 0xf; 0x40d40 → 0x43944/0x43558 registers source 0x5a with
  handler 0x40d8c, priority 0, enable bit at 0x128/0x088). DRAM only otherwise. No unaligned access, VFP or SVC.
* Exceptions in that window: vectors 0x24..0x3c ← literal pool 0x400e0 (0x40100 undef, 0x401a8 svc, 0x4011c pabt,
  0x4013c dabt, 0x4015c reserved, 0x40228 irq, 0x40178 fiq). undef/pabt/dabt/reserved → 0x40dd0: save frame at
  0x4004d7ac, log (0x42700), then spin at 0x40e60 unless [0x4004d7a0] != 0 (BSS, still 0) ⇒ silent hang.
* Loader MPU 0x41e8: regions 0–3 only (+4 on core 1), SCTLR |= 0x1005; BTCM never written. ROM leftovers survive.
* Loader 0x4f58 copies GPIO inputs (0xfff89014 + 0x40·port, 17 ports) to 0x400a0000..; 0x46ec skips the blob1 load
  (0x4b94) if [0x400a00fc] != 0. blob1 load: memset engine (regs at 0x40021420) + NAND read via buffer 0x42420000 and
  callback 0x20e50; waits for completion only if the memset call returned 0.
* Stub reproducibility: `re/sdchain/build.sh <venv python> <outdir>` (zig cc -Os) rebuilds chain.bin and
  chain_quiet.bin byte-identically to the ones on the earlier cards. Stub .bss: absorbed[] at 0x41f60004/8.
* **Card `re/build/sdchain_sec0trap/`** (`build_sdchain.py FPUPDATE.DAT chain_quiet.bin out --sec0trap`; ffboot
  57dae4c0…, ffsys 7661dadc…): quiet stub + drain; loader final jump → `sec0_trap` PRE (0xa000: save SCTLR, MPUIR,
  enabled-region bitmap, BTCM/ATCM, ACTLR at 0xaf00; repoint the pool at traps 0xa500+8k) → loader_hook stage A
  (ORANGE) → section 0. Stage B first calls RESTORE (0xa400: original literals back into 0x24..0x3c), then GREEN +
  marker as before. Trap → caches off → repeating report (sec0_trap.FIELDS, 216 bits, ~65 s per cycle):
  progress<<4|type, lr, spsr, DFSR/IFSR, DFAR/IFAR, SCTLR, MPU region count, enabled bitmap, BTCM, stub-drained ROM
  aborts + their DFSR. Decode: `led_video.py <video> --layout sec0`. Emulated (`emu_sec0_trap.py`): clean run →
  blob1 entry, marker 0xe3a03039, handlers restored, LED O then G; injected dabt at 0x43148 → exact decode, also from
  a synthetic 30 fps video.

* **sec0trap card result (F18):** stub flicker → stage A ORANGE → nothing. No exception report, no stage B; shutter →
  flash boot, DSCF2752 "Ver3.82". ⇒ section 0 stops without any CPU exception. Candidates: bus stall on the interrupt
  controller 0xfffb3xxx (unclocked / held in reset after the ROM's SD boot: no abort, just a hang), or power cut/reset.
* **Checkpoint card `re/build/sdchain_sec0cp/`** (`--sec0cp`; ffboot aa2865e8…, ffsys 7661dadc…): sec0trap +
  `sec0_cp.py`: loader final jump → CPI 0xb000 (re-points the five `bl` sites 0x40b90/98/9c/a0/a4 at trampolines,
  old words checked) → sec0_trap PRE → stage A. Checkpoint k: GREEN ×k, then ORANGE steady while routine k runs.
  Emulated: clean run O,G,O,GG,O,…,G×5,O,G → blob1 entry; injected dabt in routine 4 → OGOGGOGGGOGGGGO then report.
  On the card as ffboot.bin; previous ffboot kept as ffboot_sec0trap.bin (and ffboot_hookdiag.bin).

## Session 2026-11-09: warm-resume idea (option 3) ruled out statically
* Standby (blob2 0x10ae1bc) is in-place: SRAM routine at 0xfff00800 (DRAM self-refresh via 0xfff88000/0xfff88080),
  returns on wake; then sets [0x400a00fc] = 1 or 2 (wake source 0xfffb3008 bits 28/29) and re-snapshots GPIO.
* Loader reset 0x4000 writes 0 to 0x400a00fc before anything else ⇒ the blob1-skip at 0x46ec is dead after any
  restart. Loader reads in 128 KiB blocks; the section-table read 0x4a28(0xe0000 → 0x770000, 1 block) writes
  0x770000-0x790000 (16 KiB table + zeros), i.e. zeroes blob1's head every boot. main(r5): r5 = core id (0x42bc).
* Power hold = 0xfff88084 bit 0: set in loader system init (0x50b8), cleared only by the loader error handler 0x450c
  ⇒ after an SD-boot hang in section 0 the camera stays powered (DRAM refreshed) until the shutter restart.
* blob1 phase 0 clears its BSS (0x9c89c0 + 0x372bc0) only if section table +8 == 1 (0x7ebdf4 → [0x770008]).
* Environment is now persistent: `sh re/tools/setup_work.sh` (venv ~/.venvs/xpro1-re, extracted files in re/work/,
  gitignored); `re/tools/fnasm.py` dumps a function with literals.

## Session 2026-11-09: USB debug firmware (PTP peek/poke/call) — built, not yet flashed
Goal: read the boot ROM and live hardware state from the PC instead of LED/SD experiments (FAILURES P7).
* PTP dispatcher blob2 `FUN_00f4521c(phase, request)`: opcode high byte → table, low byte → index:
  0x10xx → 0xf4c028[≤0x1c], 0x90xx → 0xf4c09c[≤0x1d], 0x98xx → 0xf4c114[≤0x0b], else 0xf4c028[0] = 0xf4bff0 (0x2005).
  Stock vendor handlers: 0x900c → 0xf494e8, 0x900d → 0xf48664, 0x901d → 0xf482cc; MTP 0x9801.. at 0xf4c118...
  Supported-op lists 0xf52594 (25 ops) / 0xf52658 (23, chosen when the host's OS descriptor says "Windows").
* Handler protocol (from GetStorageIDs 0xf4a840 / CloseSession 0xf4bf58): request +0 opcode, +4 session, +8 tid,
  +0x10.. params; session open = [0x11f3c2c] != 0; status var 0x11f3c30; data container 0x11f3bc8 (FUN_00f45510
  copies the request, +0x24 data pointer, +0x28 length); buffer = storage callback table [0x11f3bb0] = 0xf5100c,
  entry +0x1c = 0xf4c144(size, &ptr, 0, kind): kind 7 → 0x42dfad10 (4 MB) or 0x461d9110, min(size, capacity);
  FUN_00f44ca8(container, 0) sends data or response; FUN_00f459dc(request, container, code) builds the response.
* `re/tools/build_ptpdebug.py` (v2 file → `re/build/ptpdebug_385/FPUPDATE.DAT`, label 3.85, sha256 64f7d923…):
  nine dead "not supported" stubs 0xf45a58–0xf45c08 (only table-referenced) → their slots get 0xf4bff0; the cave
  holds 0x9010 PEEK (addr, len ≤ 0x10000, word reads → data phase), 0x9011 POKE (addr, word), 0x9012 CALL (addr, r0;
  result word at 0xf45c04). 405 blob2 bytes changed; blob1 and everything outside blob2's partition = v2.
  Checks: `emu_ptpdebug.py re/work` (real dispatcher, 11 cases incl. no-session and untouched stock ops) ALL OK;
  output decodes to v2 blob2 + patch; fpupdate.verify OK; 0 tokens across 16 KiB pages (as stock).
* PC side `re/tools/ptpdebug.py` (pyusb): info / peek / poke / call / dumprom (16 KiB at 0x80000000, compared with
  fujimod's 7dc7e332…). Framing unit-tested against a fake endpoint with real short-packet behaviour.

## ✅ 2026-11-10: USB debug firmware flashed and working; boot ROM dumped
* `build/ptpdebug_385/FPUPDATE.DAT` flashed. Camera enumerates as 04cb:0280 "USB PTP Camera"; `ptpdebug.py info`:
  GetDeviceInfo OK, **debug PEEK works**. `ptpdebug.py dumprom` → `re/work/rom/bootrom_80000000.bin` (gitignored),
  sha256 **7dc7e332… = fujimod's EXR/EXR Pro ROM**. The ROM is 8 KiB, mirrored twice in the 16 KiB window.
  Disassembly: `re/work/rom/bootrom.asm`.
* Reset 0x80000028: SVC, sp 0xfff00f00; MPU region 0 = 0..4 GB normal non-cacheable, region 1 = 0xfff00000 1 MB
  strongly-ordered XN (subregions 0 and 7 off), MPU on; [0xfff88084] = 1; ROM data → 0xfff00000, BSS
  0xfff00004–0xfff00448. Boot mode 0x800001a0: bits = (GPIO0 >> 10 | GPIO2 >> 12) & 7 (Fn = bit 0, dial press =
  bit 1): 0 → 0x8000059c(0), 4 (Fn + dial) → **0x80000690 SD**, bit 2 clear → 0x8000059c(1), (bits & 0xc) == 4 →
  0x80000770(0) NAND, else 0x80000770(1). Raw bits stored to [0xfff98000]. Success → 0x80001ee0: [0xfff98008] = 1,
  clear APSR flags, `mov pc, #0`. Failure → wfi loop.
* SD path 0x80000690: mount 0x80001858(fs = 0xfff00204; sets [0xfff00000] = 0, then the fs pointer), ≤ 3 tries
  (fail → [0xfff88084] = 0, off); open 0x80001a74("ffsys.bin") (name in r0, fs from [0xfff00000]; 6 = not mounted);
  read 0x80001b38(0xfff00004, 0x200, &got); params 0x8000024c; tries = ffsys+0x10 bits 8-10; open("ffboot.bin");
  read(0x40000000, (u16)[0xfff00224] = file size, &got).
* NAND path 0x80000770: 0x80000970 init, reads the param page (magic 0x00ffaa55 0x01234567 0x89abcdef at +0/+4/+8,
  same as ffsys.bin), 0x8000024c, loader via 0x80000b04 (uses 0xf7f7e000 / 0xfff46800).
* Common params 0x8000024c: [0xfff88084] = +0x10 bit 0; clocks 0xfff98000 / 0xfff88000 from +0x14..+0x48; PLL
  change uses the interrupt controller (0xfffb3108/154/128/088 then wfi, then restores); DRAM controller 0xfffb0000.
* **Only the SD path touches SDHCI controllers 0xfff44000 (SD0) / 0xfff45000** (standard SDHCI layout: +0 SDMA,
  +4 blksz, +6 count, +8 arg, +0xc mode, +0xe cmd (0x113a = CMD17), +0x2c clock, +0x30/+0x32 int status). The
  interrupt controller, clocks, MPU and DRAM setup are identical on both paths.
* Sector read 0x80001ca4(dst, sector, offset, len): dst in 0x40000000–0x4fffffff → SDMA of the **whole 512-byte
  sector straight to dst** (offset/len ignored); otherwise via buffer 0xfff00248 + byte copy. ⇒ **F5/F6 explained**:
  open()'s directory search uses small buffers on the caller's stack; F6's stack in DRAM got whole sectors DMA'd onto
  it (stack smash); F5's stack top 0xfff01ff8 is beyond the 4 KB SRAM the loader's MPU maps (ROM stack is 0xfff00f00).
  A working ROM-file-API loader needs its stack in SRAM ≤ 0xfff00f00 (above the ROM BSS / fs struct) and
  sector-aligned reads into DRAM with ≥ 512 bytes slack.
* **RAM persists across USB mode** (2026-11-10): POKE 0xf45c04 = 0xc0ffee11 → unplug → photo → replug → still there.
* **Live tuning DB = RAM 0x40d3b580** (+ ID): 65267/65536 bytes equal the flashed area (file 0xae025c); the 269
  differing bytes are per-camera data laid over it at start-up (calibration, serial, lens/sensor tables; offsets
  0x3–0x38a, 0xcbe–0xd8a, 0x1662–0x283c, 0x4b73–0x4d65). Film-simulation tables identical to v2.
* ✅ **RAM tuning edits take effect live** (2026-11-11): chroma-gain preset ID 0xe4ec (RAM 0x40d49a6c) poked 1 → 2,
  unplug, in-camera RAW conversion of DSCF2723.RAF with PRO Neg Hi (same settings as DSCF2743) → `samples/DSCF2723 b.JPG`.
  `re/tools/compare_jpeg.py`: vs v2 conversion DSCF2743 chroma ×1.048 (reds ×1.051), |ΔL*| 0.07, hue 0°; vs the v1
  JPEG DSCF2723 ×1.000, |ΔL*| 0.02. Exactly v1's processing ⇒ Classic Chrome variants can be tried by POKE + in-camera
  RAW conversion, no flashing; switching off restores the flashed values.
* **`re/tools/tune.py`** (2026-11-11): live tuning by parameter ID over USB. show / get / set / setm / setmat /
  restore / diff; groups cc3x3, cc3x3alt, cc2x2 (×1024 fixed point, 13-bit), chromagain, detail, hstone, curveno.
  Byte-level read-modify-write on 32-bit POKE with read-back; refuses unless the live byte is the flashed value or
  the value tune.py last wrote in this power-on session (session tag kept in RAM slot 0xf45c04); per-camera ranges
  and IDs ≥ 0x10000 refused without --force; log `re/work/tune_log.jsonl`. Offline `selftest` OK; on the camera:
  set 0xe4ec 02 → show → restore all → diff = flashed.

## Session 2026-11-11: loading a 3D LUT's camera approximation (`tune.py lut`)
* `luts/ColorReps-classic-chrome.cube`, `luts/fujifake_classicnegative_rossandhisjpegs.cube` (33³; the latter
  expects Panasonic Lumix STD input). The camera has no 3D-LUT stage → fit with its controls.
* **Tone-curve format solved**: blob1 table 0x80b700 (29 entries × 0x48: u32 curve#, u8 seg[9], pad, u16 knot[28]).
  Segment j spans 2^(seg_j+6) of a 0..16384 linear input, 3 equal knots per segment (27) + terminator 0; output 14-bit.
  Proof: curve #39 (used via ID 0xddca, a linear path) is the identity within ±2. All film-sim curves use seg
  2 2 3 4 5 5 5 6 6. PROVIA = matrix preset 1 + curve #0 (IDs 0xdf8d/0xdf94, blend weight 100).
* Curve selectors: method reproduces PRO Neg Hi's 42 IDs exactly; **PRO Neg Std's 42**: 0xde01–0xde12,
  0xde7f–0xde90, 0xdf90 0xdf97 0xdf9e 0xdfa5 0xdfac 0xdfb3 (0xdfa5/0xdfb3 hold 16 = special mode, kept); shared with
  no other colour mode. **Unreferenced curve slot #41** at 0x80baa8 (also free after v2: #1–3, #24, #25, #27, #28;
  #39 is used; override 0xe14d = 0 → curve 28 off).
* PRO Neg Std selectors: 3x3 sRGB preset 4 (0xdb39…), alt 9 (0xdb93…), 2x2 4 (0xe3c1 m00, 0xe3c3 m11, 0xe3c5 m01,
  0xe3c7 m10), chroma gain 0xe4eb, detail 0xffc5 (= idx 3 of 0xf2e39c), H/S family 3 planes 0xe13a/0xe141/0xe148.
  PROVIA refs: 3x3 0xdb03…, alt 0xdb5d…, 2x2 0xe3a9…, H/S 0xe137, chroma gain 0xe4e8, detail 0xfff0.
* `re/tools/lut_fit.py camera_fit_opt`: model display = curve(M·x) on camera-linear x; target = LUT(PROVIA render);
  joint least squares (9 matrix + 27 knots, Lab residual, greys ×3). ColorReps CC: ΔE76 median 9.97 → **3.33** (p90
  6.75, greys 1.43). Classic Negative fake: 19.6 → 7.6 (p90 14.6): hue-dependent look, poor fit.
* `tune.py lut FILE [--dry-run]`: writes slot #41 knots, ns3x3/ns3x3alt (alt = M·M_P⁻¹·M_Palt), ns2x2 := PROVIA,
  selectors := PROVIA, 40 curve selectors → 41. Self-test (fake camera incl. blob1) checks PROVIA/PRO Neg Hi untouched,
  blob1 changed only in slot #41, `restore all` → flashed. Dry run on the camera OK (live curve #0 read).
  **Not yet tested on images**: convert one RAW as PROVIA / PRO Neg Hi / PRO Neg Std and compare.

## Session 2026-11-11: SD-boot base with breadcrumbs (DRAM notes read over USB) — built, not yet run
* DRAM = 256 MB 0x40000000–0x4fffffff (no aliasing). After a normal boot most of it holds data; untouched blocks keep
  the DRAM power-up stripes (00000000/ffffffff words, a few single-bit flips): 0x43d00000–0x43ffffff, 0x46f00000,
  0x4b600000, 0x4ea00000, 0x4ed00000. Breadcrumb block: **0x43f00000** (1 KB).
* `re/tools/crumbs.py` (loader patch, 0x9000–0xbfff): snapshot at the final jump (CPSR, SCTLR, MPU, boot ctrl
  0xfff98000/8, power hold, SDHCI0 +0x24..0x38, intc 0xfffb3000..10c), checkpoints at section 0's five calls, stage B
  (0x40bac; restores svc/reserved/irq/fiq literals, Ver3.89 marker), blob1 phases 1/3/2 and OS start; fatal vectors
  (undef/pabt/dabt) → exception record + heartbeat, chaining to section 0's handler if [0x4004d7a0] != 0.
  Stub `-DCRUMBS` (re/sdchain/main.c, build.sh → chain_crumbs.bin 19069ea8…): header, boot-ROM snapshot, progress
  0x01–0x03, drained abort count/DFSR. No LED signals except the stub's inflate flicker.
* Card `re/build/sdchain_crumbs/` (`build_sdchain.py … chain_crumbs.bin out --crumbs`): ffboot f0b41d31…, ffsys
  7661dadc…. `emu_crumbs.py` ALL OK (stub; clean run to blob1 with marker; phase checkpoints; injected data abort →
  record + heartbeat; resume flag → chains). Reader `re/tools/sdcrumbs.py` (verdicts incl. DRAM power-up pattern).

## Session 2026-11-11: SD dual boot solved; UI recolouring
* **Root cause of every SD-boot "dark screen" (FAILURES E25/F21):** blob1's start-up task 0x85505c powers the camera
  off (0x7a65fc clears power hold 0xfff88084) when the power-on cause is invalid; the cause uses the loader's GPIO
  snapshot port 2 bit 11, which is gone by the time the SD chain reaches the loader. Fix in `crumbs.py` PRE (set bit
  11, release Fn/dial in the snapshot). `build/sdchain_poweron/` booted by itself; DSCF2758 EXIF "Ver3.89".
* Power/DRAM facts (E26, `tools/dramtest.py`): switch OFF/ON = standby, DRAM kept; battery out or power hold = 0 →
  DRAM lost (00/ff stripes). A photo overwrites DRAM 0x43f00000.
* `tools/dramdump.py`: whole 256 MB DRAM over USB in 47 s. Live-view buffers YCbCr 4:2:2 640×426 at 0x4250a600,
  0x425f4c00, 0x426df200, 0x427c9800; layer descriptors around 0x40f8cfb4 (640×480). The menu OSD can't be caught
  this way (USB mode redraws).
* **UI colours (E27, `tools/uicolor.py`):** GVFF vector graphics in the UI DB; colour record = tag 0x00001b00 + RGBA
  float32. list / check / set R,G,B --from R,G,B / swaprg / restore, all live over USB. swaprg (5068 words) made the
  menu accent green. `crumbs.patch(..., uiswap=True)` / `build_sdchain.py --crumbs --uiswap` does the same at stage B
  (routine at loader 0xa000; backwards scan, because 7 record pairs overlap). Card `build/sdchain_green/`.

## Session 2026-11-12: tone re-checked, colour matched to the X-T20 sample, menu name (v3 candidate)
* **Tone is applied** (camera on USB, running `ptpdebug_385`): live curve table (blob1 RAM 0x80b700, 29 entries) holds
  #38 byte-identical to the X-E2 Classic Chrome curve; all 40 PRO Neg. Hi selectors read 38 (18 + 18 in
  `FUN_00f3232c`'s tables 0xf3448c / 0xf34298, 4 in `FUN_00f321f0`'s); `tune.py diff`: live area = flashed.
  `FUN_00f32808` picks `FUN_00f321f0` or `FUN_00f3232c` by recctl+0x104 / +0x180; both end at curve 38. PROVIA uses
  curve #0 in every entry of its tables, so there is no DR-specific curve to port.
* **2x2 chroma matrix axis order: [Cr, Cb]** (m00 = Cr gain, m11 = Cb gain). Two checks: (1) predicting the Classic
  Chrome shot DSCF2697 from the PROVIA shot DSCF2696 through the known matrices and curves gives mean Δab 1.06 with
  [Cr, Cb] and 1.52 with [Cb, Cr]; (2) PROVIA's effective linear matrix is closer to the sensor's colorimetric matrix
  (dcraw X-Pro1) with [Cr, Cb] (distance 0.69 vs 0.95; same for the other film simulations). Not yet confirmed by a
  one-axis poke + RAW conversion.
* **Pipeline model used:** JPEG → Y'CbCr (BT.601) → undo 2x2 → inverse tone curve per channel → new 3x3 · old 3x3⁻¹ →
  tone curve → 2x2. Scratch scripts only (not in the repository).
* **X-Pro1 (`xpro1 cc 1.JPG`, v1, ISO 320) vs X-T20 (`xt20 cc1.jpg`, genuine Classic Chrome, DR400)**, 12 patches,
  white balance / exposure normalised on four neutral patches: the X-Pro1 is greener in everything (fence a* −5.8 vs
  −3.4, grass −18.5 vs −14.8, weathered wood +5.8 vs +2.6), b* equal. Fitting the 2x2: **[[0.67, −0.03], [0.035, 1.01]]**
  (v2: [[0.959, 0.034], [0.016, 1.066]]) → mean Δab 2.10 → 0.74. Fitting the 3x3 as well: 0.73, so the 3x3 stays.
  Limits: one overcast scene, no saturated reds, blue sky or skin; the two cameras' sensors and AWB differ. The
  third-party LUT `ColorReps-classic-chrome.cube` does not support the change (it prefers Cr gain 0.82–0.97).
* **Menu text (`tools/uiname.py`):** 35 language blocks of 0x20000 at file 0x104025c (flash 0x1040000), whole block
  loaded to RAM 0x4f0000 (resource table blob1 0x84bd1c: {flash offset, block count, RAM address}; English = block 1).
  Block = packed UTF-16LE strings + 12-byte text descriptors {string pointer, 100, 100, alignment} + pointer table,
  absolute addresses. "PRO Neg. Hi" occurs 3× per block (one with icon U+F201; the icon follows the name in the
  three right-to-left blocks 22, 23, 30), each behind one descriptor. New string goes into the unused 0xff tail of the
  block, descriptors are repointed. Icons, EXIF FilmMode and the ASCII names in module 0x41 are untouched.
* **Live on the camera (RAM only, until the battery is removed):** `uiname.py set` (CLASSIC CHROME) and
  `tune.py setmat cc2x2 0.67 -0.03 0.035 1.01`. Not yet looked at on the camera.
* **Builds (`tools/build_cc3.py`, not flashed):** `build/cc3_candidate/` (v2 + both changes, label 3.86, sha 72fe08f5…)
  and `build/cc3_ptpdebug/` (same on top of the USB debug build, label 3.87, sha 66cbf5b2…). Checked: container
  checksums, blob1 decodes with the independent decoder, no page-straddling token, blob2 identical to the base,
  changes = 4 matrix values (both copies) + 3649 language-block bytes. After flashing `cc3_ptpdebug`, run tune.py
  with `XPRO1_INSTALLED=re/build/cc3_ptpdebug/FPUPDATE.DAT`.
* User (2026-11-12): the live rename shows CLASSIC CHROME in the menu. Colour not yet judged on a conversion.

## Session 2026-11-12: Classic Chrome v3 on the SD dual-boot card (run-time hooks) — built, emulated, not yet booted
* Neither data set can be patched at stage B: both are read from flash after the firmware starts.
  **Tuning area:** blob1 `0x857e44` = load(0x40d3b580, 0xb3700) through `0x863940` (128 KiB block reads), called from
  blob2 0xf28578 / 0xf7da88 / 0xf8150c. This answers the open question: the run-time area comes from flash 0xae0000,
  not from the blob1 copy 0x812470. **Language block:** blob1 `0x86334c(language 0..0x22)` → `0x8632a4` → RAM
  0x4f0000 (callers 0x7a0290, 0x970d2c).
* `tools/cchook.py`: stage B redirects the `bl` at 0x857e5c and 0x863388 (old words checked) to hooks in the loader
  filler 0xa400–0xaae0. Hook 1 rewrites the four 2x2 values if they hold the v2 values. Hook 2 writes a
  `uiname.py`-compatible tail at block offset 0x1f000 and repoints the matching descriptors (table of all 105).
  The loader area 0x9000–0xbfff is still 0xff in the running flash-booted firmware (USB read), MPU region 0 is
  executable, and the firmware's own MPU routine (0x9710e0) only adds no-access guard regions 5–7.
* `build_sdchain.py --crumbs [--uiswap] --cc`; cards `build/sdchain_cc/` (ffboot 6239132a…) and
  `build/sdchain_cc_green/` (ffboot 18ec6554…, **on the user's card**, ffsys 7661dadc…). Without `--cc` the builder
  still reproduces the previous green card byte for byte (276f1752…).
* `tools/emu_cchook.py` ALL OK: stage B changes exactly the marker + two call sites; real blob1 0x86334c for all 35
  languages → CLASSIC CHROME, three descriptors, `uiname.unpatch` restores the block, r0 and stack kept, no entry
  matches a foreign language, failed read writes no descriptor; real 0x857e44 → only the four values change, v3 or
  official 3.82 values stay. `emu_crumbs.py` ALL OK on both cards.
* **Camera test (one question: do the hooks run?)** Battery out and in, Fn + dial press at power-on. Then USB:
  `uiname.py show` → 'CLASSIC CHROME', `tune.py show cc2x2` → live 0.670 / −0.030 / 0.035 / 1.010; a photo's EXIF
  says Ver3.89. Not proven on hardware: that the hook area stays executable and untouched in an SD boot.

## Session 2026-11-12 (later): first --cc card result, start-up tuning load found, card fixed
* New samples, all in-camera conversions of DSCF2730.RAF under the SD-booted firmware (EXIF Ver3.89, card ffboot
  18ec6554…): DSCF2761 PROVIA, DSCF2759 CC slot, DSCF2760 CC slot Colour −1 / Highlight +1, DSCF2762 Velvia.
* `tools/ccfit.py DSCF2761 DSCF2759`: the CC slot is explained by the **v2** 2x2 (median Δab 0.56; v3 2.13); best
  fit [[0.948, 0.035], [0.028, 1.064]] ≈ v2 [[0.959, 0.034], [0.016, 1.066]]. ⇒ the tuning hook did not run. This also
  **confirms the 2x2 axis order [Cr, Cb]**: only that order recovers the known flashed values (the [Cb, Cr] fit gives
  [[0.82, −0.03], [0.13, 1.22]]). The simulator predicts a same-RAW conversion to median Δab ≈ 0.55.
* v2 CC slot vs PROVIA on this RAW (chroma ratio, by PROVIA hue): red cap ×0.89, leaves ×0.90, yellow ×0.77,
  foliage ×0.76, blue ×0.71; cap red C* p90 54.0 → 47.1 (Velvia 69.6).
* **Cause:** the tuning area is filled at start-up by blob1 **0x858394** (called once from the start-up task,
  0x8550d4), reading flash through 0x862b24 / 0x862754 (same partition table entry +0x120/+0x124 as 0x863940).
  It checks DB[0x200..0x201] == 0xaa55 and otherwise falls back to 0x863498 + defaults 0x8581c4. 0x857e44 is only a
  reload path. Fix in `cchook.py`: stage B also redirects the `bl` at 0x8550d4 (hooks HOOK_DB0 0xa400 start-up,
  HOOK_DB1 0xa480 reload, HOOK_LANG 0xa500). `emu_cchook.py` now runs the real call at 0x8550d4: ALL OK.
* Card rewritten: `build/sdchain_cc_green/` ffboot **8436762b…** (ffsys 7661dadc… unchanged); `build/sdchain_cc/`
  165b07d0…. The flash candidates `cc3_*` are unaffected (both paths read the flash area they patch).
* Language hook: not yet confirmed after an SD boot (the earlier "menu says CLASSIC CHROME" was the live RAM rename).
* ✅ **Fixed card works (2026-11-12):** DSCF2763 (DSCF2730.RAF, CC slot, Colour 0, Ver3.89, card 8436762b…):
  `ccfit.py DSCF2761 DSCF2763` → best fit [[0.658, −0.041], [0.043, 1.006]], **closest to v3** (v3 median Δab 0.54,
  v2 2.27). The start-up tuning hook runs in an SD boot. Per hue vs PROVIA (v2 → v3, simulator prediction for v3):
  red cap ×0.874 → ×0.634 (pred. 0.644), leaves 0.899 → 0.723, yellow 0.771 → 0.725, foliage 0.756 → 0.688,
  blue 0.707 → 0.644; cap red C* p90 54.0 / v2 47.1 / v3 34.5; ΔL* v3 vs v2 0.23 (tone unchanged).
* **Caution on reds:** relative to PROVIA's 2x2, v3 scales Cr by 0.67 / 1.206 = ×0.56, Fuji's X-E2 Classic Chrome
  by 1.008 / 1.268 = ×0.79 (= v2). The X-T20 scene that v3 was fitted to had no saturated reds, so v3's red
  strength is not backed by a genuine reference yet. Needed: an X-T20 Classic Chrome shot of a red subject.


## Session 2026-11-12: Highlight / Shadow tone mapped (feasibility of extended H/S)
* **Stage:** `FUN_00f32c08` (callers `FUN_00f28a60`, `00f28b24`, `00f28b54`) writes 19 u16 to regs +0x2a..+0x4e.
  The alternative `FUN_00f32a30` writes a flat value into the same 19 regs in 1/3 EV steps (800, 632, 503, 400 … 100,
  ×512/100) ⇒ the 19 values are a **luminance-dependent digital gain, 512 = ×1.0**, knot 0 = shadows, knot 18 = white
  (always 512). Not the 29-entry film-sim tone curves (0x80b700); those are a separate stage.
* **Inputs:** recctl +0xbc = Highlight, +0xc0 = Shadow, stored as menu position 0..4 = +2 HARD … −2 SOFT; tables
  0xf34478 / 0xf34480 = [4,3,0,1,2] → column 0 std, 1 −1, 2 −2, 3 +1, 4 +2. Column c (0..3) from recctl +0x118 via
  0xf34484, +0x154 == 2 → 0, plane 1/2 → 1 (shadow gain ×0.86 / ×1.75 / ×3.5 / ×7 in set 0: looks like DR).
  ID = u16 0xf33df0[set*100 + (H*5 + S)*4 + c]; DB byte at that ID (0xe06f–0xe136) = curve number.
  Set = 1 if the H/S family byte (IDs 0xf34180[plane*7+fam], 0xe137–0xe14b) == 2, else 0. Plane 0: PROVIA and
  CC (0xe13b patched 2 → 1 in v1) use set 0; everything else, and planes 1–2, use set 1. DB[0xb5] == 1 → fixed curve DB[0xe06e].
* **Curve table:** blob1 0x8098e0, 175 entries × 0x2c {u32 id; u16 gain[19]; u16 0}, count u32 @0x80b6fc;
  loader blob1 0x8057e8 (linear search by id, not found → entry 0; base hard-coded by movw/movt). Only `FUN_00f32c08`
  uses it. Set 0 = curves 0–99, set 1 = 100–174 (columns 0 and 1 share 100–124). Every entry is referenced.
* **Model, exact to 1 % on all 200 selections:** curve(H, S, c) = std(c) × S-ratio(S, c) × H-ratio(H, c), i.e. H and S
  add in EV. Steps are linear in EV (±2 offset ≈ 2 × ±1 at every knot). Size of ±2: shadow ≈ ±0.8 EV at knot 0,
  ±0.4 EV at knots 4–6, 0 at knot 10; highlight only ±0.35 EV peak (knots 13–16), 0 at knots ≤ 11 and at white.
* **Camera check (existing samples):** DSCF2759 (H 0) vs DSCF2760 (H +1, Colour −1), same RAW, SD-booted: mean ΔL* 0.0
  for L* < 60, +0.8 / +2.7 / +3.0 / +1.5 for L* 60–70 / 70–80 / 80–90 / 90–100. ⇒ +0xbc really is Highlight, and
  hard = brighter highlights, as the table predicts.
* **Extended levels are data:** ±3 / ±4 = 1.5× / 2× the ±2 EV offset, per knot and column. Knot range then 70–8724
  (stock 175–5604): the register width above 5604 is unknown (the +0x108 path already caps at 0x1000).
* **UI:** English strings `HARD` "(+2)HARD", "(+1)MEDIUM HARD", "(±0)STANDARD",
  "(−1)MEDIUM SOFT", "(−2)SOFT" (glyphs e128 "(", e129 ")", e12b "+", e12d "−", e120 "±", e130–e132 "0–2");
  each ×3 (probably Sharpness, Highlight, Shadow). Relabelling = uiname-style descriptor repoint, H/S descriptors only.
* **Routes:** (1) remap in place: rewrite the 175 entries so the 5 menu slots mean e.g. −4/−2/0/+2/+4. No DB or code
  change; live via POKE to blob1 RAM, SD card via a stage-B memcpy, flash via blob1 re-encode. Affects every film
  simulation (the stage is shared), EXIF still says ±1/±2. (2) + relabel menu text. (3) true 9-level menu: menu item
  count, setting bounds, EXIF 0x1040/0x1041, and either 9×9×4 curves (table relocation) or a hook that computes the
  curve from std × ratio^k. The menu/setting code is not mapped yet.

## Session 2026-11-12: ROM dump card (`romdump/`) — built, emulator-checked, not yet booted
* blob2 is **not** in RAM at stage B: the loader (0x468c) loads only sections 0, 1 and blob1 (0x4b94). blob1 loads
  blob2 later (0x863c1c: section 5 via 0x7ebdac(5), called from 0x970c7c) and starts it through 0x972518 →
  `bl 0x854e48` at **0x972520** (0x854e48: section 5 entry via [entry+4]+0xc). The two callers 0x973d44 / 0x973dc0
  first require five ready checks to return 1.
* `romdump/build_dumpcard.py`: tested power-on card (crumbs.patch, = ffboot e7af6d5a…) + `extra` installer: stage B
  redirects 0x972520 → DUMP_HOOK (loader 0xb020), which sets blob2 handler slot 0xf4c0dc (opcode 0x9010, stock
  0xf4bff0) to a PEEK handler at 0xb080 (build_ptpdebug.handlers(base=…, ops=('peek',))) and writes status 1 / 2
  to 0xb01c; ID 'XPRO1 ROMDUMP' + version at 0xb000. No POKE / CALL; blob2 code untouched. ffboot 79118fee…,
  ffsys 7661dadc…. `crumbs.patch(extra=None)` and `handlers()` defaults reproduce earlier outputs byte for byte
  (e7af6d5a…, 8436762b…).
* Checks: `emu_crumbs.py` ALL OK on the card; `re/tools/emu_dumpcard.py` ALL OK (stage B, real 0x972518 with
  registers identical to a stock run, one blob2 word changed, real PTP dispatcher: PEEK / clamp / no session /
  0x9011-0x9012 generic, slot-in-use and other-firmware cases). `romdump/romdump.py` tested against a fake camera.
* Camera test: battery out/in, Fn + dial press, USB → `romdump.py info` → "ROM dump card v1 is running"; `rom` →
  sha256 7dc7e332….

## Session 2026-11-12 (night): Classic Chrome as its own film simulation (Strategy B), first mapping
Goal: keep PRO Neg. Hi stock and add Classic Chrome as an 11th menu item. Static work plus USB reads (camera on
`ptpdebug_385`, flash v2).
* **Free slot: MODE_FSIM 6 "CHROME"** (hidden on the X-Pro1, no menu item). fsim → colour mode table blob2 0xf396b0
  (`FUN_00f38780`, fsim 1..12) = [5,0,4,2,3,**1**,2,2,2,2,6,7]: fsim 6 → **colour mode 1** (the unused "CHROME" mode).
  Using 6 instead of a new 13 avoids every `≤ 12` bound: backup property → fsim `blob1 0x9bad40` (identity table
  0x9bd8d0, `cmp #0xc`), develop converter `FUN_010d1b54` (0..12, else error 0x84), `FUN_00f38780` (`< 0xc` after −1).
* **Colour mode 1 has no data of its own:** every lookup maps it to PROVIA's index 0: 3×3 `FUN_00f32fcc` (two cm→i
  if-chains), 2×2 `FUN_00f2d404` (sRGB switch + alt switch), chroma gain `FUN_00f2c8fc`, detail `FUN_00f2c044`
  (byte tables only for cm 2..7), tone (`0xf34362[cm]`, cm 2..7 only). So the pipeline needs code changes: cm 1 → a
  new index with CC's presets. In the ID tables that have the special-mode switch (recctl +0xa8, indices 7..0x28),
  **index 0x10 is never produced** (candidate slot); the alt tables still need checking.
* **Settings data path (shooting):** fsim = settings struct +0x1570 (array of 0x60 × 0x4dfc at `[0x125d7b4]`,
  `FUN_01067d70`), loaded by `FUN_010181c0` from 0x1276df4 +0x1008, which `FUN_01098ed0` fills from the backup property
  (+0x9c via blob1 0x992d80). Property store blob1 RAM **0xa81240** + bank·0x2130 + idx·0xa8 + 0x164 (setter
  0x992d98, its only caller 0x9897ec). Shooting recctl fill `0xf39014` (fsim from param +0x1c → 0xf38a00); RAW
  conversion path `FUN_010c027c` (develop struct 0x13a0974, fsim at +0x4c).
* **USB mode unloads the shooting state:** `[0x125d7b4]` = 0, 0x1276df4 and the property store 0xa81240 read all
  zero over USB (PEEK verified on live PTP globals 0x11f3bb0). ⇒ fsim 6 can't be tried by a USB POKE; the settings are
  rebuilt from the backup when the cable comes out. Testing needs code (SD card hook) or a working menu item.
* **Menu text:** each language block also holds UI lists as 8-byte pairs {text descriptor, u16 width, u16 lines}
  (English block: 0x2560–0x5a40+). Film-sim list (English 0x39a0–0x3a3c): per item an icon-only entry and an
  icon+name entry, icons are **font glyphs**: U+F06A PROVIA, F06B Velvia, F06C ASTIA, F201 Neg Hi, F202 Neg Std,
  F06D MONO, F1B4 Ye, F1B3 R, F1B5 G, F06E SEPIA. Offsets differ per language and nothing in blob1/blob2 points at
  them, so lists are found through a per-block index that is not decoded yet.
* **X-E2 reference (debug name pool in its blob1):** a 14th film sim touches ~9 menu tables
  (`UI_MENU_TBLID_UIMENUCOM_RECMENU_FSIM_TBL`, `QUICKMENU_FSIM_TBL`, `RECMENU_FSIM{1,2,3}_BKT_VAL_TBL`,
  `C_SAVE_PARAM_FSIM_TBL`, `PLAY_RAWDEV_FSIM_TBL`, `FUNCTION_FSIM_TBL`, `DSP_CUSTOM_EVFLCD_FSIM_TBL`), per-list text
  (`REC_SIM_C_CROME*`, `REC_CUS_FSIM_C_CROME`, `CONT_FILMSIM_BKT_C_CROME*`, `PB_RAW_FSIM_C_CROME*`) and four icon sets
  (`ICO_FILM_*`, `ICO_INFO_FILM_*`, `ICO_QUICK_MENU_FILM_*`, `ICO_FILM_*_OL`). The X-E2 also has icons for the hidden
  CHROME sim (`ICO_FILM_CHROME`, `ICO_QUICK_MENU_FILM_CHROME`, `ICO_FILM_CHROME_OL`). Name tables: X-E2 blob1
  0x8d667c (menu table IDs, 366), 0x8dd550… (text IDs), 0x8edd98… (icons). X-E2 blob2 0x13a4090 (381 words) holds
  per-table function pointers (layout not decoded).
* EXIF FilmMode for fsim 6 is 0x000 (PROVIA) today; needs 0x600.

## Session 2026-11-12 (late night): film-sim menu data mapped (Strategy B, part 2)
X-Pro1 blob1 now decompiled too: `decompiled/xpro1_blob1_0x774000.c.gz` (Ghidra 12.1.4 + JDK 21 in ~/opt, 2.5 min).
* **UI text IDs** (`tools/uitext.py`): each language block holds one ID-indexed table of 1693 × {u32 layout, u32
  descriptor}; IDs are language-independent (English table at block offset 0x255c, Japanese 0x923c). Film-sim lists,
  all in menu order: 640–667 (FILM SIMULATION BKT / shooting-menu list: icon, icon+name per sim), 800–832 (icon
  small/big/name; mono has an extra "B&W" 819), 1057–1067 (icon only), 1196–1216 (icon, name). Nothing in code,
  UI DB or data tables maps a film-sim value to these IDs (searched every order, stride and offset): each screen's
  strings are consecutive in menu order, so the screens draw "item k" from their own group. **Adding an 11th item
  needs the screen resources, not only a table** — the open problem.
* **X-E2 comparison:** its debug name chain (blob1 0x8dc3d8, cmp/ldreq) gives 3448 text names, e.g. REC_SIM_STD..SEP
  1000–1009, REC_SIM_C_CROME 157 (CC strings inserted at 157–164). Its shooting-menu item table blob1 0xaa4204
  (11 × 0x20: 4 text IDs, 0, 0xff0004xx, X_REC_D_MENU text, text) is referenced from menu nodes
  {group, 0x198, 4, 0, link, values 0xaa9dc4, items 0xaa4204}. The X-Pro1 has no such item table.
* **X-Pro1 settings/menu model (blob1 data 0x774000–0x77c000):** nodes of 6 words {group, property, 7, 0, link,
  values}; value lists are (u32 value, 0) pairs ending 0x7ffffffe. Film-sim nodes (values = menu rows
  [0,1,2,8,7,6,4,3,5,9], 6 lists like the X-E2's six): 0x779ffc {0x3c, **0x3d**} and 0x77a544 {0x1, 0x3d} (main film
  sim), 0x775e94 / 0x779fe4 / 0x778244 {0x3e, 0x3f/0x40/0x41} (FS bracketing 1–3, list 0x776540), 0x779d4c {0x2b, 0x9a},
  0x778d9c {0x2e, 0x152} (order [0,1,2,8,7,3,5,4,6,9]).
* **Conversion engine** blob1 `0x78a9ec(table = property, value, from, to)` (0 = row index, 1–3 = columns c0–c2),
  tables via pointer array 0x78ba10[property], rows of 3 u32 ending {ffff, ffff, ffff}, 0x7ffffffe = none.
  Film sim (0x3d → 0x78f168; 0x3f/0x40/0x41 → 0x78f804/0x78d680/0x78c7b0, identical): row = menu row (0 PROVIA,
  1 Velvia, 2 ASTIA, 3 R, 4 Ye, 5 G, 6 MONO, 7 NegStd, 8 NegHi, 9 SEPIA), c0 = stored property value (0 P, 1 A, 2 V,
  3 R, 4 Ye, 5 G, 6 MONO, 7 SEPIA, 11 NS, 12 NH), c2 = MODE_FSIM. **Row 10 exists and is empty (all 0x7ffffffe):**
  natural slot for {c0 13, -, fsim 6}. Users: 0x786524 (property → fsim, c0→c2), 0x79c348 (menu row → c0 → set),
  custom-setting load blob2 0xf13e68.
* **Property storage:** `0x78fb50` get / `0x793814` set; 0x3d = high nibble of 0x9cafef + bank·0x12a + mode·7
  (mode 7 stored elsewhere), so values 0–15; c0 13 fits.
* Camera dropped off USB during the session (auto power-off); DRAM search for the run-time text-table pointer pending.

## Session 2026-11-12/13: live 11th-row experiment (`tools/fsimslot.py`) — applied in RAM, result pending
* Full DRAM dump: 0x40000000 + a mirrors low address a; no pointer to the text table exists while the camera is in USB
  mode (the two 0x4f255c words at 0x12af5b4 / module 0x41 0x1487a58 are an unrelated constant; other languages' bases
  appear nowhere). No code builds 0x4f0000 except the loader, so how the UI reaches the table stays unknown.
* The settings data (blob1 0x774000–0x77c000, 0x78a000–0x790000) is identical in RAM and file and can be poked live;
  the UI property store is readable in USB mode (film sim = 0x9cafef + 7·mode, high nibble; mode byte 0x9d1b64).
* `fsimslot.py apply` (done, flash v2 + debug firmware running): table 0x78f168 row 10 := {13, -, 6}; nodes 0x779ffc
  and 0x77a544 → new list [0,1,2,8,7,6,4,3,5,9,10] at 0xb800 (loader filler). Bracketing nodes and tables 0x3f–0x41
  untouched. **Question:** does the FILM SIMULATION menu show an 11th row, what does it draw, and does selecting it
  store 13 (read back with `fsimslot.py status`)? fsim 6 → colour mode 1 = PROVIA rendering for now.
* ✅ **Camera (user, 2026-11-13): FILM SIMULATION shows an 11th, blank row** after `fsimslot.py apply` ⇒ the menu
  builds its rows from the node's value list; the cursor row comes from the same table (blob2 `FUN_00f1e248` case
  0x3d: fsim → row). Not yet selected (stored value still 5).
* Menu engine (blob2): current node `[0x9d1254]`, per-row state array 0x9d1404 (1/2 = disabled/hidden),
  `FUN_00f0eb98` counts rows (≤ 0xaa) up to the 0x7ffffffe pair.
* Text ID 0 is an empty string (descriptor with a null string pointer). Test running: `tools/uitextmark.py apply
  0 668 669 833 834 1068 1217 1218` gives those IDs visible labels "#ID" in RAM, to see which ID the blank row draws.
* (2026-11-13) User: with the markers on, DYNAMIC RANGE in the shooting menu read "#833" ⇒ **the shooting menu draws
  the 800 text group**. The 11th row was gone by then: a power cycle reloads blob1 (fsimslot changes lost) but not
  the language block. Markers removed (`uitextmark.py restore`). Free preset slots counted: 3×3 17–30, 2×2 12–30.
  **Summary of the whole "new film sim" work: `FINDINGS.md`.**
* (2026-11-13) Second camera round: 11th row present and blank even with a label on text ID 0 ⇒ nothing is drawn.
  **Cause found: menu screens are code in module 0x41** (screen table 0x1430190, text draw 0x1433480, id < 0x69f);
  row → text tables there (0x1483c20, 0x142ac5c, 0x14838f4 + eight icon tables) have 10 entries and the draw code
  skips rows > 9. Details and table list: `FINDINGS.md` §6. Camera restored to stock (`fsimslot.py restore`).
* (2026-11-13) Live code test applied (`fsimslot.py apply`, extended): module 0x41 name table 0x1483c20[10] := 819
  ("B&W", test label) and row limit 0x147c748 `cmp r4,#9` → `#10`; I-cache invalidated by CALL blob1 0x8a5d70
  (`mov r0,#0; mcr p15,0,r0,c7,c5,0; bx lr`) after pushing the D-cache line out with a 2 MB read. The CALL returned
  and the camera still answers. Result pending: does row 11 read "B&W", can it be selected, stored value 13, photo.
* ✅ (2026-11-13, user + USB read) Row 11 reads "B&W", is selectable, pictures look standard; active MODE_FSIM
  global 0x9cb890 = 6. The 0x9cafef nibble still read 5 (not the active copy). `FINDINGS.md` §4.
* (2026-11-13) Shortcut for a live look test: fsim → colour-mode table blob2 0xf396b0[5] (fsim 6) poked 1 → 7, so
  the new row uses PRO Neg. Hi's colour mode, which holds the X-E2 Classic Chrome data in the flashed v2 (2x2 live =
  v2 values). In `fsimslot.py apply`. Final design still needs CC in its own presets (17/18, 12, curve slot) and
  PRO Neg. Hi restored to stock.
* (2026-11-13) Menu look from the X-E2: its Classic Chrome entry is the string U+F2B9 + "CLASSIC CHROME" (icon glyph
  **U+F2B9**). Fonts: both cameras use an "FDL Font" file with identical headers; X-Pro1 0x81134 bytes (file
  0x154025c, RAM 0x510000 = file, verified live), X-E2 0x84294 bytes (file 0x166025c), different from byte 0x3a on.
  X-Pro1 font partition = 0xa0000 (load table: flash 0x1540000) and RAM after the font is zero, so the X-E2 font fits
  as a whole. Unknown: whether it is a superset (same code points for every glyph the X-Pro1 UI uses).
  Live: text 819 (unused "B&W", the test row's name) → "CLASSIC CHROME" via `uitextmark.py apply 819=...`.
* (2026-11-13) `tools/fontswap.py xe2`: X-E2 font written over the X-Pro1 font in RAM (only 10838 words differ;
  6 s, verified; the camera kept answering). Text 819 := U+F2B9 + "CLASSIC CHROME". Result pending: does the row show
  the Classic Chrome icon, and do all other menu icons/text still look right with the X-E2 font?
* (2026-11-13) Camera: with the X-E2 font, the row reads "<CC icon> CLASSIC CHROME" (U+F2B9 renders), but the
  right-hand value icon of the menu is missing. Menu items are module-0x41 records {item, text, gfx, flag, A, B}
  (e.g. 0x14299ec item 11 and 0x142bd88 item 8 = FILM SIMULATION, both A = 0x142aa4c (803 icons),
  B = 0x1427320 (802 small icons), 10 entries each, menu order, packed: entry 10 = next table).
  Test applied after a power cycle: `fsimslot.py apply` now also copies A/B with an 11th entry = text 1215 to
  0xb900 / 0xb940 and repoints the 4 record fields (0x14299fc, 0x142bd98, 0x1429a00, 0x142bd9c);
  `fontswap.py xe2`; `uitextmark.py apply 819='CLASSIC CHROME' 1215=U+F2B9` (1215 = unused SEPIA-icon copy in the
  1197 group: table 0x142e558 uses 830 instead; no code immediate or module word references it).
* ✅ (2026-11-13, user) **The 11th row shows the X-E2 Classic Chrome icon and the name CLASSIC CHROME.** Menu entry
  complete in RAM (name, icon, selectable, selects fsim 6 → colour mode 7 = CC data of v2). `FINDINGS.md` §4, §6.

## Session 2026-11-13: SD card with Classic Chrome as its own menu entry (`build/sdchain_cc11_green/`)
* **Font: no change needed.** The X-E2 Classic Chrome icon U+F2B9 is already in the X-Pro1 font, byte-identical
  (unused there). Font index: per code point an entry at 0x38050 + 4·(c − 0xE000) (u32, offset = value >> 8, glyph
  = gap to the next entry); fits all 304 PUA characters the X-Pro1 UI uses. The X-E2 font adds 46 glyphs
  U+F2D1–U+F2FE (0x3161 bytes at 0x7aa92) and is otherwise identical.
* Load points: blob1 data at stage B; module 0x41 is streamed in later by blob1 0x9715e4, whose init loop calls
  each module's init list with `blx r3` at **0x9717b8** (module 0x41 list = [0x1430170, 0] at the module base; the
  module table entry's base field doubles as the load address, so it can't be repointed). blob2 at its start call
  0x972520. Fonts: blob1 0x863718 (section 3). Language block: cchook's hook (0x863388).
* `tools/fsim11.py` (extra installer, table-driven stage B because the inline marker block is full),
  `cchook.install(lang=...)` / `crumbs.patch(cc_lang=...)`, `build_sdchain.py --fsim11`. Defaults unchanged:
  `--crumbs --uiswap --cc` still gives 8436762b….
* Card `build/sdchain_cc11_green/` ffboot **140622c0…**, ffsys 7661dadc…: `emu_fsim11.py` ALL OK, `emu_crumbs.py` ALL OK.
  Camera test pending.
* (2026-11-13) Camera (card 140622c0…, photos samples/menu.jpg + menu1.jpg): FILM SIMULATION pop-up shows the 11th
  entry with icon + CLASSIC CHROME, but the shooting-menu line still showed the STD badge. Cause: the menu line's
  value index comes from module 0x41 `FUN_0146ef68` case 8 = byte table **0x1474e7c[MODE_FSIM]** (menu row per film
  sim; identical copy 0x1474e3c used by `FUN_0146fcec` case 0) where fsim 6 → 0 (PROVIA's row). Fix: entry 6 := 10
  (word 0x1474e80 / 0x1474e40: 0x05000905 → 0x050a0905). Applied live (`fsimslot.py apply`, flash-booted camera) and
  on the card: `build/sdchain_cc11_green/` ffboot **1923db4f…**, emu_fsim11 ALL OK (20), emu_crumbs ALL OK.
* ✅ (2026-11-13, user) Row-map fix confirmed live: the shooting-menu FILM SIMULATION line shows the Classic Chrome
  icon. Card updated to ffboot 1923db4f… (verified after remount). README / FINDINGS / TODO updated.

## Session 2026-11-13: Classic Chrome's own look data, PRO Neg. Hi restored (`tools/cclook.py`)
* Colour mode 1 (MODE_FSIM 6) already inherits PROVIA's detail (`FUN_00f2c044`: byte table only for cm 2–7),
  chroma-gain preset (`FUN_00f2c8fc` chain → index 0 → 0xe4e8 = 1) and H/S family (`FUN_00f32c08` default) — all
  equal to what the X-E2 gives Classic Chrome. Only the 3x3, the 2x2 and the tone family fall back to PROVIA.
* **Selector tables indexed by film-sim index i**: the sRGB tables have an unused index 7 holding PROVIA's values
  (3x3: 0xdd26 / 0xdd8e / 0xdd5e for +0x104 = 0 / 4,8 / other; 2x2: 0xe4a0; `FUN_00f30b10`'s 2x2-by-mode rows
  0x100fa + 0x30·row, index 7 = 0x10101…). The alt tables (+0xc8 ≠ 0) have 7 entries: 0xf34300 / 0xf34248 / 0xf2dea8
  are followed by a 2-byte padding word (now the 8th ID), 0xf34064's 8th slot is the tone byte table (relocated via
  its movweq/movteq at 0xf33474), 0xf31718 (4 rows × 7 u32) is relocated with row stride 8 (`rsb r5,r5,r5,lsl#3` at
  0xf30e18 → `lsl r5,r5,#3`; r5 is dead afterwards).
* **cm → index chains** end in a fallback instruction for cm 0/1/8/9: `movne r2,#0` 0xf333c4 (3x3 sRGB), `movne r1,#0`
  0xf3344c (3x3 alt), `mov r3,#0` 0xf2d724 / 0xf2d7a8 (2x2), `movne r2,#0` 0xf30d7c / 0xf30e0c. Each becomes
  `bl(ne)` to a 4-instruction stub returning 7 for cm 1, else 0 (flags of the chain kept by using `blne`).
* **Tone families**: 7 families (0 PROVIA; byte tables 0xf34364 + (cm−2), 0xf3443c…, 0xf34074… give 1–6 for cm 2–7).
  No spare family: the byte 0xf34363 before the table is the last ID of Neg Std's curve table, so "index cm−1" would
  corrupt it. Instead the range-check fallback `movhi r2,#0` (0xf32218) / `movhi r3,#0xf9` (0xf32360, 0xf32570)
  becomes a `bl` to a stub giving family 5 / code 0xff for cm 1 (r3 = cm−2 = −1), flags restored with `cmp r3,#5`.
  SEPIA (cm 3) donates family 5 / 0xff: its curve IDs are all PROVIA's (0), so its byte-table entries become 0 / 0xf9
  with no visible change; family 5's 40 IDs := 38 (0xdf92, 0xdf99, 0xdfa0, 0xdfae, 0xde37–0xde48, 0xdeb5–0xdec6).
  The two '+7' entries (0xdfa7, 0xdfb5) stay 16: in that mode every film simulation uses curve 16 (v2 kept them too).
* Curve lookup blob1 0x8056a8: a curve number not in the table falls back to entry 0 (curve 0), so on a stock-flash
  camera (no curve 38) the tone patches are skipped by HOOK_B2's guard and sepia would still render with curve 0.
* Data (tuning area, via the existing tuning hooks, now 99 u16 entries): the 76 v2 bytes back to stock, v2's 3x3
  matrices → presets 17 (sRGB) / 18 (alt), v3 2x2 → preset 12, selectors (0xdd26/0xdd8e/0xdd5e := 17, 0xe4a0 and
  0x10101+0x30·r := 12, free bytes 0xe409 := 18 / 0xe40b := 12 for the alt tables), curve IDs. 161 bytes in all.
* **Live (camera, flash-booted v2 + debug): `cclook.py apply`** poked everything (20 blob2 words + stubs/tables in the
  loader filler 0xbc00–0xbd00, I-cache invalidated); `restore` brought the area back to v2 exactly; re-applied with
  the final plan. `fsimslot.py apply --own` keeps fsim 6 on colour mode 1. Photos not yet taken.
* Card: `build/sdchain_cc11own_green/` (`--crumbs --uiswap --cc --fsim11 --cclook`), ffboot **2edd070e…**: HOOK_B2 is
  now table-driven ({addr, old, new, flag}; flag 1 = needs curve 38 in blob1's table), `cchook.install(db_params=)`,
  `crumbs.patch(cc_db=)`, `build_sdchain.py --cclook [--flash FILE]`. `tools/emu_cclook.py` ALL OK: tuning hook →
  planned image exactly (and only stock-matching entries on a 3.82 area), HOOK_B2 with/without curve 38, real
  `FUN_00f32fcc` / `FUN_00f2d404` / `FUN_00f30b10` / `FUN_00f2c8fc` / `FUN_00f321f0` / `FUN_00f3232c`: colour mode 1 =
  what v2's PRO Neg. Hi produced (all sRGB/alt/mode variants, curve 38), PRO Neg. Hi = stock, PROVIA/SEPIA/MONO
  unchanged. `--cc` alone still reproduces 8436762b…; the borrow card (`--fsim11`) is now 7d62033a… (table hook).
