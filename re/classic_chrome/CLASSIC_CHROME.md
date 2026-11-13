# Classic Chrome: extracted from X-E2 (FWUP0004.DAT), mapped onto X-Pro1 (FPUPDATE.DAT)

Files in this folder:
| file | contents |
|---|---|
| `CLASSIC_CHROME.md` | this document |
| `cc_port_data.json` | every extracted value: X-E2 CC + PROVIA (curves, matrices, IDs, raw), X-Pro1 PROVIA, ported values |
| `xe2_colour_mode_tables.txt` | every X-E2 parameter-ID table indexed by colour mode, with the CC column called out |
| `xpro1_proneghi_to_classic_chrome_patch.json` | the 25 concrete byte patches for the data-only port (old/new, both NOT-space and raw-file bytes) |

Addresses: `blob1`/`blob2` addresses are RAM addresses of the decompressed images
(X-E2: blob1 @0x8a0400, blob2 @0xf6a9c0; X-Pro1: blob1 @0x774000, blob2 @0xe0ec80).
"File offset" means an offset in the NOT-ed image (`not.bin`). The raw update file holds the bitwise NOT of those bytes.

---

## 1. How film simulations work on these cameras (EXR-processor generation)

```
MODE_FSIM (UI enum, 0..13)            settings struct field (X-E2 +0x51c)
      │  FUN_010bbc80 (X-E2) / FUN_00f38780 (X-Pro1)
      ▼
colour mode (0..9)                     recctl+0x108 (X-E2) / recctl+0xc4 (X-Pro1)
      │  u16 parameter-ID tables, indexed by colour mode (sometimes [row][10] or [cm][5])
      ▼
parameter ID ──► adjustment DB byte:   value = DB[ID]   (u16 values = DB[ID] | DB[ID+1]<<8)
      │  values are either final gains (0x40 = 1.0) or PRESET numbers
      ▼
preset ──► preset tables of more IDs ──► matrices / curve numbers ──► image-processor registers
```

**Colour-mode enum** (same on both cameras; CC added as 8):
| colour mode | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | **8** | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| film sim | PROVIA / STD (and F1c) | CHROME (unused) | MONO + B&W filters | SEPIA | Velvia | ASTIA | PRO Neg Std | PRO Neg Hi | **CLASSIC CHROME** | spare |

`MODE_FSIM → colour mode`: 0→0, 1(F1b ASTIA)→5, 2→0, 3(F2 Velvia)→4, 4/7/8/9/10(mono)→2, 5(SEPIA)→3, 6→1, 11→6, 12→7, **13→8**.
The mono filter is a separate field (X-E2 +0x114, X-Pro1 +0xd0): Ye=1, R=2, G=3.

**Adjustment DB** (all tuning parameters):
| | X-E2 | X-Pro1 |
|---|---|---|
| getter | `func 0x009446ac(ID)`: `ldrb [*(0xbfd92c) + map(ID)]` | `func 0x00857be0(ID)`: `ldrb [0x40d3b580 + ID]` |
| u16 getter | `0x009eb0c4` | `0x009742b4` |
| RAM copy | 0x42068000 (pointer @0xbfd92c) | 0x40d3b580 |
| source in update file | flash 0xe0000 → **file 0xe025c + ID** | flash 0xae0000 → **file 0xae025c + ID** |
| compiled mirror | — (only a sparse default list @blob1 0xb0aa28, IDs 0x100–0x3f2) | **blob1 0x812470 + ID** (identical at all patch IDs) |
| ID→offset | identity for ID < 0x3e0000 (banked above) | identity |

The X-E2 loader treats DB offsets 0x0000–0x2fff as per-camera calibration and 0x3000–0x41fff as tuning
(blob1 0x944cf4: copy of `0x3f000` bytes from offset `0x3000`). Every film-sim parameter is in the tuning range.

---

## 2. What makes Classic Chrome (X-E2 source data)

Classic Chrome differs from PROVIA in exactly **three data items**. Everything else reuses PROVIA's values or neutral (`0x40`) gains.

