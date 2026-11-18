# X-Pro1 menus: how they work, the full map, and what can be changed

State 2026-11-18. **Static analysis only** (official 3.82 firmware, no camera test in this session). Everything that
film-simulation work has proven on the camera is in `FINDINGS.md`; this file generalises it to every menu.
The complete generated tables (every page, item, setting, node, list, conversion table, storage bit field, screen
layout, hidden item, free bit) are in **[`MENU_MAP.md`](MENU_MAP.md)**, written by `tools/menumap.py`:

```
cd re && ~/.venvs/xpro1-re/bin/python tools/menumap.py        # needs work/ (setup_work.sh) and decompiled/*.c.gz
```

RAM addresses throughout (blob1 0x774000, blob2 0xe0ec80, module 0x41 0x1420000, module 0x44 0x15c0000).

## 1. Summary

A menu entry exists in **four places that must agree**. The film-simulation work touched all four:

| Layer | Where | What it holds | Changeable by |
|---|---|---|---|
| Menu tree | blob1 data 0x774000–0x77c000 | nodes {group, setting, widget, flag, parent, list}; a list = (value, child) pairs | data poke (live) / stage-B patch (card) |
| Settings | blob1 data 0x78a000–0x790000 + getter code | conversion table per setting (row → stored value → internal value); a bit field in the settings bank | data poke; capacity changes need getter/setter code |
| Screens | module 0x41 (code + data) | per screen kind: page layout, item records (title, icon, label tables), draw code with row caps | data / code patch at module-0x41 init (card) |
| Rules | blob2 code | which rows are greyed or hidden in which mode (`FUN_00f0f2c8`) | code patch (HOOK_B2) |

Plus the **consumer**: the code that acts on the internal value (pipeline, AF, display). A new option needs it to
understand the new value. That was the hard part for film simulations (FINDINGS §6c, §6d).

| What was mapped (2026-11-18) | Result |
|---|---|
| Menu tree | 241 nodes; 5 roots (MENU, Q, 3 small) + 12 pop-ups opened by code; 90 item IDs |
| Main menu | SHOOTING 5 pages × 7, PLAYBACK 2 × 7, SET-UP 3 × 7: every item named, its setting, list, table and storage known |
| Q menu | 16 items (+1 hidden), all named |
| Sub-screens | ISO AUTO, WB SHIFT / colour temperature, custom-setting editor C1–C7, mount adaptor (6 lenses), Fn button, display custom (OVF 15 / EVF 22 toggles), flash, MF assist / peaking, RAW CONVERSION, image search, photobook, date/time, sensor cleaning, file names |
| Settings | 506 IDs; 192 conversion tables; 269 storage fields (address, bits) parsed from the getter |
| Screen kinds (module 0x41) | 30 kinds; 22 with record arrays, all main menus aligned with blob1 |
| Hidden things | 4 always-hidden items, 12 settings with table rows no menu offers, free bits in the settings bank |

## 2. The menu tree (blob1)

**Node** (6 words): `{group, setting, widget, flag, parent, list}`. **List**: `(value, child)` pairs ending
`0x7ffffffe`. `child = 0` means a leaf value (or an action item on a page); a child pointer opens that node.

* **Pages** are nodes whose setting is **5**. Their list values are **global item IDs** (0–134); the child is the item's
  node. The same item ID means the same item everywhere (2 = FILM SIMULATION in the shooting menu and the Q menu,
  56 = LCD BRIGHTNESS in SET-UP and Q).
* **Setting nodes**: list values are **row numbers of the setting's conversion table**, in menu order (FILM SIMULATION
  `0,1,2,8,7,6,4,3,5,9`). One setting can have several nodes (main menu, Q menu, custom-setting editor, …).
