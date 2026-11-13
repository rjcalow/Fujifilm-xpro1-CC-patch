# Adding new film simulations to the X-Pro1: findings

Goal: add film simulations (Classic Chrome first) as **extra menu entries**, keeping all ten stock ones.
State 2026-11-13. Nothing here is flashed. Camera tests were RAM-only: live over USB (debug firmware `ptpdebug_385`)
and then from the SD-boot card `build/sdchain_cc11_green/` (§6b), which works on the camera.
Addresses are RAM addresses (blob1 loads at 0x774000, blob2 at 0xe0ec80). Session detail: `NOTES.md` (2026-11-12 night onward).

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
| Other menus (Q menu, bracketing, RAW conversion, custom settings), EXIF | Lists located, not patched (§3, §7) |

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

## 7. Still to do

1. Camera check of the own look (§6c): photos CLASSIC CHROME vs PRO Neg. Hi vs PROVIA vs SEPIA, same scene;
   CLASSIC CHROME should match what PRO Neg. Hi gave on v2, PRO Neg. Hi should be Fuji's original again.
2. Check a photo's EXIF (Ver3.89, film mode).
3. Other places a film sim appears: Q menu, film-simulation bracketing (nodes/tables 0x3f–0x41), RAW conversion
   (0x152?), custom settings (0x9a?), shooting-screen indicator (1058 group), EXIF FilmMode for MODE_FSIM 6 (0x600).
4. What a flash boot does with saved value 13 (and where the active setting copy is stored).
5. Flash only when complete; until then the SD card.

## 8. Tools added

| Tool | Use |
|---|---|
| `tools/uitext.py` | print UI text by ID, any language |
| `tools/fsimslot.py` | live 11th-row test: `apply` / `restore` / `status` (row, name, icon tables, row maps, one code poke) |
| `tools/fsim11.py`, `build_sdchain.py --fsim11` | the same changes on the SD-boot card |
| `tools/emu_fsim11.py` | emulator test of the card's hooks (real firmware code) |
| `tools/fontswap.py` | live: load the X-E2 font in RAM (research; not needed for the icon) |
| `tools/cclook.py`, `build_sdchain.py --cclook` | own look data for colour mode 1 + PRO Neg. Hi restore: live `apply` / `restore` / `status`, and the card |
| `tools/emu_cclook.py` | emulator test of the look patches (tuning hook, HOOK_B2, real pipeline selection functions) |
| `tools/uitextmark.py` | live: label text IDs with "#ID" to see what a screen draws; `restore` removes them |
| `decompiled/xpro1_blob1_0x774000.c.gz`, `xpro1_mod41_0x1420000.c.gz` | X-Pro1 blob1 and module 0x41 decompiles (Ghidra 12.1.4 + JDK 21 in `~/opt`) |