### 2.1 Tone curve: curve #38
* Selected by `FUN_010b28a0`: tone-preset tables `0x14695e8` / `0x14693f4` (layout `[plane 0..3][cm][level 0..4]`).
  For cm 8, **every** plane and level = **preset 59**. PROVIA uses 1/11/21, Velvia 2/12/22, and so on.
* `preset → curve#`: `curve = DB[0x1469840[(preset-1)*6 + k]]` (`FUN_010b2044`). Preset 59 → **curve 38** for every k.
  IDs 0xd655–0xd65a. No other preset uses curve 38. Curves 37 and 39–41 exist but are unused.
* Curve data is **compiled into blob1**: table @`0xb839d8` (count @`0xb839d0` = 42), entries of 0x48 bytes
  `{u32 curve#; u8 seg[9]; u8 pad[3]; u16 knot[28]}`. Read via `0x0093793c`. Knots are 14-bit (0..16383);
  `seg` = per-segment spacing exponents.
* Curve #38 (Classic Chrome), header `2 2 3 4 5 5 5 6 6`:
  ```
  134 339 595 849 1125 1398 1948 2511 3058 4214 5191 6021 7683 8943
  9905 10863 11515 12085 12663 13072 13462 14213 14730 15219 15643 16066 16383 0
  ```
  raw entry (0x48 bytes): `260000000202030405050506060000008600530153025103650476059c07cf09f20b761047148517031eef22b1266f2afb2c352f77311033963485378a39733b1b3dc23eff3f0000`