* **Roots** (parent 0): main MENU `0x776b24` (values 86–90 → SHOOTING page node `0x779754`, 91–93 → PLAYBACK
  `0x775a3c`, 94–96 → SET-UP `0x7765ec`; one entry per page, all pointing at the same node), **Q menu `0x776214`**,
  ISO pop-up `0x77758c`, a reduced playback menu `0x777624` and an unknown root `0x7793c4` (setting 0x113),
  plus 12 parentless pop-ups (LANGUAGE at first start `0x77a27c`, settings 0x136/0x139/0x13a/0x149/0x14a/0x14b/
  0x12b/0x161/0x162, page items 97–99), all in `MENU_MAP.md`.
* **Widget** (word 2): 7 list, 5 slider (SHARPNESS/HIGHLIGHT/SHADOW/NR in the shooting menu; the Q menu uses 7 for
  the same settings), 6 sub-page, 2 two-field (WB SHIFT, FLASH SET-UP), 19 R/B grid, 10/11 11-step slider, 42 text
  entry (file name), 16 Q grid, 1 menu root, 3/8 other sub-pages.
* **Group** (word 0) groups related nodes (1 shooting, 3 playback, 5 set-up, 0x3c Q, 0x2e RAW CONVERSION, 0x2b
  custom settings, 0x2a display custom, …). It selects the node's row-rule function (§5); the engine also tests it
  in places (`*[0x9d1254] == 0x21`). The node → screen link is in code (each screen's draw function passes a
  fixed kind, §3).
* Menu engine (blob2): current node `[0x9d1254]`, cursor `[0x9d1258]`, row count `[0x9d16ac]` (`FUN_00f0eb98`
  counts to the end marker, cap 0xaa rows), row states at 0x9d1404.

## 3. Screens (module 0x41)

* **Screen kind** = first argument of the module-0x41 helpers. `FUN_01476b8c(kind, page, row)` returns the record
  index: byte at `layout + page·15 + row·2 + variant·0x60` (each page: count byte at −1, then 7 × (record, flag);
  variant `[0x12af4f8]` 0–3). `FUN_014796fc` / `0x1479630` return a record's fields, `FUN_01477318` its y position.
* **Item record** (24 bytes, per kind): `{item, title text ID, graphic 0xff000000|n, flag, label table A, label
  table B}`. Title text IDs are UI text IDs (`tools/uitext.py`); A/B are u32 text-ID tables, one entry per option, in
  menu order, packed against the next table (copy to extend; FINDINGS §6).
* **Alignment rule (verified for all three main menus):** a page node's list is in screen order, and the kind's
  layout lists the same items in the same order once the always-hidden items are skipped. Counts match exactly
  (SHOOTING 36 − 1 = 35 slots, PLAYBACK 15 − 1 = 14, SET-UP 23 − 2 = 21), and every pair agrees in value count and
  labels. So layout slot *k* ↔ the *k*-th visible list entry. **A page change needs both: the blob1 list entry and
  the layout byte.**
* Main kinds: **0 SHOOTING** (layout 0x1429d4a, records 0x142bcc8, 53 records incl. variants, e.g. ISO ×3, FLASH
  MODE ×9), **4 PLAYBACK** (0x142a03a / 0x142a4bc), **6 SET-UP** (0x142ce16 / 0x142fcd4). Sub-screens: 1 movie
  menu, 0xf image search, 0x15 custom-setting editor, 0x16/0x17 display custom, 0x1c RAW CONVERSION, 0x1d ISO AUTO,
  0x20 mount-adaptor lenses, 0x23 FS BKT films, 0x24 sensor cleaning, 0x27 MF ASSIST, 0x28 colour space.
  The Q menu's screen is not among them (open, §8).
* **Option labels** are drawn by per-menu code with **row caps** (film sim: `cmp r4,#9` at 0x147c748 and
  0x147c61c; WB name table cap 8). Other menus' caps are in the same functions (`FUN_0147c5dc`, `FUN_0147c7ac`:
  cases per kind, e.g. kind 0x1a WB 0x1483c48 cap 8, 0x18 0x1483bf8 cap 9, 0 0x1483968 cap 9, 1 0x1483990 cap 7).
  Extending any list past its cap needs that `cmp` raised (code, module-0x41 init hook).

