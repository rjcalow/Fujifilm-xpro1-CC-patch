# Adding new film simulations to the X-Pro1: findings

Goal: add film simulations (Classic Chrome first) as **extra menu entries**, keeping all ten stock ones.
State 2026-11-15. Nothing here is flashed. Camera tests were RAM-only: live over USB (debug firmware `ptpdebug_385`)
and then from the SD-boot cards (§6b, §6d), which work on the camera. **To add another film simulation, an AI agent
should start at §9.**
Addresses are RAM addresses (blob1 loads at 0x774000, blob2 at 0xe0ec80). Session detail: `NOTES.md` (2026-11-12 night onward).

> **Files moved 2026-11-16** (sections below keep the old names as history): `tools/fsim11.py` →
> `classic_chrome/features/menus.py` + `rawconv.py`; `tools/cclook.py`'s plan → `classic_chrome/features/cc_look.py`
> (the live USB tool stays `tools/cclook.py`); `tools/crumbs.py` / `cchook.py` → `classic_chrome/engine/chain.py` /
> `hooks.py` (the old names still import); `tools/emu_crumbs.py` / `emu_fsim11.py` / `emu_cclook.py` →
> `classic_chrome/validate/emu_chain.py` / `emu_card.py` / `emu_look.py`, all run by `classic_chrome/verify.py`.

## 1. Summary