* Compared with PROVIA (#1: `129 330 605 875 1189 1504 2144 2802 3390 4628 5503 6232 7678 8722 9623 10509 …`),
  #38 is 7–10% darker from deep shadows through the lower mids and brighter in the upper mids. That's an S-curve with harder shadows.

### 2.2 3×3 colour matrix: preset 9 (sRGB) / preset 16 (colour-space alt)
* Selected by `FUN_010b22c0` from table `0x1469b68` (`cm + (+0x10c)*10`). CC row0 = **9**, row1 = **16** (IDs 0xce94 / 0xce96).
  `+0x10c` is a two-state setting, most likely colour space (sRGB / AdobeRGB).
* Loaded by `FUN_010b23b8`: 9 IDs at `0x1468e80 + (preset-1)*0x12`, row-major, each a **13-bit two's-complement u16**, 0x400 = 1.0.
  Used by `FUN_010b24cc`.
* **Preset 9 (sRGB)**, IDs 0xad53…0xad63 (step 2), raw `0563 1ef0 1fad 0011 0401 1fee 0057 1edb 04ce`:
  ```
  [ +1.3467  -0.2656  -0.0811 ]
  [ +0.0166  +1.0010  -0.0176 ]
  [ +0.0850  -0.2861  +1.2012 ]      (rows sum to 1.0)
  ```
* **Preset 16 (alt)**, IDs 0xadd1…0xade1, raw `0401 004c 1fb3 001c 0414 1fd0 0058 1ef7 04b1`:
  `[[1.0010, 0.0742, -0.0752], [0.0273, 1.0195, -0.0469], [0.0859, -0.2588, 1.1729]]`
* PROVIA for comparison (preset 1): `[[1.295,-0.353,0.058],[-0.031,1.104,-0.072],[0.061,-0.272,1.212]]`.

### 2.3 2×2 chroma matrix: preset 11 (sRGB) / preset 13 (alt)
* Selected by `FUN_010ada9c` from table `0x1467364` (`cm + (+0x10c)*10`). CC row0 = **11**, row1 = **13** (IDs 0xcec2 / 0xcec4).
* Loaded by `FUN_010adb04`: 4 IDs at `0x1466fa0 + (preset-1)*8`, **storage order `m00, m11, m01, m10`**, 13-bit signed, 0x400 = 1.0.
  `FUN_010adce8` then multiplies it by 5 gains (user Colour setting etc.). It is skipped for mono and sepia.
* **Preset 11 (sRGB)**, IDs 0xce9a 0xce9c 0xce9e 0xcea0, raw `0408 0437 0005 0058` → `[[1.0078, 0.0049], [0.0859, 1.0537]]`
* **Preset 13 (alt)**, IDs 0xceaa…0xceb0, raw `0407 0401 000c 006c` → `[[1.0068, 0.0117], [0.1055, 1.0010]]`
* PROVIA (preset 1): `[[1.268, 0.009], [0.205, 1.542]]`. CC has much lower chroma gain, which gives its muted colour.

### 2.4 Everything else for colour mode 8 (copy of PROVIA / neutral)
See `xe2_colour_mode_tables.txt`. CC takes:
* detail/edge preset (`0x14671fc`, `010ae77c`): **1** (= PROVIA); alt row 3
* chroma gain preset (`0x1466f8c`, `010adc00`): **1** (= PROVIA)
* H/S tone family (`0x146a384`, `010b40b0`): 1/3/4/3/3 per format (= PROVIA)
* gains `0x1467dd0`, `0x1467de4`, `0x14684d0`, `0x1469ef4`: 64 (= 1.0, same as all colour modes)
* `0x1469028` (local contrast/level, `[cm][5]`): 64 46 39 27 21 for PROVIA; **64 39 21 11 5** for CC (same as Velvia/ASTIA/Neg)

### 2.5 Other Classic Chrome code on the X-E2 (UI and metadata)
| what | where |
|---|---|
| MODE_FSIM 13 → colour mode 8 | `FUN_010bbc80` case 0xd → 8 |
| EXIF FilmMode 0x1401 = 0x600 | `FUN_011e48c8` (switch on settings+0x51c), `mov r0,#0x600` @0x11e49d0 |
| EXIF Saturation 0x1003 = 0x8000 for CC | `FUN_011e42c8`, bitmask 0x200a (F1b, F2, CC) |
| UI symbols | `ICO_FILM_C_CHROME(_OL)`, `ICO_INFO_FILM_C_CHROME`, `ICO_QUICK_MENU_C_CROME`, `CONT_FILMSIM_BKT_C_CROME`, `PB_RAW_FSIM_C_CROME`, `BKUP_FILM_SIM_CLASSIC_CHROME` |

---

## 3. X-Pro1 equivalents (target)

| item | X-E2 | X-Pro1 |
|---|---|---|
| fsim → colour mode | `FUN_010bbc80` (switch, 13 cases) | `FUN_00f38780`: `if (fsim-1 < 0xc) cm = u32 table 0xf396b0[fsim-1]` (12 entries; next table 0xf396e0 follows) |
| colour-mode field | recctl+0x108 | recctl+0xc4 (mono filter +0xd0) |
| tone curve table (blob1) | 0xb839d8, count @0xb839d0 = 42 | **0x80b700, count @0x80b6f8 = 29**; lookup `0x008056a8` |
| tone selection | `FUN_010b28a0` (preset tables) | `FUN_00f32808` → `FUN_00f321f0` / `FUN_00f3232c`: family = `byte 0xf34362[cm]` (cm 2..7 only, else 0) → curve IDs `0xf34098[fam]`, `0xf3427c[fam]` → blend `FUN_00f28ba0` |
| H/S tone stage | `FUN_010b40b0` | `FUN_00f32c08` (switch on cm, family 0..6; IDs `0xf34180 + (plane*7+fam)*2`) |
| 3×3 matrix | `0x1468e80`, preset-1, stride 0x12 | **`0xf33b94`, preset-1, stride 0x12** (`FUN_00f32ef8`); preset IDs `0xf34108[i]` (sRGB) / `0xf34300[i]` (alt); `i`: PROVIA 0, Velvia 1, ASTIA 2, NegStd 3, NegHi 4, mono 5, sepia 6 (`FUN_00f32fcc`) |
| 2×2 chroma matrix | `0x1466fa0`, preset-1, stride 8 | **`0xf2e0d0`, preset-1, stride 8** (`FUN_00f2d384`); preset IDs `0xf2dd80[i]` (`FUN_00f2d404`) |
| detail preset | `0x14671fc` (`010ae77c`) | `FUN_00f2c044` → `0xf2e39c[idx]`, idx = `0xf2e096[cm]` (`00f2ccb8`) |
| chroma gain preset | `0x1466f8c` (`010adc00`), gains `0x1467274[(p-1)*5 + col]`, col = +0x158 | **`FUN_00f2c8fc`**: preset = DB[`0xf2df08[i]`], gain = DB[`0xf2de74 + (p-1)*10 + col`], col from recctl+0x118 (0,3,6,7,8); called by `FUN_00f2db68` and `FUN_00f311cc` |

X-Pro1 per-film-sim assignments:
| | PROVIA | Velvia | ASTIA | Neg Std | **Neg Hi** |
|---|---|---|---|---|---|
| 3×3 preset sRGB / alt | 1 / 6 | 2 / 7 | 3 / 8 | 4 / 9 | **5 / 10** (IDs 0xdd23 / 0xdd4c) |
| 2×2 preset | 1 | 2 | 3 | 4 | **5** (ID 0xe49d) |
| tone family → curve# | 0 → 0 | 1 → 16 | 2 → 17 | 3 → 26 | **4 → 27** (IDs 0xdf91, 0xdf98) |
| detail preset | 1 | | | | **3** (ID 0xffc6) |
| chroma gain preset | 1 (×1.00 all columns) | 2 | 2 | 2 | **2** (ID 0xe4ec; 128/134/141/147/147 = up to ×1.15) |
| H/S family plane0 | 1 | | | | **2** (ID 0xe13b) |

Curve check: X-Pro1 curves 16/17/26/27 are byte-identical to X-E2 curves 6/11/16/21. Those are what the X-E2 uses for
Velvia/ASTIA/NegStd/NegHi in the plane where CC uses #38. So the X-Pro1 tone pipeline matches that X-E2 plane, and
**curve #38 can be copied verbatim**. X-Pro1 PROVIA reads curve# 0, which equals X-E2 #16. Curve number 38 is free on the X-Pro1.

---

## 4. Porting

> **Built:** `re/build/ccswap_candidate/FPUPDATE.DAT` (see its README; statically verified, not hardware-tested).
> The final build differs from the plan below in one point. Tone: instead of overwriting curve #27, the X-E2 curve #38
> entry replaces the *unreferenced* X-Pro1 curve slot #40, and **all 40** PRO Neg Hi tone-curve IDs (main path #27 and
> the per-level variants #22–#26 in `FUN_00f3232c`) are pointed at 38. The 2 IDs for the special mode where every film
> sim uses curve 16 are kept. The low-confidence alt matrix uses `(CC9·P1⁻¹)·XP1_altPROVIA`. Container checksums and the
> 16 KB LZ chunk rule are solved (`re/tools/fpupdate.py`, `re/tools/lzenc_chunked.py`).

### Strategy A: data only, replace PRO Neg Hi with Classic Chrome (recommended first step)
No code changes. The menu, icon and EXIF still say "PRO Neg Hi", but images get Classic Chrome processing.
The PRO Neg Hi slot was chosen because its presets and curve are not shared with any other film sim, and it runs
the full colour pipeline. SEPIA and mono skip the chroma stage.

All 25 operations, with old and new bytes, are in `xpro1_proneghi_to_classic_chrome_patch.json`:
1. **Tone:** blob1 curve entry for curve #27 @**0x80be98**: keep the first 4 bytes (`curve# = 27`) and replace bytes 4..0x47
   with X-E2 curve #38's. blob1 must be re-compressed. Tested: the re-encoded size is 0x13bbe0, under the 0x140000 limit, and it round-trips.
2. **3×3 sRGB** (preset 5): DB IDs 0xdb4b…0xdb5b := ported matrix (below).
3. **3×3 alt** (preset 10, *low confidence*): DB IDs 0xdba5…0xdbb5 := ported alt matrix.
4. **2×2 chroma** (preset 5): DB IDs 0xe3c9 (m00), 0xe3cb (m11), 0xe3cd (m01), 0xe3cf (m10) := ported matrix.
5. **Detail preset** ID 0xffc6: 3 → 1 (PROVIA's, as on the X-E2).
6. **H/S family** ID 0xe13b: 2 → 1 (PROVIA's).
7. **Chroma gain preset** ID 0xe4ec: 2 → 1 (PROVIA's, ×1.00; as the X-E2 does for CC). *Added in v2 (2026-11-06)*: v1 missed it
   because `FUN_00f2c8fc` receives the colour mode as an argument, so the direct `+0xc4` table scan didn't find it.
   v1 Classic Chrome therefore had up to 15% too much chroma (noticed on strong reds).
Each DB write goes to **both** copies: file offset `0xae025c+ID` and blob1 mirror `0x812470+ID`.

**Ported values** (relative transfer: `X-Pro1_CC = (X-E2_CC · X-E2_PROVIA⁻¹) · X-Pro1_PROVIA`, which keeps the X-Pro1's
sensor-specific base tuning and applies CC's change from PROVIA):
* 3×3 sRGB: `[[1.388,-0.304,-0.083],[-0.034,1.016,0.017],[0.105,-0.198,1.093]]`, raw `058d 1ec8 1fab 1fdd 0411 0012 006b 1f35 045f`
* 2×2: `[[0.959,0.034],[0.016,1.066]]`, raw (storage m00,m11,m01,m10) `03d6 0444 0023 0010`
* Alternative: copy the X-E2 CC matrices verbatim (the cameras' PROVIA matrices differ by only a few percent).
* **v3 candidate (2026-11-12, `re/tools/build_cc3.py`):** 2×2 `[[0.670,-0.030],[0.035,1.010]]`, raw (storage m00,m11,m01,m10)
  `02ae 040a 1fe1 0024`. This is a fit to a genuine X-T20 Classic Chrome photo, not Fuji's X-E2 data. The 2×2 acts on
  `[Cr, Cb]`. Details: `../NOTES.md`, session 2026-11-12.

### Strategy B: a real 14th film sim (Classic Chrome as a new menu item)
Data (as in A, but in new preset slots instead of overwriting Neg Hi), plus code:
1. `FUN_00f38780`: allow fsim 13 → cm 8 (bound `0xc` → `0xd`, plus an entry; the u32 table @0xf396b0 is followed by
   another table, so either special-case 13 in code or relocate the table).
2. Every `cm-2 < 6` range check in the colour pipeline must accept 8, and every byte table indexed by cm needs entry [8]:
   `0xf34362`, `0xf3443a`, `0xf34072` (tone families), `0xf2e096`, `0xf2e0b2` (detail).
   ID tables indexed by `i` need entry 7 or a new mapping: `0xf34108`, `0xf34300`, `0xf2dd80`, `0xf34098`, `0xf3427c`;
   `FUN_00f32fcc`/`FUN_00f2d404` map cm→i with if/switch chains, which need a case for 8.
3. New DB IDs for CC's presets (free tuning-range offsets), new preset slots in 0xf33b94 / 0xf2e0d0 (check for
   unused trailing entries), and new tone-curve entry #38 (count 29 → 30; the table is followed by other data, so relocate or reuse an unused entry).
4. Settings and UI: MODE_FSIM_NUM 13 → 14 bounds, the film-sim menu list, the icon (UI resource DB 0x130000; the X-E2 has
   `ICO_FILM_C_CHROME*` bitmaps to borrow), the quick menu, film-sim bracketing, the RAW-convert menu, and backup/restore of the setting.
5. EXIF: FilmMode table @blob2 **0x1097f6c** (u16[13]) needs entry 13 = 0x600 (relocate), and the Saturation-tag logic.

---

## 5. Confidence and open items
* **High:** colour-mode enum and mapping; getter/DB mechanism and base (decoded matrices have unit row sums, gains
  decode to 0x40); X-E2 CC tone curve, 3×3 and 2×2 data; X-Pro1 table addresses, preset indexing (`preset-1`, verified in asm).
* **Medium:** the meaning of `+0x10c` (colour space?) and of the X-Pro1 `+200` branch used for the "alt" 3×3. The ported
  alt 3×3 has large off-diagonals, so validate before use (op 3 is marked `low`).
* **Medium:** X-Pro1 PROVIA tone reads curve# 0. The verbatim-copy argument relies on curves 16/17/26/27 = X-E2 6/11/16/21.
* **Unknown:** whether the X-Pro1 updater rewrites the adjustment area (flash 0xae0000) or keeps the camera's copy.
  Patching both the flash image and the blob1 mirror covers both cases only if the firmware rebuilds from the mirror.
  This must be verified (look at what the X-Pro1 blob1 does with 0x812470, as for the X-E2 loader at 0x944cf4).
* **Blocking for any flash:** the outer FPUPDATE checksum (header 0x20c / 0x24c) is still unsolved.
* **fujimod (external) changes the risk picture:** EXR/EXR Pro boot ROMs support Fujifilm's service `SD_BOOT`
  (`ffsys.bin` + `ffboot.bin` + `ffuser.bin`). So a bricked X-Pro1 is likely recoverable in principle, and the swap
  could be *dual-booted* from the card (RAM image: no flash write, no recompression, no checksum) before any flash.
  This isn't usable for the X-Pro1 yet: SD-boot keys unknown, fujimod's EXR Pro builder incomplete. See NOTES.md.
* **Recovery path:** the update file name (`A:\FPUPDATE.DAT`) appears only in blob2 (0xf50f25, 0xf7ec6f), not in the
  boot or loader stubs. The SD-card updater is therefore part of the main firmware. If a patched blob1/blob2 fails to
  boot, reflashing from SD is probably impossible (no independent recovery path found).

### Full audit of colour-mode-dependent parameters (2026-11-06, before v2)
Every function in the X-Pro1 pipeline (blob2 0xf20000–0xf40000) that reads recctl+0xc4, plus every callee it passes
the colour mode to, was listed and its ID tables resolved (PROVIA vs PRO Neg Hi). Same sweep on the X-E2 (+0x108).
| X-Pro1 lookup | PROVIA vs Neg Hi | action |
|---|---|---|
| 3×3 (`00f32fcc`), 2×2 (`00f2d404`, and `00f30b10` u32 tables → same preset 5), tone (`00f321f0`/`00f3232c`) | differ | ported |
| detail (`00f2c044`) main / alt | 3→1 / 3 (= X-E2 CC alt 3) | ported / correct as is |
| H/S tone family (`00f32c08`) plane 0 / planes 1–2 | 2→1 / all 2 | ported / nothing to do |
| **chroma gain (`00f2c8fc`)** | 1 vs **2** | **ported in v2** |
| `00f29b4c` (0xf2b12c), `00f2979c` (0xf2b2c8/0xf2b31e), `00f2c384` (0xe58d../0xe5b6..), `00f2e8c8` (0xf2fc0c..), `00f31d70` (0xf34444.., the counterpart of X-E2 `0x1469028`), `00f37508` | equal | nothing to do |
| mono/sepia-only branches (`00f2a60c`, `00f2a990`, `00f31e40`, `00f2c6f4`) | n/a | nothing to do |

X-E2 side: all CC-dependent lookups are in `xe2_colour_mode_tables.txt` except `FUN_010ae1a8` (`DAT_01466dd8[cm]`: CC = PROVIA = Neg Hi = 0)
and `func_0x009ec468` (mono/sepia test only). `verify_ccswap.py` now checks all of the above.

### Installing and rolling back
The updater only accepts files newer than the built-in 3.82, so patched builds are labelled 3.83 and rollback uses
the official firmware relabelled (e.g. 3.84). Official files cannot downgrade or re-install. Details: `../NOTES.md` →
"Firmware versions, downgrades and rollback".

## 6. Tools used (in `re/tools`)
`extract.py` (unpack), `gscripts/MakeFuncs.java` + `gscripts/DumpC.java` (Ghidra headless decompile of each blob to C),
`getfunc.py` (print functions from the C dump), `cmtables.py` (colour-mode ID tables → DB values),
`cc_port.py` (extraction plus relative port, which writes `cc_port_data.json`), `cc_patchlist.py` (patch list).