## 4. Settings: conversion tables and storage

* **Conversion table** `0x78ba10[setting]` (506 entries): rows `{c0, c1, c2}` ending `{0xffff ×3}`; `0x7ffffffe` =
  none. Engine blob1 `0x78a9ec(setting, value, from, to)` (0 = row, 1–3 = c0–c2). Usually **c0 = stored value,
  c2 = internal value** for the consumer (FILM SIMULATION: c2 = MODE_FSIM; COLOR: c0 3/4/0/6/5, c2 7/8/0/10/9).
  Some tables have only c2 (RAW CONVERSION parameters: colour temperature 10000…2500 K, DR 100/200/400, …).
* **Storage**: getter `FUN_0078fb50(setting, bank, default?, slot)` (blob1; setter `0x793814`, wrapper `0x793048`).
  One switch case per setting, reading a bit field of the **settings bank** (bank 0 at 0x9caf00…, stride 0x12a).
  Image-quality settings are kept **per custom-setting slot** (byte + 7·slot, slots 0–6 = C1–C7; slot 7 elsewhere):
  FILM SIMULATION = 0x9cafef bits 7..4, WHITE BALANCE = same byte bits 3..0, COLOR 0x9cafec 7..5, SHARPNESS
  0x9cafed 7..5, SHADOW 0x9cafee 7..5, NR 0x9caff0 6..4, HIGHLIGHT 0x9caff1 5..3. `param_3 = 1` returns the default
  (table at `[0x791694]`). The parsed field of every setting is in `MENU_MAP.md`.
* **Capacity = 2^bits.** "spare" in `MENU_MAP.md` = stored values the field can hold that no row uses. Key ones:

| Setting | Field | Used | Spare stored values |
|---|---|---|---|
| FILM SIMULATION 0x3d (and FS BKT 0x3f–0x41) | 4 bits | 10 | 8, 9, 10, 13, 14, 15 (converter uses them, FINDINGS §11b) |
| WHITE BALANCE 0x130 | 4 bits | 10 | 10–15 |
| COLOR / SHARPNESS / HIGHLIGHT / SHADOW / NR | 3 bits each | 5 | 3 each (COLOR 1, 2, 7; others 5, 6, 7) |
| IMAGE QUALITY 0x3c | 3 bits | 5 | 5, 6, 7 |
| MOUNT ADAPTOR lens 0xa6 | 3 bits | 6 | 6, 7 |
| BACKGROUND COLOR 0x30 | 3 bits | 6 (+row 6 defined) | 7 |
| PLAYBACK VOLUME 0x19 | 4 bits | 11 | 11–15 |
| **MF ASSIST 0x110, PEAK level 0x111** | **1 bit each** (0x9caf5c b5, 0x9caf5b b7) | 2 | **none** |
| Fn BUTTON 0xd / second button 0xe | 4 bits | 16 | none |

* **Free bank bits** (no getter case reads them): e.g. 0x9caf24/26/2a/2b/2d/31 bits 7..5, 0x9caf36 bits 4..0,
  0x9caf38 bits 6..5, 0x9caf51/52 bits 4..0 (table in `MENU_MAP.md`). Caution: code that copies, resets or saves
  the bank as a whole is not covered. Check before using one.

## 5. Row states: greyed and hidden rows (blob2)

`FUN_00f0f2c8(setting, value, state)` sets the state of the row carrying `value` in the current node, if the node's
setting matches: **0 normal, 1 greyed, 2 hidden**. `FUN_00f1ff44` counts the rows, clears their states and then
calls one rule function chosen by the **node's group**:

| Group | Rule function | Menu |
|---|---|---|
| 1, 2, 0x3c, 0x46 | `FUN_00f12184` (param = group) | shooting menu, Q menu, flash set-up |
| 3, 4, 0x11 | `FUN_00f184b8` | playback menus |
| 5 | `FUN_00f10220` | set-up |
| 0x2e / 0x2b / 0x2a | `FUN_00f10140` / `FUN_00f11484` / `FUN_00f0f680` | RAW CONVERSION / custom-setting editor / display custom |
| 0x14, 0x2d, 0x33 | `FUN_00f0f850` | ISO AUTO |
| 0x35 / 0x36 / 0x44, 0x45 | `FUN_00f15fc0` / `FUN_00f113f4` / `FUN_00f1591c` | setting-0x113 root / mount adaptor / file names |
| 0, 9, 10, 0xb, 0x10, 0x12, 0x13, 0x1a, 0x1b, 0x1f, 0x20 | `FUN_00f0f3f0`, `00f103d8`, `00f10280`, `00f183f0`, `00f18474`, `00f1055c`, `00f0fe50`, `00f104d8`, `00f161e4`, `00f10508` | main root, date/time, language, image search, … |

Rules key on the shooting mode `[0x9cb300]` (0x1d, 0x29, …), flash, lens and similar. A new option that must be
greyed in some modes gets a call in its group's function (blob2 code: HOOK_B2 stub).

**Always hidden on this body** (the module-0x41 layouts have no slot for them):

| Item | Menu | Setting / node | Rule |
|---|---|---|---|
| 113 | SHOOTING, Q | 0x1a6, values rows 3, 2 (stored 1/0, internal 6/3), 1 bit 0x9caf57 b7 | `FUN_00f12184`, both branches |
| 79 | PLAYBACK | 0x16d (two on/off children 0x16e, 0x16f) | `FUN_00f184b8`, unconditional |
| 68 | SET-UP | 0x34, on/off, 0x9caf72 b2 | `FUN_00f10220`, unconditional |
| 134 | SET-UP | action item | greyed by `FUN_00f10220`; no layout slot |

These are probably features of other bodies sharing the code (the firmware also has a movie menu, internal-memory
copy and IR communication screens the X-Pro1 never shows).

## 6. The map at a glance

Full detail: `MENU_MAP.md`. Format: *page.row title (setting)*; † = item opens a sub-screen.

* **SHOOTING**. 1: ISO (0xf7)†, IMAGE SIZE (0x3a), IMAGE QUALITY (0x3c), DYNAMIC RANGE (0x42), FILM SIMULATION (0x3d),
  FILM SIMULATION BKT (0x3e → 0x3f/0x40/0x41)†, SELF-TIMER (0x67). 2: WHITE BALANCE (0x130 → WB SHIFT 0x4d, colour
  temperature 0x131)†, COLOR (0x48), SHARPNESS (0x49), HIGHLIGHT TONE (0x4a), SHADOW TONE (0x4b), NOISE REDUCTION
  (0x39), LONG EXPOSURE NR (0x15). 3: SELECT CUSTOM SETTING (0xa3), EDIT/SAVE CUSTOM SETTING (0x92 → 0x93: 0xa2,
  0x94–0xa1)†, AF MODE (0x64), CORRECTED AF FRAME (0x35), MOUNT ADAPTOR SETTING (0xa6 → 0xa7: 0xa8–0xab, 0xb2, 0xba,
  0xed)†, SHOOT WITHOUT LENS (0xf4), FUNCTION (Fn) SETTING (0xc → 0xd, 0xe)†. 4: MULTIPLE EXPOSURE (0xf5), DISP.
  CUSTOM SETTING (0x6a → EVF/LCD 0x6b: 0x6c–0x81, OVF 0x82: 0x83–0x91)†, FRAMING GUIDELINE (0x69), AF ILLUMINATOR
  (0xa), AE/AF-LOCK MODE (0xf), AE/AF-LOCK BUTTON (0x10), AUTOROTATE PB (0x1a). 5: FLASH SET-UP (0x65 → FLASH MODE
  0x144, FLASH COMPENSATION 0x66)†, RED EYE REMOVAL (0x8), SAVE ORG IMAGE (0x9), IS MODE (0x1ae), APERTURE SETTING
  (0x10e), MF ASSIST (0x110 → PEAK 0x111)†, AF+MF (0x112).
