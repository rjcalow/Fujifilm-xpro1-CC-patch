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
| PRO Neg Hi → Classic Chrome candidate | ✅ built + statically verified, untested on hardware: re/build/ccswap_candidate/ |
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