| Part | State |
|---|---|
| Free film-sim slots inside the firmware | **Found**: 3 hidden enum values, no bounds to change (§2) |
| How a menu choice becomes a film simulation | **Mapped** (§3) |
| An 11th row in the FILM SIMULATION menu | **Works on the camera from the SD card**: X-E2 icon + CLASSIC CHROME, selectable, selects hidden film sim 6, shown on the shooting-menu line (§4, §6b) |
| Classic Chrome look for the new entry | **Own data** (2026-11-13): presets 17/18/12 + tone family 5 for colour mode 1, PRO Neg. Hi back to stock; emulator-proven, camera photos pending (§6c) |
| Space for the new look's data (matrices, curves) | **Found**, plenty (§5) |
| Space for names / lists / code | **Found** (§5) |
| Where menu rows get their name + icon | **Found**: tables + row limit in module 0x41 (§6); icon already in the X-Pro1 font |
| Image pipeline using the new slot's own data | **Done**: 9 fallback instructions → stubs, 2 tables relocated, data in free presets (§6c) |
| RAW CONVERSION menu (playback) | **Works on the camera** (2026-11-15): CLASSIC CHROME row, converts as Classic Chrome (§6d) |
| Four looks on the SD card (PR #3: Superia 400, Reggie's Portra, Kodachrome II, focus peaking) | **Works on the camera** (2026-11-17): rows 11–13 next to Classic Chrome; also fixes a WHITE BALANCE menu name bug of the earlier cards (§11) |
| ACROS (from the X-Pro2) | **Researched** (2026-11-16): colour modes 10–13 of its own, same table scheme and curve format as the X-Pro1, plus an ACROS-only per-ISO processing category; an ACROS-style film sim is feasible, a faithful copy is not (§10) |
| Other menus (Q menu, bracketing, custom settings), EXIF | Lists located, not patched (§3, §7) |

## 2. Free film-simulation slots

The internal film-sim number (MODE_FSIM) runs 0–12 and every check accepts 0–12, but the menu only offers ten:

| MODE_FSIM | Meaning | In the menu | Colour mode it selects |
|---|---|---|---|
| 0, 1, 3 | PROVIA, ASTIA, Velvia | yes | 0, 5, 4 |
| **2** | "F1c" | **no** | 0 (PROVIA) |
| **4** | "B&W" (old plain mono) | **no** | 2 (mono) |
| 5 | SEPIA | yes | 3 |
| **6** | "CHROME" | **no** | **1** (unused colour mode, falls back to PROVIA data) |
| 7–10 | MONO, +R, +Ye, +G | yes | 2 |
| 11, 12 | PRO Neg. Std, Hi | yes | 6, 7 |

* **Three spare values: 6, 2 and 4.** 6 is the cleanest (own colour mode 1). 2 and 4 need their entry in the
  fsim → colour-mode table (blob2 0xf396b0, 12 × u32) changed, e.g. to the spare colour modes 8 or 9.
* Accepting 0–12 without change: saved-setting reader blob1 0x9bad40, RAW-conversion converter blob2 `FUN_010d1b54`,
  fsim → colour mode blob2 `FUN_00f38780`. A 13th+ value would need all three widened.
* So **up to three new film simulations** fit without touching any range check.

## 3. How the menus work (settings model)

Film simulation is setting **0x3d**. Everything is data in blob1 (0x774000–0x77c000 and 0x78a000–0x790000),
identical in RAM and in the update file, and can be changed live by POKE.

**Menu nodes**: 6 words {group, setting, 7, 0, link, pointer to list of allowed rows}. A list is (row, 0) pairs
ending in 0x7ffffffe.

| Node | Setting | List | Rows (menu order) | Menu |
|---|---|---|---|---|
| 0x779ffc | 0x3d (group 0x3c) | 0x779a84 | 0 1 2 8 7 6 4 3 5 9 | FILM SIMULATION (camera-tested) |
| 0x77a544 | 0x3d (group 0x01) | 0x77b908 | same | second copy (Q menu?) |
| 0x775e94 / 0x779fe4 / 0x778244 | 0x3f / 0x40 / 0x41 | 0x77917c / 0x77a4d4 / 0x7759e4 | same | Film-sim bracketing FILM 1 / 2 / 3 |
| 0x779d4c | 0x9a | 0x77969c | same | unknown (custom settings?) |
| 0x778d9c | 0x152 | 0x779cf4 | 0 1 2 8 7 3 5 4 6 9 | unknown (RAW conversion?) |

**Conversion tables**: one per setting, pointer array 0x78ba10[setting]; rows of 3 words {c0, c1, c2}, ending
{0xffff ×3}; engine blob1 `0x78a9ec(setting, value, from, to)` (0 = row number, 1–3 = c0–c2).
Film sim: 0x3d → 0x78f168; 0x3f / 0x40 / 0x41 → 0x78f804 / 0x78d680 / 0x78c7b0 (identical content).

| Row | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | **10** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Shown as | PROVIA | Velvia | ASTIA | +R | +Ye | +G | MONO | Neg Std | Neg Hi | SEPIA | **empty** |
| c0 = stored value | 0 | 2 | 1 | 3 | 4 | 5 | 6 | 11 | 12 | 7 | — |
| c2 = MODE_FSIM | 0 | 3 | 1 | 8 | 9 | 10 | 7 | 11 | 12 | 5 | — |

* **Row 10 is an empty placeholder in all four tables**: one new film sim needs only two words written per table.
  More rows need the table copied elsewhere and its pointer in 0x78ba10 changed.
* **Stored value** = 4 bits (high nibble of 0x9cafef + 7 × mode, per settings bank + 0x12a). Used: 0–7, 11, 12.
  **Free: 8, 9, 10, 13, 14, 15** (six values). Readable over USB, so a test result can be read back.
* Paths: setting → film sim blob1 0x786524 (c0 → c2); menu row → stored value blob1 0x79c348 (row → c0);
  cursor position blob2 `FUN_00f1e248` case 0x3d (fsim → row); custom-setting load blob2 0xf13e68.

## 4. Camera tests (2026-11-13, RAM only, `tools/fsimslot.py`)

| Step | Change | Result on the camera |
|---|---|---|
| 1 | Table row 10 := {stored 13, –, MODE_FSIM 6}; nodes 0x779ffc + 0x77a544 → list `… 9, 10` at 0xb800 | **11th row appears, blank** |
| 2 | + name table 0x1483c20[10] := text 819 ("B&W"); row limit 0x147c748 `cmp r4,#9` → `#10` (live code poke, I-cache invalidated via CALL blob1 0x8a5d70) | **Row reads "B&W" and can be selected** |
| 3 | Row selected | **Active MODE_FSIM global 0x9cb890 = 6** (read over USB); pictures look like PROVIA, as expected (colour mode 1 has no data of its own yet) |
| 4 | fsim → colour-mode table 0xf396b0[5] (fsim 6): 1 → 7 (PRO Neg. Hi's colour mode = X-E2 Classic Chrome data in the flashed v2) | applied; photo comparison pending |
| 5 | X-E2 font loaded over the X-Pro1 font (`fontswap.py xe2`, 10838 words differ); text 819 := "CLASSIC CHROME", text 1215 := U+F2B9 (X-E2 Classic Chrome icon); icon tables 0x142aa4c / 0x1427320 copied with an 11th entry (1215) to 0xb900 / 0xb940, 4 menu-record pointers moved | **Row shows the Classic Chrome icon and name** (the font swap turned out to be unnecessary, §6) |
| 6 | SD card `sdchain_cc11_green` ffboot 140622c0… (steps 1–5 at boot, no font change) | Pop-up OK; **the shooting-menu line still showed PROVIA's STD badge** (`samples/menu.jpg`, `menu1.jpg`) |
| 7 | Film sim → menu-row byte tables 0x1474e7c / 0x1474e3c (module 0x41), entry 6: 0 → 10 (live) | **Shooting-menu line shows the Classic Chrome icon**; on the card as ffboot 1923db4f… |

* **Proven: a new menu entry can select a hidden film simulation with data patches plus one instruction.**
* Live code patching works: poke, read 2 MB elsewhere to push the data-cache line out, CALL 0x8a5d70.
* Not checked yet: the shooting-screen indicator and Q menu for the new value, EXIF of a photo, and what a flash
  boot does with the saved value (the nibble at 0x9cafef still read 5: the active copy is elsewhere).
* Live changes to blob1 data and module 0x41 are lost at power off/on (reloaded from flash); the language block is
  not. The SD card re-applies everything at each SD boot.

## 5. Space for new film simulations

| What | Where | Free |
|---|---|---|
| Film-sim numbers | MODE_FSIM | 6, 2, 4 (§2) |
| Colour modes | 0–9 | 1, 8, 9 |
| Stored setting values | 4-bit field | 8, 9, 10, 13, 14, 15 |
| Conversion-table rows | 4 tables | row 10 in each; more by relocating |
| 3×3 colour-matrix presets | 30 slots, ID table blob2 0xf33b94 | **17–30 unused** (identity placeholders; data IDs 0xdc23 + 0x12 × (n − 17)) |
| 2×2 chroma-matrix presets | 30 slots, ID table blob2 0xf2e0d0 | **12–30 unused** (IDs 0xe401 + 8 × (n − 12)) |
| Tone curves | 29 entries, blob1 0x80b700 | unreferenced on stock: #1–3, #24, #25, #28, #41 (#40 holds CC's curve in v2) |
| Preset-selector index | ID tables 0xf34108 etc. (0x29 entries) | index 0x10 never produced by any code path |
| Text strings | each language block (0x20000) | 0xdb24–0x12d2c bytes unused at the end of every block |
| Text IDs | table of 1693 entries | **none free** (table is packed; cannot grow in place) |
| Lists / hook code in RAM | loader filler 0x9000–0xbfff | all 0xff in the running firmware; the cc11 card uses up to 0xac60 |
| Font glyphs | X-Pro1 font | U+F2B9 (Classic Chrome icon) present but unused; the X-E2 added only U+F2D1–U+F2FE |
| blob1 in flash | compressed limit 0x140000 | 0x13bbe0 used by v1 (about 17 KB headroom) |

So the look data (matrix + chroma + curve) for several new film simulations fits in existing unused slots, as
pure data. Only the code that picks the slot needs patching (§7).

## 6. Menu text and icons (found 2026-11-13)

**The menu screens are drawn by code in module 0x41** (file 0x46025c, RAM 0x1420000; decompile
`decompiled/xpro1_mod41_0x1420000.c.gz`). blob2 turns a screen ID into a draw function: `FUN_00f7c6b4` → u16 table
0xf7d17c[screen − 0x100] → module table 0x1430190 (8 bytes per screen: function, flag) → `0x1422520(n)`.
Film-sim bracketing screen 0x154 = entry 0x4f = function 0x143e4c8 (list drawn by 0x143dfa8).

**Row labels come from u32 tables in module 0x41, indexed by menu row (menu order), 10 entries each:**

| Table | Text IDs | What |
|---|---|---|
| 0x1483c20 | 804 807 810 813 816 820 826 823 829 832 | shooting menu, name (used by 0x147c5dc; followed by a 0 word) |
| 0x1427320, 0x1427b88, 0x142b970 | 802 805 … 830 | small icon |
| 0x14283a4, 0x142aa4c | 803 806 … 831 | icon |
| 0x14838f4 | 1198 1200 … 1216 | name, second screen (0x147c5dc when item = 0x1c) |
| 0x142e558 | 1197 1199 … 1213, 830 | icon, second screen |
| 0x142a1f8 | 1058 … 1067 | icon only (shooting-screen indicator?) |
| 0x142ac5c | 649 651 … 667 | bracketing list, icon + name (0x143dfa8) |
| 0x14275b0 | 648 650 … 666 | bracketing list, icon |

* **The shooting-menu line** (setting value on the right) is a different path: item 8's value index is
  `FUN_0146ef68` case 8 = byte table **0x1474e7c[MODE_FSIM]** (menu row per film sim: 0 2 0 1 5 9 **0** 5 7 6 8 4 3;
  copy 0x1474e3c for `FUN_0146fcec`), then icon table A of the item's record (`FUN_01474628`). Film sim 6 needs
  entry 6 = 10 there too (camera-confirmed).
* **Why the 11th row is blank (camera-confirmed twice):** the draw code only labels rows 0–9 (`if (9 < row) skip`
  in 0x147c5dc; last row capped at 9 in 0x143dfa8) and the tables have 10 entries.
* Text draw `0x1433480(x, y, id)`: **id < 0x69f = text ID**; `0xff000000 + n` (n < 0x883) = UI-DB graphic;
  0xfd000000/1 special. So text IDs cannot simply be extended past the table: the limit is in code.
* Text IDs are the same in all 35 languages (`tools/uitext.py`); icons are font characters (PROVIA U+F06A …
  SEPIA U+F06E, Neg Hi/Std U+F201/F202). The shooting menu uses the 800 group (camera: label on 833 showed as
  DYNAMIC RANGE).
* **What a labelled 11th row needs (done for the shooting menu):** (1) an 11th entry in each table the screen uses
  (tables are packed: copied elsewhere and repointed), (2) the row limit 9 → 10 in the draw function (0x147c748),
  (3) text IDs for name and icon: no new ID is possible (limit 0x69f in code), so two unused IDs (819, 1215) are
  repointed, (4) the film sim → row byte tables (0x1474e7c / 0x1474e3c).
* Module 0x41 is plain (uncompressed) in the update file and in RAM, so data patches are simple; code patches
  need the SD-boot route or a flash.

### Name and icon from the X-E2 (camera-proven 2026-11-13)
* X-E2 Classic Chrome menu string: icon glyph **U+F2B9** + "CLASSIC CHROME".
* **The X-Pro1 font already contains U+F2B9, byte-identical to the X-E2's, unused by any X-Pro1 string.** So no font
  change is needed. Font index: one u32 per code point at 0x38050 + 4 × (c − 0xE000) (glyph offset = value >> 8,
  size = gap to the next entry); fits all 304 private-use characters the X-Pro1 UI uses. The X-E2 font adds 46 glyphs
  (U+F2D1–U+F2FE, 0x3161 bytes at 0x7aa92) and is otherwise identical.
* Name and icon use two spare text IDs, repointed to new strings in each language block's free tail: **819**
  ("B&W", unused) := "CLASSIC CHROME", **1215** (an unused copy of the SEPIA icon) := U+F2B9. Neither is referenced
  by code or by any module table; each has its own descriptor in all 35 languages.
* Menu items are records {item, title text, graphic, flag, icon table A, icon table B} in module 0x41; the
  FILM SIMULATION item exists twice (0x14299ec item 11, 0x142bd88 item 8), both using A = 0x142aa4c, B = 0x1427320.
  These are copied with an 11th entry (1215) and the four record fields repointed.

## 6b. SD-boot card (camera-confirmed 2026-11-13)
`build/sdchain_cc11_green/` (README there), built with `tools/build_sdchain.py … --crumbs --uiswap --cc --fsim11`.
Current card: ffboot **1923db4f…**, ffsys 7661dadc…. It is the green-accent v3 card plus the new entry, applied in
RAM where each piece of data arrives (old value checked before every write):

| When | What (`tools/fsim11.py`) |
|---|---|
| Stage B (blob1 in RAM), table-driven | conversion row 10 := {13, –, 6}; both FILM SIMULATION nodes → 11-entry list; two call sites below |
| blob1 0x9717b8 `blx r3` (module init loop) → hook, only for module 0x41's init 0x1430170 | name entry 819, row limit `cmp r4,#10`, both records → 11-entry icon tables, fsim → row maps entry 6 := 10; D-cache clean + I-cache invalidate |
| blob1 0x972520 (start blob2) → hook | fsim → colour mode 0xf396b0[5] := 7 |
| Language load (cchook hook, `lang=`) | texts 819 / 1215 in all 35 languages; PRO Neg. Hi keeps its name |

Checks: `tools/emu_fsim11.py` ALL OK (20 checks, real firmware code around each hook), `tools/emu_crumbs.py` ALL OK;
without `--fsim11` the builder still reproduces the earlier card byte for byte (8436762b…).
Camera: entry with icon and name in the pop-up and on the shooting-menu line (after the second build).
Caution: select a stock film simulation before booting from flash; the flash firmware has no row for value 13.

## 6c. Own look data for colour mode 1, PRO Neg. Hi restored (2026-11-13, `tools/cclook.py`)
Colour mode 1 inherits PROVIA's detail, chroma gain and H/S family, which are Classic Chrome's. The three selections
that differ fall back to "index 0 / family 0" for colour mode 1 in one instruction each; those become calls to small
stubs (loader filler) that answer **index 7** (matrices) or **family 5 / code 0xff** (tone) for colour mode 1:

| Selection | Sites (blob2) | Where the data goes |
|---|---|---|
| 3x3 sRGB / alt | `FUN_00f32fcc` 0xf333c4 / 0xf3344c | sRGB tables' unused index 7 (IDs 0xdd26 / 0xdd8e / 0xdd5e := preset 17); alt tables' 8th slot: padding words 0xf3430e / 0xf34256 := ID 0xe409 (:= 18), 0xf34064 relocated (movweq/movteq 0xf33474) |
| 2x2 | `FUN_00f2d404` 0xf2d724 / 0xf2d7a8; `FUN_00f30b10` 0xf30d7c / 0xf30e0c | index 7: 0xe4a0 and 0x10101 + 0x30·row := preset 12; alt: padding 0xf2deb6 := ID 0xe40b (:= 12), 0xf31718 relocated with stride 8 (0xf30e10/14/18) |
| Tone family | `FUN_00f321f0` 0xf32218; `FUN_00f3232c` 0xf32360 / 0xf32570 | family 5 / 0xff taken from SEPIA (its curves all equal PROVIA's; its byte-table entries 0xf34365 / 0xf3443d / 0xf34075 → family 0 / 0xf9); family 5's 40 curve IDs := 38 |

* Presets 17 (sRGB 3x3) / 18 (alt 3x3) get the v2 Classic Chrome matrices, preset 12 the v3 2x2; the 76 bytes of the
  v2 PRO Neg. Hi patch go back to stock. 161 tuning bytes, 20 blob2 words, 7 filler blobs (stubs + 2 tables).
* Guard: tone patches only if blob1's curve table holds curve 38 (the flashed v2's slot #40); a missing curve
  number falls back to curve 0 in the lookup 0x8056a8, so a stock-flash camera stays safe.
* Why not an 8th family: the byte before the cm→family table is the last curve ID of Neg Std's table, and the
  family-indexed ID tables are followed by other data. Donating SEPIA's family costs nothing.
* Proven in the emulator (`tools/emu_cclook.py`, real firmware functions, every sRGB/alt/mode variant): colour mode 1
  now produces exactly what v2's PRO Neg. Hi produced; PRO Neg. Hi produces what stock does; PROVIA, SEPIA, MONO
  unchanged. Applied live on the camera (flash-booted v2) and on the card `build/sdchain_cc11own_green/`.

## 6d. RAW CONVERSION menu (2026-11-15, `tools/fsim11.py` rawconv; camera-confirmed 2026-11-15)

The RAW CONVERSION screen is its own setting (0x152, node 0x778d9c, list 0x779cf4 rows [0,1,2,8,7,3,5,4,6,9],
conversion table 0x78adc8 via pointer 0x78bf58, no spare row). It does **not** store a MODE_FSIM: the choice is
kept in the RAW-convert block 0x9d4d28 as a **film code** at +8 (0 PROVIA, 3 ASTIA, 5 Velvia, 6 Neg Std, 7 Neg
Hi) and a COLOR code at +0x1c (6–10 = mono / sepia). Blob2 `FUN_00f10e58` (0xf10ee0–0xf11048) stores row → codes,
`FUN_00f1e248` (0xf1f8f8–0xf1f964) shows codes → row; module 0x41 draws the row name from table 0x14838f4 (cap
`cmp r4,#9` at 0x147c61c) and the icon from 0x142e558.

**Who turns the film code into the film simulation** could not be found by reading (no table, no direct
reference). Three runs of a RAM-only call logger (`tools/fsimlog.py`, 10 hooks, conversions PROVIA → Velvia and
PROVIA → ASTIA) traced the value backwards: tuning context (`FUN_00f38a00`, r1 = 3 / 1) ← job parameters ←
engine +0x1570 ← request word [2] of blob2 `FUN_0107b948` (mode 0xf job) ← **module 0x44 `FUN_016326a4`**, whose
`switch(block[2])` at 0x163289c is the mapping (3→1, 5→3, 6→11, 7→12, default 0) — the X-E2 stores film code **8**
for Classic Chrome, so the X-Pro1 gets the same code.

Card `build/sdchain_cc11rc_green/` (ffboot 6693177b…) adds, all in RAM: row 10 → code 8 in a copied list and
table (stage B); a row-10 case in the apply chain and a code-8 case in the cursor chain (two blob2 `b`/`bne`
words → stubs, HOOK_B2 table); an 11th entry in the screen's name and icon tables with the cap raised (four
module 0x41 words, HOOK_INIT table); and `case 8 → film simulation 6` in module 0x44 (its default branch →
stub; a second HOOK_INIT table applied when module 0x44's first init 0x15c05ec is about to run).
`emu_fsim11.py` runs the real conversion engine, both blob2 chains, the module 0x44 switch (codes 0/3/5/6/7/8/9)
and checks the module 0x41 words: ALL OK (27 checks); `emu_cclook.py`, `emu_crumbs.py` ALL OK.
**Camera (user, 2026-11-15): CLASSIC CHROME shows in the shooting menu and in the playback RAW CONVERSION menu,
and the conversion works.**

## 7. Still to do

1. Camera check of the own look (§6c): photos CLASSIC CHROME vs PRO Neg. Hi vs PROVIA vs SEPIA, same scene;
   CLASSIC CHROME should match what PRO Neg. Hi gave on v2, PRO Neg. Hi should be Fuji's original again.
2. Check a photo's EXIF (Ver3.89, film mode).
3. Other places a film sim appears: Q menu, film-simulation bracketing (nodes/tables 0x3f–0x41), custom settings
   (0x9a?), shooting-screen indicator (1058 group), EXIF FilmMode for MODE_FSIM 6 (0x600). RAW conversion: done (§6d).
6. **Classic Chrome accuracy test** (TODO.md): the same scenes through an X-T20 / X-E2 (real Classic Chrome) and the
   X-Pro1 card (in-camera RAW conversion, Color 0, same WB), compared per hue; decide only then whether to correct.
4. What a flash boot does with saved value 13 (and where the active setting copy is stored).
5. Flash only when complete; until then the SD card.

## 8. Tools added

| Tool | Use |
|---|---|
| `tools/uitext.py` | print UI text by ID, any language |
| `tools/fsimslot.py` | live 11th-row test: `apply` / `restore` / `status` (row, name, icon tables, row maps, one code poke) |
| `classic_chrome/features/menus.py`, `build_sdchain.py --fsim11` | the same changes on the SD-boot card (was `tools/fsim11.py`) |
| `classic_chrome/validate/emu_card.py` | emulator test of the card's hooks (real firmware code; was `tools/emu_fsim11.py`) |
| `tools/fontswap.py` | live: load the X-E2 font in RAM (research; not needed for the icon) |
| `tools/cclook.py` (live), `classic_chrome/features/cc_look.py` (plan), `build_sdchain.py --cclook` | own look data for colour mode 1 + PRO Neg. Hi restore: live `apply` / `restore` / `status`, and the card |
| `classic_chrome/validate/emu_look.py` | emulator test of the look patches (tuning hook, HOOK_B2, real pipeline selection functions) |
| `tools/uitextmark.py` | live: label text IDs with "#ID" to see what a screen draws; `restore` removes them |
| `tools/fsimlog.py` | live RAM-only call logger (`install` / `read` / `remove`): ring of {tag, caller, r0, r1, 4 loaded values}; how the RAW-conversion consumer was found (§6d, §9.5) |
| `classic_chrome/features/rawconv.py`, `build_sdchain.py --rawconv` | the RAW CONVERSION row on the card (§6d) |
| `classic_chrome/convert.py` | **the converter**: official firmware → complete SD-boot card, one module per feature (README there) |
| `classic_chrome/verify.py` (`convert.py --verify`) | all emulator checks + the known-good builds (`validate/regression.py`) on a built card |
| `decompiled/xpro1_blob1_0x774000.c.gz`, `xpro1_mod41_0x1420000.c.gz` | X-Pro1 blob1 and module 0x41 decompiles (Ghidra 12.1.4 + JDK 21 in `~/opt`) |

## 9. Instructions for an AI agent: adding another film simulation

Read this whole section, then `ADDING_FILM_SIMS.md` (the numbers and tables), then the parts of §2–§6d and
`NOTES.md` that cover the place you are changing. Classic Chrome (film sim 6) is the worked example for every step;
copy its code (`classic_chrome/features/menus.py`, `rawconv.py`, `cc_look.py`) rather than inventing a new mechanism.

### 9.1 Rules from the camera owner (non-negotiable)

1. **Never write flash.** Everything goes into RAM: live over USB for experiments, the SD dual-boot card for use.
   The flashed firmware is `build/ptpdebug_385` (v2 + USB debug PTP ops PEEK 0x9010 / POKE 0x9011 / CALL 0x9012).
2. **Results come from data you read**, i.e. EXIF, USB PEEK, the logger, the user's photos. Never LED blink codes.
3. **Before every live camera test, tell the user what they will see** (e.g. "one extra row", "nothing visible")
   and how it is undone. **Remove test changes afterwards** (`restore` / `remove`, or say a power cycle clears them).
   A leftover test label once replaced a menu name, and the user had to point it out.
4. Keep each step tied to the film-sim goal. One question per camera test. Ask the user to do the camera actions
   (menu, shutter, conversion, cable); you do the USB reads.
5. Before the user boots **without** the card, a stock film simulation must be selected: the flash firmware has no
   row for the new stored value.
6. Commit only when asked, on the working branch (`v3-cc-sdboot`); docs (§1 table, the new section, README status
   row, TODO, card README, NOTES) are part of every finished step.

### 9.2 Environment

* Python: `~/.venvs/xpro1-re/bin/python` (keystone, capstone, unicorn, numpy). Run from `re/`.
* **Card input is the official 3.82 file `../FPUPDATE.DAT`** (repo root). `build/ptpdebug_385/FPUPDATE.DAT` is only
  for `--flash` / the emulators' 4th argument (the flashed tuning values the hooks expect). Building the card from
  the flashed file gives a card whose tuning checks fail.
* Images: `work/blob1.bin` (RAM 0x774000), `work/blob2.bin` (0xe0ec80), `.asm` listings next to them; modules are
  plain in the decoded update image (XOR 0xff): 0x41 at file 0x46025c → RAM 0x1420000, 0x44 at file 0x60025c → RAM
  0x15c0000 (0x42 0x14c0000, 0x43 0x1500000). Full RAM dump: `work/dram/menu.bin` (256 MB, index = address).
  Decompiles: `decompiled/*.c.gz` (blob1, blob2, modules 0x41–0x44, X-E2 blob1/blob2); unzip to the scratchpad.
* Camera on USB: `lsusb | grep -i fuji` → `04cb:0280`. Flash-booted = debug PTP available; SD-booted cards too.

### 9.3 Workflow (one film simulation)

1. **Pick the numbers** from `ADDING_FILM_SIMS.md` §1 (MODE_FSIM, colour mode, stored value, menu row, text IDs,
   glyph, presets, curve slot, tone family, RAW-conversion film code). Write them down in NOTES first.
2. **Verify every word you will change, statically**, in the official image (like `fsim11.check()` /
   `check_rawconv()`): each patch is (address, stock word, new word), and the runtime code re-checks the stock word
   before writing. Never patch a word you have not read.
3. **Live test over USB** for anything visible (menu rows, names, icons): small `apply` / `restore` / `status` tool
   like `tools/fsimslot.py`, data in free loader filler (check it is all 0xff first). Tell the user what changes.
4. **Card code** in the converter `re/classic_chrome/` (README there): a new film simulation is a `FilmSim` in
   `film_sims.py` (+ its look in `looks.py`); a new menu or place is a new `card.Part` module added in `convert.py`.
   The engine (`engine/card.py`) routes each change by where it lives:
   * blob1 data (setting tables, menu lists, pointers) → stage-B markers (applied before blob1 runs);
   * module code/data → the module-init hook (blob1 0x9717b8 `blx r3`): one patch table per module, applied when
     `r3` is that module's first init (0x41: 0x1430170, 0x44: 0x15c05ec). Modules are streamed in later; patching
     them earlier does nothing;
   * blob2 code → HOOK_B2 table (blob2 in RAM, not started); guard entries that depend on optional data;
   * tuning bytes → cchook `db_params` (old value checked);
   * new code → small stubs in the filler; a stock branch to "default/fallback" is the usual place to divert
     (`b`/`bne`/`movne` → stub that handles the new value and jumps back to the stock target otherwise).
   Filler for the card: `0xa400`–`0xc000` (`install` asserts this). Live tools use `0xb800`–`0xd010`; don't mix.
5. **Emulator checks** (real firmware code, unicorn): extend `classic_chrome/validate/emu_card.py` / `emu_look.py`
   (constants in `validate/card_map.py`) with the new value *and* the stock values (stock must be unchanged). Run
   them all with `classic_chrome/verify.py ../FPUPDATE.DAT <card dir> [converter options]` or `convert.py … --verify`:
   it must end with ALL OK.
6. **Regression**: `classic_chrome/convert.py ../FPUPDATE.DAT <out> --verify` checks ffboot against the known-good
   builds (`classic_chrome/validate/regression.py`: default `6693177b…` and three variants); `build_sdchain.py ../FPUPDATE.DAT work/chain/chain_crumbs.bin
   <out> --crumbs --uiswap --cc` must still give `8436762b…`. New feature → its own option, off until camera-tested.
7. **Card**: build into `build/sdchain_<name>/` with a README (command, sha256, what changed, checks, what's not
   covered). Write: copy both files to the card root, `sync`, unmount, remount, re-check sha256, unmount from
   outside the mount point (`cd ~` first). Don't power off the reader.
8. **Camera test**, then docs (§9.1 rule 6).

### 9.4 Every place a film simulation appears

| Place | Classic Chrome | Where |
|---|---|---|
| FILM SIMULATION menu (shooting) + shooting-menu line | done | §4, §6, §6b; `features/menus.py` |
| Look data (matrices, tone, chroma) | done | §6c; `features/looks.py`, `cc_look.py` |
| RAW CONVERSION (playback) | done | §6d; `features/rawconv.py` |
| Q menu, film-sim bracketing, custom settings, shooting-screen indicator, EXIF FilmMode | open | `ADDING_FILM_SIMS.md` §4 |

A second new film simulation needs a fresh value in each place (the stubs get one more `cmp`), never Classic
Chrome's numbers: film sim 6, colour mode 1, stored 13, row 10, texts 819/1215, presets 17/18/12, family 5,
RAW-conversion code 8.

### 9.5 When reading the code doesn't find it: trace it live

Some links have no table and no direct reference (state is passed through messages, structs and pointers). The
RAW-conversion consumer was found only like this:

1. Hook candidate functions with `tools/fsimlog.py` (each hook: first instruction → branch to a stub that logs
   {tag, caller, r0, r1, 4 values loaded through r0/r1/fp} into a RAM ring, runs the original instruction, returns).
   A hooked first instruction must not be PC-relative; check the site holds its stock word before installing.
2. Ask the user for one action with a **recognisable value** that differs from the current setting (e.g. a
   PROVIA-shot RAW converted as ASTIA, so the value 1 can't come from the file).
3. `read`, find the entry carrying that value, go one level up (its caller / the struct it came from), add hooks
   there, repeat. Three rounds were enough for RAW conversion.
4. `remove` when done (also wipes older ring layouts). A power cycle removes everything too.

Static search tips that worked: grep the `.asm` for `movw/movt` pairs and literal-pool words with the address
(Ghidra hides pointer-based writes); scan `work/dram/menu.bin` for the 32-bit address; decompiles name cross-blob
calls `func_0x…`; jump tables sit right after `ldrls pc, [pc, rN, lsl #2]`.

### 9.6 Pitfalls already paid for

* PEEK must be 4-byte aligned (an odd address returns 0 bytes and aborts).
* Live code patches: POKE, then read 2 MB (pushes the D-cache), then CALL 0x8a5d70 (I-cache invalidate).
* A power loss / battery change wipes every live patch; re-check the filler is clean (0xff) before re-installing.
* Keystone rejects numeric local labels (`1f`); use named labels.
* Emulating a chain entered mid-function: give it a fake frame whose popped return address is the stop address.
* A conversion-engine reverse lookup returns the *first* matching row; ambiguous codes (6/7 appear twice in
  setting 0x152) are not a fault.
* Stub tables grow: re-check slot sizes (`assert len(code) <= …`) after adding entries.

## 10. ACROS research: the X-Pro2 firmware (2026-11-16, static only)

Source: `FWUP0008.DAT` (X-Pro2; `FWUP0008_xpro2.DAT` is the same file, identical SHA-256). Unpacked to `re/x2/`
(`tools/unpack.sh`; blob1 RAM 0xa51000, blob2 0x1263000; third code image file 0x7d025c → RAM 0x18e3000, 0x6b0000,
saved as `x2/blob3.bin`). Nothing about ACROS exists on any EXR-generation body (X-Pro1, X-E2, X-T1), so the X-Pro2
(X-Processor Pro, 24 MP X-Trans III) is the only donor.

**What ACROS is in the firmware**
* Four film simulations: MODE_FSIM 14 ACROS, 15 +R, 16 +Ye, 17 +G (`MODE_FSIM_ACROS_N/R/Y/G_FILTER`, blob1
  0xca9728); develop codes 12–15; own UI items in the shooting menu, Q menu, custom settings, film-sim bracketing
  and RAW conversion (`PB_RAW_FSIM_ACROS(_Y/_R/_G)`). Grain effect (`MODE_GRAIN_OFF/SOFT/HARD`) arrived with it.
* **Film sim → colour mode** (blob2 0x13fab48, jump table, result stored at struct +0x52):

  | film sim | PROVIA | ASTIA | Velvia | B&W/MONO (all filters) | SEPIA | CHROME | Neg Std | Neg Hi | CLASSIC CHROME | ACROS | +Ye | +R | +G |
  |---|---|---|---|---|---|---|---|---|---|---|---|---|---|
  | colour mode | 0 | 5 | 4 | 2 | 3 | 1 | 6 | 7 | **8** | **10** | **11** | **12** | **13** |

  Colour modes 0–7 are **numbered exactly as on the X-Pro1** (table blob2 0xf396b0), Classic Chrome is 8 as on the
  X-E2, 9 is unused, and ACROS takes four colour modes of its own: unlike MONO, its filters are separate colour
  modes, not a filter setting. A flag "ACROS" (colour mode 10–13) is also stored at struct +0x53 (blob2 0x13fb810).
* **Same parameter scheme as the X-Pro1**: parameter area at file **0xc025c**, 0xd0000 bytes, loaded to RAM
  0x2668000 (pointer 0xea7eb8; byte getter `0xb94708`/`0xb94ab4`, u16 getter `0xb94ac4`; IDs 0x202/0x203 = marker
  0xaa55); value(ID) = byte at the area + ID (two ID ranges ≥ 0x160000 are banked). The pipeline functions at blob2
  0x13eb000–0x13f3000 read the colour mode and index **u16 parameter-ID tables [row][14 colour modes]** (tables
  0x17af52c, 0x17af66c, 0x17b031c, 0x17b048c, 0x17b059c, 0x17b0454, 0x17b0854, 0x17b094c, …): ACROS has its own ID
  in several of them (e.g. 0x17af52c rows: preset 2 for ACROS where every other film sim has 1).
* **ACROS gets its own processing category.** Two switches on colour mode − 2 (blob2 0x13ebbcc, 0x13f0814) sort film
  sims into 0 = colour, 1 = MONO/SEPIA, **2 = ACROS** (3 = ACROS with a filter, second switch), each category with
  its own per-ISO tables (struct +0x4d = ISO step, 15 steps): table 0x17b06d0 is 1 at all 15 ISO steps for ACROS but
  only at the five lowest for the rest, and 0x17b06b8 / 0x17b088c / 0x17b0904 hold ACROS rows. This matches
  Fujifilm's description of ACROS (fine grain and tone that change with ISO), and means ACROS is **more than a
  curve and a matrix**.
* **Tone curves: same format as the X-Pro1** (blob1 table 0xe27970, count 0x30 = 48 entries of 0x48 bytes:
  number, 9-byte segment header, 28 × 14-bit knots; the X-Pro1 has 29 at 0x80b700). Only three X-Pro2 curves are
  byte-identical to X-Pro1 ones (X-Pro2 41 = X-Pro1 0 / 26, 45 = 28); the rest are re-tuned for the X-Pro2's sensor,
  and the X-E2's Classic Chrome curve is not among them.

**What that means for an X-Pro1 ACROS**
1. A faithful copy is not possible: ACROS's per-ISO processing category belongs to the X-Processor Pro's pipeline;
   the X-Pro1 (EXR Pro) has no equivalent stage to switch on. Its tables are tuned for another sensor.
2. An **ACROS-style film simulation** is possible with the converter: a new `FilmSim` (MODE_FSIM 2 or 4, own colour
   mode 9, text IDs + an icon), MONO's matrices (monochrome), and ACROS's tone taken the way Classic Chrome's was:
   the X-Pro2's ACROS curve **relative to the X-Pro2's PROVIA/MONO curve**, applied to the X-Pro1's curve. The +Ye /
   +R / +G variants would need MONO's filter mechanism (one colour mode + filter field on the X-Pro1).
3. **Tone found (2026-11-16):** the X-Pro2's base tone (blob2 0x13f094c: two curves from tables 0x17b0a9c /
   0x17b0eb4 [level·16 + slot], slot from colour mode via blob1 0xbbf8d0, blended by 0x17b0e8c = 128 → one curve)
   is curve 1 for PROVIA, MONO and SEPIA and **curve 7 for ACROS** (all filters). Ported as a change relative to
   PROVIA (`classic_chrome/config/acros_curves.py`): ACROS_X-Pro1 = curve7 ∘ curve1⁻¹ ∘ the X-Pro1 curve, for the
   three curves MONO's base tone uses (#0, #14, #16; tone family 6 IDs 0xdf93/0xdf9a, 0xdfa1/0xdfaf, 0xdfa8/0xdfb6).
   Result: deeper blacks, brighter mid-tones. Live preview: `tools/acros_live.py apply|restore|status` puts them in
   the unused curve slots #1–#3 and points MONO at them (RAM only).
   **Planned build** (after the preview): film simulation 4 (the hidden B&W slot, already monochrome: colour mode 2,
   no filter) as ACROS, menu row 11 with its own name and icon; detection per image by a side table filled where
   the filter is set (`0xf38818`, called with the film sim), read by a stub in the base-tone function
   `FUN_00f321f0` that swaps curves 0/14/16 for 1/2/3 when the image is ACROS; RAW-conversion film code 9 →
   film simulation 4. Needs the converter's second-film-sim support (conversion table moved, 4 texts).
4. Older next steps: (a) decode the X-Pro2's tone-selection code (which curve number each colour mode and tone level uses;
   the counterpart of the X-Pro1's `FUN_00f321f0` / `FUN_00f3232c`), giving ACROS's curves and MONO's for the
   difference; (b) list every [row][14] table where ACROS differs from MONO (colour mode 2), to see what besides
   tone ACROS changes (sharpness, noise reduction, the per-ISO rows); (c) check the X-Pro1 for a free tone family
   (none is free: ADDING_FILM_SIMS.md §1) or relocate the family tables; (d) the second-film-sim limits in the
   converter (row 11, more texts).

## 11. Four looks on the SD card (2026-11-17, from PR #3; camera-confirmed 2026-11-17)

`re/classic_chrome/convert.py --four-looks` (card `re/build/sdchain_fourlooks_green/`, ffboot `4261ad85…`) puts PR #3's
looks next to our Classic Chrome, in RAM at boot, flash untouched. PR #3 itself builds a flashable 3.93
(`public/FOUR_LOOKS.md`) with Classic Chrome in PRO Neg. Hi's slot; on the card Classic Chrome keeps its own
entry, so two things are done differently:

| Row | Entry | How (module) |
|---|---|---|
| 10 | CLASSIC CHROME | as before: MODE_FSIM 6, own look, RAW CONVERSION (menus, looks, rawconv) |
| 11 | SUPERIA 400 | MODE_FSIM 2 → **colour mode 8**; the look's stubs answer for it: ASTIA's 3x3 (index 2), PROVIA's 2x2, PROVIA's detail / chroma gain / H-S family (stock fallbacks), PRO Neg. Std's tone (family 3, code 0xfc) (looks.OwnLook extras). PR #3's +4 % / +12 % 2x2 boost needs a second 2x2 preset and selector index; left out. |
| 12 | REGGIE'S PORTRA | **recipe** on Classic Chrome: AUTO WB R+2/B−4, Color +2, Highlight −1, Shadow −1, Sharpness −2 |
| 13 | KODACHROME II | **recipe** on PRO Neg. Std: AUTO WB R+1/B−2, Color −2, Highlight +1, Shadow +2, Sharpness +2 |

* **Recipes** (features/recipes.py): PR #3's two override points: the shooting-settings copy into the outgoing
  message (blob2 0xf79434) and the compact capture exporter's return (blob1 0x9b7610). PR #3 gives each recipe its own
  MODE_FSIM; the X-Pro1 has three spare ones (2, 4, 6), so on the card a recipe keeps its base's MODE_FSIM and is
  recognised by its stored menu value (settings getter 0x793048(0x3d, 0), a plain read of the settings bank).
  Stored values: Superia 14, Reggie's Portra 15, Kodachrome II 10. MODE_FSIM 4 stays free (ACROS).
* **Rows 11–13** need the setting-0x3d conversion table copied with the extra rows (pointer 0x78ba10[0x3d]), and their
  names are drawn from ASCII strings by PR #3's DRAW stub on the name-draw call 0x147c798 (same text in every
  language). The shooting-menu line shows the base's icon for a recipe (shared MODE_FSIM).
* **Focus peaking** (features/peaking.py): tuning bytes 0xc88c 40→48, 0xc8a5 / 0xc8a7 64→120.
* **Bug fixed on every card**: the FILM SIMULATION row-name table 0x1483c20 has 10 entries; its word 10
  (0x1483c48) is **entry 0 of the WHITE BALANCE name table** (COLOR TEMPERATURE, FINE, SHADE, …; entry 0 = AUTO,
  stock 0 = no name). The earlier cards (and PR #3's 3.93) wrote Classic Chrome's text ID there (visible effect on the
  WB menu not confirmed on the camera; the four-looks card's WB menu is normal, 2026-11-17). The table is now
  copied with the new rows and its pointer (movw/movt 0x147c750/54) repointed; 0x1483c48 stays 0. All card hashes
  changed (validate/regression.py).
* **Checks** (`convert.py --four-looks --verify`, ALL OK): emu_chain; emu_card with 4 entries (lists, conversion
  engine for rows 10–13, name table copy + WB table untouched, icon tables, row maps, draw call); emu_look (Classic
  Chrome's look, peaking bytes); emu_extras: drawn names through the stock lookup + DRAW (glyphs = text), both
  recipes through the real message producer and exporter (exactly their 7 values, 12 other selections unchanged,
  3 WB modes, MODE_FSIM guard), Superia's colour mode through the real 3x3 / 2x2 / chroma-gain / tone functions
  (= ASTIA / PROVIA / PROVIA / PRO Neg. Std), every stock colour mode as on stock firmware, Classic Chrome still
  curve 38, peaking bytes from the real tuning hook.
* **Camera (user, 2026-11-17)**: rows 10–13 shown with names and icons, each selectable and kept; WHITE BALANCE menu
  normal; the four entries give four different pictures. Not yet checked: colour of each against its reference,
  focus-peaking strength, RAW CONVERSION of a recipe picture (gives the base look; there is no recipe row).