* **PLAYBACK**. 1: RAW CONVERSION (0x14e → 0x150–0x15d)†, ERASE (0x168), CROP (action), RESIZE (0x173), PROTECT
  (0x16c), IMAGE ROTATE (action), RED EYE REMOVAL (action). 2: SLIDE SHOW (0x14d), PHOTOBOOK ASSIST (0x15f)†, MARK FOR
  UPLOAD TO (0x169), IMAGE SEARCH (0x163 → 0x164–0x167)†, PRINT ORDER (0x16b), DISP ASPECT (0x174), PLAYBACK VOLUME
  (0x19).
* **SET-UP**. 1: DATE/TIME (0x24 → 0x25–0x2a)†, TIME DIFFERENCE (0x2b → 0x2c: 0x2d–0x2f)†, LANGUAGE (0x1f), RESET
  (action), SILENT MODE (0x20), FRAME NO. (0x7), FOCUS RING (0x12). 2: LCD BRIGHTNESS (action; Q uses node 0x128),
  POWER SAVE MODE (0x22), QUICK START MODE (0x23), AUTO POWER OFF (0x21), OPERATION VOL. (0x16), IMAGE DISP. (0x6),
  SENSOR CLEANING (0x36 → 0x37, 0x38)†. 3: COLOR SPACE (0x14), GUIDANCE DISPLAY (0x31), FOCUS SCALE UNITS (0x13),
  BACKGROUND COLOR (0x30), PREVIEW EXP. IN MANUAL MODE (0x1b), EDIT FILE NAME (0x1a1 → 0x1a2, 0x1a3)†, FORMAT (action).
* **Q MENU** (node order): SELECT CUSTOM SETTING (0xa3, 8 values: BASIC + C1–C7), [hidden 0x1a6], ISO, DYNAMIC
  RANGE, WHITE BALANCE, NOISE REDUCTION, IMAGE SIZE, IMAGE QUALITY, FILM SIMULATION, HIGHLIGHT TONE, SHADOW TONE,
  COLOR, SHARPNESS, SELF-TIMER, AF MODE, FLASH MODE (0x144), LCD BRIGHTNESS (0x128). Separate nodes from the main
  menu (e.g. film sim Q node 0x779ffc vs main 0x77a544) on the same settings.
* **Copies of the image settings** that a new option must also reach: Q nodes; custom-setting editor 0x94–0xa1
  (C1–C7, kind 0x15); RAW CONVERSION 0x150–0x15d (own tables, c2 only); FS BKT 0x3f–0x41.

## 7. How to change things (recipes)

Rules from the camera owner apply to every step (FINDINGS §9.1): RAM only (USB live test, then SD card); results
from USB reads, EXIF or photos, never LEDs; before a live test say what the user will see and undo it afterwards.

**a) Reorder or remove options of a setting.** Data only: copy the list with the new order and repoint the node's
list word (+0x14). Do it for every node of the setting (main, Q, custom editor). **Label tables are indexed by
list position, not table row** (FILM SIMULATION's name table 0x1483c20 runs PROVIA, Velvia, ASTIA, Neg Hi, Neg Std,
MONO, +Ye, +R, +G, SEPIA = list order of rows 0,1,2,8,7,6,4,3,5,9), so every A/B table of the item's records and
the draw code's own tables must be reordered the same way. Check by selecting a row and reading the stored value
over USB.

