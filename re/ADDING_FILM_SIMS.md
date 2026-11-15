# How to add another film simulation to the X-Pro1 (recipe)

Written 2026-11-15 after Classic Chrome was added as an 11th FILM SIMULATION entry (SD-boot card
`build/sdchain_cc11own_green/`). Background and every address: `FINDINGS.md` (§2–§6c) and `NOTES.md`.
All addresses are RAM addresses of the official 3.82 firmware (blob1 0x774000, blob2 0xe0ec80, module 0x41 0x1420000).

Classic Chrome used: MODE_FSIM **6**, colour mode **1**, stored value **13**, menu row **10**, text IDs **819 / 1215**,
presets **3x3 17/18, 2x2 12**, tone family **5** (donated by SEPIA). A second new film sim needs a fresh value in each
column of the checklist below.

## 1. Pick the numbers

| What | Classic Chrome | Still free | Notes |
|---|---|---|---|
| MODE_FSIM (film-sim number) | 6 | **2, 4** | Accepted 0–12 everywhere; 13+ needs three range checks widened (FINDINGS §2) |
| Colour mode | 1 | **8, 9** | fsim → colour mode table blob2 0xf396b0 (u32, index fsim − 1): set the new fsim's entry |
| Stored setting value (4 bits) | 13 | **8, 9, 10, 14, 15** | c0 column of the conversion table |
| Menu row | 10 | 11, … | Row 10 used the empty placeholder; row 11+ needs the conversion tables copied with more rows |
| Text IDs (name, icon) | 819, 1215 | find more unused IDs | No new ID possible (draw code caps at 0x69f); repoint unused ones (check no code/table uses them, own descriptor in all 35 languages) |
| Icon glyph | U+F2B9 (already in the font) | any glyph present in the X-Pro1 font | Font index: u32 at 0x38050 + 4·(c − 0xE000), value >> 8 = offset; a gap of 0 = no glyph |
| 3x3 matrix presets | 17 (sRGB), 18 (alt) | **19–30** | IDs 0xdc23 + 0x12·(n − 17), 9 u16, 0x400 = 1.0 |
| 2x2 matrix preset | 12 | **13–30** | IDs 0xe401 + 8·(n − 12), storage order m00 m11 m01 m10. Note: cclook uses bytes 0xe409/0xe40b (preset 13's first two IDs) as selectors, so start at **14** |
| Tone curve | 38 (in v2's slot #40) | unreferenced slots #1–3, #24, #25, #28, #41 | blob1 table 0x80b700, 0x48 bytes per entry; a missing curve number falls back to curve 0 |
| Tone family | 5 (from SEPIA) | **6 from MONO is not free** (mono uses it); otherwise none | See §4 |
| Selector index | 7 | none in the sRGB tables (index 7 is the only unused one before the special-mode block) | Second sim: use the stub to return a different index whose table slots are unused (check 0x10, never produced by any path) |

## 2. Settings and menu (blob1 data, module 0x41) — copy `tools/fsim11.py`

1. **Conversion tables** for setting 0x3d (0x78f168) and the bracketing slots 0x3f/0x40/0x41 (0x78f804 / 0x78d680 /
   0x78c7b0): add a row {stored value, 0x7ffffffe, MODE_FSIM}. Row 10 was an empty placeholder; a 12th row needs the
   table copied to free RAM and its pointer in 0x78ba10[setting] changed.
2. **Menu lists** ((row, 0) pairs ending 0x7ffffffe): FILM SIMULATION nodes 0x779ffc and 0x77a544 (+0x14 = list
   pointer). Copy, append the row, repoint.
3. **Module 0x41** (patched from the module-init hook at blob1 0x9717b8, before init 0x1430170):
   * name table 0x1483c20 (entry = row) and its row limit `cmp r4,#9` at 0x147c748;
   * icon tables of both FILM SIMULATION records: A 0x142aa4c, B 0x1427320 (records 0x14299ec and 0x142bd88,
     fields +0x10 / +0x14) — copy with the extra entry, repoint the four fields;
   * main-menu value: MODE_FSIM → row byte tables 0x1474e7c and 0x1474e3c: entry [MODE_FSIM] := row.
4. **Language block** (cchook language hook, `fsim11.lang`): repoint the chosen text IDs' descriptors to new strings
   in the block's free tail (0x1f000) for all 35 languages.

Test live first: `tools/fsimslot.py` (+ `uitextmark.py` for text) on the flash-booted camera, then the card.

## 3. Look data (blob2, tuning area) — copy `tools/cclook.py`

* The new colour mode inherits PROVIA's detail (`FUN_00f2c044`), chroma-gain preset (`FUN_00f2c8fc`) and H/S family
  (`FUN_00f32c08`) unless those are patched too. Classic Chrome needed none of them.
* **3x3 / 2x2**: the cm → index chains end in a fallback instruction for colour modes 0/1/8/9:
  `movne r2,#0` 0xf333c4, `movne r1,#0` 0xf3344c, `mov r3,#0` 0xf2d724 / 0xf2d7a8, `movne r2,#0` 0xf30d7c / 0xf30e0c.
  They now call stubs (`cmp r2,#1; moveq r2,#7; movne r2,#0`). For a second sim extend the stubs
  (`cmp r2,#8; moveq r2,#<index>`) and give that index its selector IDs.
* **Selector IDs** for the index: sRGB tables 0xf34108 / 0xf341d0 / 0xf33a78 (u16), 2x2 0xf2dd80 and 0xf31ae0 rows;
  alt tables have only 7 entries (cclook relocated 0xf34064 and 0xf31718, and used padding slots of 0xf34300 /
  0xf34248 / 0xf2dea8). Each selector's DB byte = the preset number.
* **Tone family**: 7 families, no spare. Classic Chrome took SEPIA's (5) because SEPIA's curves equal PROVIA's.
  The other families all have their own curves (Velvia 1, ASTIA 2, Neg Std 3, Neg Hi 4, MONO 6 — check
  0xf34098 / 0xf3427c / 0xf33db0 / 0xf3407c / 0xf3448c / 0xf34298 before reusing). A second sim with its own curve
  needs the family-indexed ID tables relocated with an 8th family (tables are packed against other data).
* **Tuning bytes** go through the tuning hooks (`cchook.install(db_params=...)`): each entry checks the old value.

## 4. Other places (not done for Classic Chrome yet)

| Place | What is known |
|---|---|
| RAW conversion menu (**done for Classic Chrome**, `fsim11.py` rawconv, FINDINGS §6d) | Screen `FUN_01442d64` (module 0x41, item group 0x1c); setting 0x152: list 0x779cf4 (node 0x778d9c+0x14) and conversion table 0x78adc8 (pointer 0x78bf58 = 0x78ba10[0x152], no spare row → copy with 11 rows {-, -, code}); the choice is kept as (film code at 0x9d4d30, COLOR code at 0x9d4d44) — apply blob2 0xf10ee0–0xf11048 (`b` at 0xf10ff0 → stub: row → code), cursor 0xf1f8f8–0xf1f964 (`bne` at 0xf1f960 → stub: code → row); name table 0x14838f4 (movw/movt 0x147c624/28, row cap `cmp r4,#9` 0x147c61c), icon table 0x142e558 (record field 0x142ae18). Film codes: 0 PROVIA, 3 ASTIA, 5 Velvia, 6 Neg Std, 7 Neg Hi, **8 Classic Chrome** (as the X-E2). **Consumer: module 0x44 `FUN_016326a4`** (request builder, `switch(block[2])` at 0x163289c: jump table for codes 3–7, default `b` at 0x16328ac → stub writing request word 0x121bcbc = MODE_FSIM) → blob2 `FUN_0107b948` → engine +0x1570 → tuning context. A second new sim: another `cmp` in the three stubs, next free film code (9+). |
| Q menu | node 0x77a544 is the second FILM SIMULATION node (patched); screen not checked |
| Film-sim bracketing | settings 0x3f/0x40/0x41, nodes 0x775e94 / 0x779fe4 / 0x778244, lists 0x77917c / 0x77a4d4 / 0x7759e4; label tables 0x142ac5c / 0x14275b0 (bracketing screen 0x143dfa8, row cap 9) |
| Custom settings | setting 0x9a, node 0x779d4c, list 0x77969c (no conversion table) |
| Shooting-screen indicator | icon-only text group 1058–1067 (table 0x142a1f8) |
| EXIF FilmMode | blob2 table 0x1097f6c (u16 per MODE_FSIM); Classic Chrome = 0x600 |

## 5. Checks before a camera test

1. `build_sdchain.py … --crumbs --uiswap --cc` must still give ffboot 8436762b… (no regression).
2. `emu_fsim11.py`, `emu_cclook.py`, `emu_crumbs.py` ALL OK on the new card (extend them for the new entry).
3. Copy, `sync`, unmount, remount and re-check the sums, unmount (never power off the reader).
4. One question per camera test; results from EXIF or USB reads, never LEDs.