**b) Offer a table row that already exists** (§8 list, `MENU_MAP.md` "Table rows defined but not offered"). Append
the row number to the list (copy + repoint). Then the label: the new list position has no label-table entry, so
the row is likely blank, or shows whatever word follows the packed table (the WHITE BALANCE slip, FINDINGS
§12.3 a); copy the tables with an extra entry and raise the cap (§3). Then check what the consumer does with the
internal value. One live poke shows whether the
camera accepts it.

**c) Add a new option** (worked example: Classic Chrome, `ADDING_FILM_SIMS.md`, converter `features/menus.py`):
1. a spare **stored value** in the field (§4), or widen the field (getter + setter case: code);
2. a **conversion row** {stored, –, internal} (use an empty row or copy the table and repoint 0x78ba10[setting]);
3. the row number in **every node's list**;
4. **labels**: an entry in each record's A/B tables (copy, repoint the record fields) and the draw function's cap;
   text via a repointed unused text ID or a drawn string (converter `features/texts.py`, `menus.py` DRAW stub);
5. **row rules** if the option must be greyed in some modes;
6. the **consumer** for the new internal value (the bulk of the work; trace it live with `tools/fsimlog.py`, FINDINGS §9.5);
7. the copies listed at the end of §6, and EXIF if the setting is written to files.

**d) Change what an existing option does.** Keep the menu, change the consumer's data: tuning bytes through the
cchook tuning hook (e.g. focus peaking HIGH in PR #3, `features/peaking.py`), or remap c2 in the conversion table.
Cheapest and safest kind of change; only the label stays wrong (rename with `features/texts.py`).

**e) Rename an item or option.** Text IDs are shared by all screens that use them; repoint the descriptor in each
of the 35 language blocks (`tools/uiname.py`, `uitextmark.py` live; `features/texts.py` on the card).

**f) Move, replace or add a main-menu item.** Replace: change the item ID in the page list *and* the record byte in
the module-0x41 layout (same slot). Moving within a page is the same pair of edits. Adding needs a free slot: every
page is full (7 rows), so a new page is needed, i.e. a layout page with a count byte, a new main-root value
(86–96 are taken; the root list must grow) and whatever code fixes the page count (not found yet). Free item IDs
(not in any list or row rule): 24, 25, 28, 34, 37, 40, 43, 49, 50, 53, 54, 65, 82, 100–105, 107, 110–112, 117–124,
126–128, 135+ (other uses of item IDs not checked).

**g) Unhide a hidden item.** Remove its `FUN_00f0f2c8(…, 2)` call (blob2 code, HOOK_B2) *and* give it a layout slot
(f). Without a slot the cursor and the drawn rows go out of step.

## 8. Research: candidate adjustments

Ranked by value for this project and how much is already known. "Live test" means a RAM poke over USB with
the debug firmware, undone by `restore` or a power cycle.

| # | Adjustment | What the map shows | Feasibility / first step |
|---|---|---|---|
| 1 | **Focus peaking: more levels** (TODO, user 2026-11-17) | MF ASSIST 0x110 {STANDARD, PEAK} and PEAK level 0x111 {LOW, HIGH} are **1-bit fields** (0x9caf5c b5, 0x9caf5b b7); that byte has no free bit. Table 0x111 {1,–,1} {0,–,2}: internal 1 / 2. Screen kind 0x27 (MF ASSIST) | A third level needs a wider field: widen getter/setter case 0x111 into a free bank bit (e.g. 0x9caf36 b4..0, check other users first), a third row + list entry, a label and cap, and the consumer path internal level → `FUN_010bfa6c` (levels 4/5 → sets 0xc87d / 0xc88b). **Cheaper alternative: keep two levels and retune them** (d), e.g. LOW = today's HIGH and HIGH = stronger. First step: trace 0x111 → picker live (`fsimlog.py`, toggle LOW/HIGH) |
| 2 | **Highlight / Shadow beyond ±2** (NOTES 2026-11-12 "Highlight / Shadow tone mapped") | 3-bit fields, 5 used → **3 spare stored values each**; 5-row tables (no empty row → copy); shooting widget = slider (5), Q = list; labels in records 14/15 A/B (5 entries, packed); RAW CONVERSION (0x15b/0x15c) and custom editor (0x9f/0xa0) are separate copies | Menu side feasible (c); the slider's 5 positions may be fixed in draw code (unknown). Simpler: remap the existing 5 positions to wider tone curves (NOTES "route 1"), no menu change |
| 3 | **COLOR / SHARPNESS / NR extra steps** | same 3-bit pattern, 3 spare each; COLOR's c2 is 0, 7–10 | same as 2; consumer = tuning lookup by internal value |
| 4 | **Seventh BACKGROUND COLOR** (menu colour theme; relates to the green UI work) | table row 6 {6,–,–} exists, list offers 0–5; field 3 bits | **Cheapest test in the map**: live, copy list 0x77741c with row 6 appended, repoint node 0x778864 → SET-UP's BACKGROUND COLOR list shows a 7th row (no label entry: blank, or the next packed table's first word); select it, read 0x9caf23 over USB (bits 7..5 = 6?) and look at the menu colours. Undo: power cycle. Visible side effect: that extra row only |
| 5 | Other defined-but-hidden options | FRAMING GUIDELINE row 2, Fn row 4 (stored 3) / second button row 4, FLASH MODE row 9, SLIDE SHOW rows 5–6, IMAGE SEARCH row 2, ISO rows 0–4 (stored 20–24, internal 1–4, 28), ISO AUTO default row 16, AF MODE row 4 | Same one-poke test as 4 each; identify by what the camera does. ISO rows: only after reading the consumer (sensor settings) |
| 6 | Film simulations in **FS BKT** and the **custom-setting editor** | FS BKT: settings 0x3f–0x41, own 4-bit fields (0x9caf69 b7..4, 0x9caf67), tables with an empty row 10, labels 0x142ac5c / 0x14275b0 (cap 9 in 0x143dfa8); editor: node 0x779d4c (setting 0x9a, no own table), kind 0x15 | Same recipe as the shooting menu (FINDINGS §12.2 "not yet"); next converter modules |
| 7 | **Q menu**: own slot layout, film-sim icon | 17 nodes (16 + hidden); the Q screen kind is not in the module-0x41 kind switch | Find the Q draw function (screen table 0x1430190; Q group 0x3c) to see where its icons and layout come from |
| 8 | Fn button: new function (e.g. cycle the new film simulations) | 4-bit field, 16 rows all used (row 4 hidden); labels via table 0x1429e7c | Needs the Fn dispatcher (not mapped); row 4 is the natural slot |
| 9 | Unhide items 113 / 79 / 68 | functions unknown; no layout slots | Low value; only with (f) |

## 9. Open questions

* Which code decides the page count of a menu (needed to add a page)? And what `[0x12af4f8]` (layout variant 0–3) is.
* Where the Q menu is drawn and how its 4×4 slots are assigned.
* Names of the parentless pop-ups (settings 0x136, 0x139, 0x13a, 0x149–0x14b, 0x12b, 0x161/0x162; items 97–99) and
  of setting 0x113's root (eight single-value children 0x114–0x11b). Likely shooting-screen buttons (photometry,
  drive, AF area); confirm by reading `[0x9d1254]` over USB while each is open.
* The setter `0x793814`: confirm it mirrors the getter's fields (needed before widening a field).
* EVF/LCD display-toggle names (0x6c–0x81, 22 toggles; the OVF list's names are assumed from kind 0x16's records).
* Everything in this file is static. Cheap camera confirmations: read 0x9caf5b over USB with PEAK LOW vs HIGH
  (bit 7 should flip), and the BACKGROUND COLOR row test (§8 #4).
