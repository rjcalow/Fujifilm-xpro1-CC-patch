# SD dual boot: failure log (read before trying anything)

**Goal:** boot a modified X-Pro1 firmware from the SD card **without writing the camera's flash**.
Every attempt below failed. Each has a cause and a rule, so it isn't repeated. Details and addresses are in
`NOTES.md` (sessions 2026-11-06 to 2026-11-09).

**Status (2026-11-11): SD DUAL BOOT WORKS.** Card `re/build/sdchain_poweron/` (ffboot e7af6d5a…) boots the firmware
from flash through our chain stub with RAM patches applied: screen came on by itself, and the running firmware's RAM
holds the Ver3.89 marker (blob1 0x857a98 = 0xe3a03039, read over USB). Root cause of every earlier "dark screen":
E25 / F21 below. **EXIF confirmed:** DSCF2758 (JPG + RAF, 2026-11-11 12:39) Software = "Digital Camera X-Pro1 Ver3.89" (rule 5 met).

## Established facts (proven on the camera; build on these)

| # | Fact | How it was proven |
|---|---|---|
| E1 | SD boot trigger = **Fn + press the command dial**, held at power-on after taking the battery out and back in | LED stub lit the green LED (2026-11-07). Found from the firmware key map: GPIO 0-10 (Fn) + 0-11 (dial press), the same lines the X-E2 and X-T1 use |
| E2 | Card must be **FAT32**. Copy, `sync`, **verify checksums**, unmount (don't power off the reader) | F2, F17 |
| E3 | The boot ROM loads `ffsys.bin` (stock param block, word +0x10 = 0x301) and `ffboot.bin` (≤ 64 KiB) and runs it | E1 |
| E4 | The boot ROM leaves an **asynchronous abort pending**. Code must drain it before the stock loader unmasks CPSR.A | Crash report decoded (F9), then ORANGE×2 drain signal (F10) |
| E5 | With the drain, our chain stub runs the **whole stock boot loader**: every start-up step and every main step (section table, all sections from flash). The loader then jumps to section 0 (entry 0x40020) | Trace video decoded (2026-11-08) |
| E6 | The firmware's EXIF "Software" text is built by blob1 0x8579e8 (called from the modules code), so a patched "Ver3.89" there is a valid test of what produced a photo | Static: modules 0x151aa34 / 0x163cbd8 / 0x161008c |
| E7 | **After a failed SD boot, pressing the shutter starts a normal boot from flash.** The screen coming on proves nothing. Photos taken then are from the flash firmware (Ver3.82) | F12–F14 |
| E8 | **Boot order:** mask boot ROM (not in the update file) → stock loader at 0 → **section 0** (0x40000, entry 0x40020; the loader passes blob1's entry 0x8554c4 in r0) → section 0 main 0x40b64 calls **blob1 once per start-up phase** (`blx r4`, phase 0 at 0x40bac, then 1, 3, 2) | Static (loader 0x468c / 0x4740, section 0 0x40b64) + F14 |
| E9 | **blob1 is unpacked in the background** (loader 0x4b94 starts a hardware transfer and may not wait), so blob1 cannot be patched at the loader's final jump; patch it just before section 0 first calls it | Static + F12 |
| E10 | The ROM's file functions (`open` / `read`) hang when called from our code: loading anything beyond `ffboot.bin` (≤ 64 KiB) must not use them | F5, F6 |
| E11 | Updater: a file is accepted only if its header version (0x204 major / 0x208 minor, outside the checksums) is **newer than the built-in 3.82**. Label builds 3.83. Official files cannot downgrade or re-install; rollback = stock firmware relabelled | Static (blob1 0x857af0, blob2 0xee5010) + camera |
| E12 | Colour (flash v2, working): the v1 port missed the chroma-gain preset (ID 0xe4ec, up to ×1.15 on reds); v2 fixes it; in-camera RAW conversion uses the patched tuning; the camera still reports Ver3.82 | Same-RAW comparison DSCF2723 vs DSCF2743 |
| E13 | CPU speed: ~13 MIPS at the ROM's clock; ~14× faster once the loader enables the caches. Busy-wait delays must account for both | Trace video timings |

## Failures

| # | What was tried | What happened | Why it failed | Rule |
|---|---|---|---|---|
| F1 | Flash v2 labelled 3.82, then 3.83 | "LATEST FIRMWARE" | Card still held the old v1 file. 3.82 is never newer than the built-in 3.82 | Check the card's file (sha / `xxd -s 0x204`) before every flash. Label ≥ 3.83 |
| F2 | SD boot on the first cards | Nothing | Files were **0 bytes** (copy never flushed); then the card was **exFAT** | E2 |
| F3 | Shutter + UP (service-manual "BOOT mode"); shutter + Fn; shutter + other keys | No SD boot (blank screen / nothing) | Wrong input lines. The manual's mode is a USB/jig mode | Use E1 only |
| F4 | fujimod EXR loader + `ffuser.bin` (full RAM image via the ROM file API) | Blank, no sign of life | Hangs inside the ROM (see F5/F6) | Don't use fujimod's EXR loader |
| F5 | Own loader using the ROM file API, code and stack in SRAM 0xfff00800 | LED on → off: **stuck inside ROM `open()`** | ROM file API (0x80001a74 open / 0x80001b38 read; fujimod's untested EXR ABI) does not return | — |
| F6 | Same, code and stack in high DRAM (no SRAM writes) | Still stuck in `open()` | SRAM corruption was not the cause. The ROM file API is unusable as documented | **Abandon `ffuser.bin` / ROM-file-API loading** |
| F7 | Chain boot: `ffboot.bin` carries the stock loader (deflate), inflate to 0, jump | Loader never reached its main | Root cause found later (E4) | — |
| F8 | + D-cache clean, MPU/caches off before the jump | Same | Not the cause (kept anyway: correct hand-over) | — |
| F9 | + IRQ/FIQ masked before the jump | Crash report: data abort at checkpoint 1, in the loader's mode setup | Pending ROM abort (E4) | — |
| F10 | + drain the pending abort | Loader runs completely and jumps to section 0 | **Fixed** | Keep the drain |
| F11 | Trace build (checkpoint blinks, firmware started 72 s after power-on) | Screen dark | Not timing (F12 had no delays) | — |
| F12 | Quiet build + RAM patch at the loader's final jump (Ver3.89 marker) | Dark. Shutter → screen on, photos **Ver3.82** | Patch skipped (blob1 still unpacking at that point), and (F14) the firmware never ran | Never judge by "screen came on" (E7) |
| F13 | Two-stage hook (patch just before section 0 first calls blob1) | Photo Ver3.82 | See F14 | — |
| F14 | Same with LED feedback | Stage A ran (orange), **stage B never ran**. Photo DSCF2751 Ver3.82 | **Section 0 never reaches its first call into blob1 (0x40bac): the SD-booted firmware dies in section 0's own start-up** | See "Where it stands" |
| F15 | SD-card log | Not possible yet | ROM file API hangs (F5/F6, now explained: E23); the SD controller **is** standard SDHCI (E22; earlier note was wrong); the firmware's own hang log needs a running firmware | Don't plan around an SD log until a driver exists |
| F16 | Reading LED blink counts by eye | Ambiguous every time | — | Superseded by F19: no LED tests at all |
| F17 | `udisksctl power-off` on the card reader | Built-in reader vanished until reboot | — | `udisksctl unmount` only |
| F18 | Section-0 exception reporter card (ffboot 57dae4c0…, `--sec0trap`) | Stub flicker → stage A ORANGE → nothing: **no exception report, no stage B**. Shutter → flash boot, DSCF2752 Ver3.82 | Section 0 stops **without a CPU exception** (all its vectors were trapped). Left: a stalled bus access (VIC 0xfffb3xxx is the only device it touches), or power cut / reset | — |
| F19 | Checkpoint card (ffboot aa2865e8…, `--sec0cp`: green ×k + orange per routine) | "A lot of green and red", no video; unreadable | Repeated P4: another blink-count test | **No more LED tests.** On-camera results must be EXIF or data read on the PC |
| F20 | Idea: leave a patched blob1 in DRAM with the warm flag (0x400a00fc) set, let the shutter-triggered flash boot skip the blob1 reload | Not built: ruled out statically (2026-11-09) | The stock loader's reset entry 0x4000 **clears 0x400a00fc first**, so its skip at 0x46ec never fires after a restart. Also the section-table read (0x4668) copies a whole 128 KiB block to 0x770000, zeroing blob1's first 0x1c000 bytes on every boot. main's flash-free branch (r5 != 0) is just core 1 | No DRAM-persistence tricks through the stock flash loader |
| F21 | Breadcrumb card (ffboot f0b41d31…, 2026-11-11) | Stub flicker seen; after shutter restart the block was pure 00/ff stripes | The firmware powered the camera off (E25), which wipes DRAM (E26). F14/F18 "section 0 never reaches blob1" was a misreading of LEDs by eye | Before theorising about a hang, check what the next stage does with its inputs; a clean power-off is not a hang |

## Process failures (how the work went wrong)

These cost more camera rounds than any technical problem.

| # | Failure | Example | Rule |
|---|---|---|---|
| P1 | **Trusted unverified sources** | Built on fujimod's EXR file-API ABI, which was never tested on hardware for this ROM generation | Treat external recipes as hypotheses; check what has actually been tested on a camera before building on it |
| P2 | **Assumed instead of checked** | Said the 3.83 file was on the card without looking (it held v1); placed the Ver3.89 marker before checking where the EXIF text comes from; patched at the loader's jump before learning section 0 sits between loader and firmware | Verify every premise in the code or on disk before a camera test |
| P3 | **Treated a working camera as success** | "Screen came on after the shutter" read as progress; it was a normal flash boot each time | Success = EXIF "Ver3.89" (or another marker that only the patched firmware can produce), nothing else |
| P4 | **Designed signals the user could not read reliably** | Blink counts by eye, ambiguous in most rounds; video decoding came five attempts too late | Any on-camera result must be machine-readable (EXIF marker, decoded video) or a single unambiguous yes/no |
| P5 | **Used the camera when the firmware had the answer** | Boot order, blob1 background unpacking and the EXIF text source were all readable from the code | Static analysis first; the camera only answers questions the code cannot |
| P6 | **Operational slips** | Powered off the card reader; kept tools and the Python venv in scratch folders that got wiped (twice) | Unmount only; tools in the repo (`re/tools`, `re/sdchain`), venv `~/.venvs/xpro1-re`, extracted files `re/work/` (`sh re/tools/setup_work.sh`) |
| P7 | **Kept probing a black box** | Five LED rounds on section 0, while the actual unknowns all sit in the 16 KiB boot ROM, which we can't read | Get the boot ROM (dump or facts) before any more SD-boot hand-over experiments |

## Working rules (from the failures above)

1. Read this file before any SD-boot attempt.
2. Static analysis first. Use the camera only for questions the code can't answer.
3. Each camera test states **one question** and has a result that can't be misread.
4. Before every test: check the files on the card (sha256, header bytes), FAT32, unmount (not power-off).
5. Claim success only when a photo's EXIF says **Ver3.89**.
6. On-camera results must be machine-readable: EXIF, or data read over USB. **Never LED blink patterns** (F16, F19).
7. No more SD-boot hand-over experiments until the boot ROM can be read (P7).

## Static facts (code + emulation, 2026-11-08/09; not camera-proven)

| # | Fact |
|---|---|
| E14 | Section 0 entry → 0x40bac **never polls hardware** and keeps IRQ/FIQ masked. Its only device accesses are the interrupt controller 0xfffb3xxx (0x43fc0/0x4307c: 95 vector slots + priorities; 0x40d40 enables source 0x5a). Everything else is DRAM. No unaligned access, VFP or SVC; nothing writes the loader area (hook code at 0x9000–0xb000 is safe) |
| E15 | **Every exception before 0x40bac is a silent hang**: section 0's vectors go to 0x40dd0, which saves registers at 0x4004d7ac and spins at 0x40e60 while [0x4004d7a0] == 0 |
| E16 | Loader MPU setup 0x41e8 writes **regions 0–3 only** (region 4 on core 1), ORs M/C/I into SCTLR, never touches other regions or BTCM. Boot-ROM leftovers there survive our stub |
| E17 | Loader 0x4f58 copies all GPIO inputs to 0x400a0000–0x400a0040 (the firmware's power-on keys; in SD boot it sees Fn + dial press) |
| E18 | **WRONG (see E25)** ~~Power stays on after an SD-boot hang~~: power hold = 0xfff88084 bit 0, set in loader system init (0x50b8), cleared only by the loader error handler 0x450c |
| E19 | **Warm flag 0x400a00fc is cleared by the loader's very first instruction** (reset entry 0x4000), so its blob1-skip at 0x46ec never fires after a restart. It is set only by blob2's in-place standby wake (0x10ae5fc). The section-table read copies a full 128 KiB block to 0x770000 (zeroes blob1's head every boot). Loader main's flash-free branch is core 1 only |
| E20 | fujimod's EXR II ROM facts (their X70 SD dual boot works): the ROM has a separate **mount** routine and the filesystem pointer at 0xfff00000 is **0 when ffboot starts**. Our loader (F5/F6) read that pointer without mounting: a likely cause of the `open()` hang. Our ROM's mount address is unknown (fujimod has the EXR ROM's sha256 7dc7e332…, not its image) |
| E22 | **Boot ROM dumped over USB** (2026-11-10, sha256 7dc7e332… = fujimod's). Its SD path touches only the SDHCI controllers 0xfff44000/0xfff45000 and its own SRAM; clocks, PLL, interrupt controller, MPU and DRAM are set up by the same routine (0x8000024c) from the same parameter block on both paths. NOTES 2026-11-10 |
| E23 | **F5/F6 explained:** the ROM's sector read sends whole 512-byte sectors by SDMA when the destination is in DRAM, ignoring offset/length; `open()` searches the directory with buffers on the caller's stack. F6's DRAM stack was overwritten; F5's stack (0xfff01ff8) was outside the 4 KB SRAM. The file API works when the stack is in SRAM below 0xfff00f00 |
| E24 | **Live tuning over USB works** (2026-11-11): RAM parameter area 0x40d3b580 + ID; a POKE survives unplugging and changes the next in-camera RAW conversion (ID 0xe4ec 1 → 2 reproduced v1's colour exactly: ×1.000 vs v1, ×1.048 vs v2). This achieves dual boot's purpose (try changes without flashing) for tuning data |
| E25 | **Root cause (camera-proven 2026-11-11).** blob1's start-up task 0x85505c decides the power-on cause from the loader's GPIO snapshot (0x400a0008 = port 2, **bit 11**), the live POWER switch (port 2 bit 10), live port 0 bit 2 and a state nibble (0x85ea2c(5)); an invalid cause → 0x7a65fc clears power hold 0xfff88084 = **hard power-off**. Port 2 bit 11 is 1 only briefly after power-on (flash boot: snapshot 0xdd40, live 0xd540). The SD chain reaches the loader seconds later → cause 0x26 → power-off; a shutter press then cold-boots from flash. Section 0 never hung; the firmware always started. Fix: at the loader's final jump set snapshot port 2 bit 11 and port 0 bits 10/11 (`crumbs.py` PRE) |
| E26 | Power states: switch OFF/ON keeps DRAM (marker 100 % intact); battery out 10 s or power hold = 0 (POKE 0xfff88084 0 over USB) wipes it to 00/ff stripes. DRAM 0x43f00000 is **not** untouched: taking a photo overwrites it with image data, so breadcrumbs must be read before shooting |
| E27 | **UI colours (camera-proven 2026-11-11).** The UI resource DB (RAM 0x130000, file 0xc8025c) holds 2178 GVFF vector graphics; colours are records `00 1b 00 00` + RGBA float32 (6850 records). The live RAM copy equals the file and is what the UI draws from: POKEs take effect at once. Changing only pure red (1,0,0) recoloured the shooting-screen info, not the menu; the crimson pair (207,61,84)/(148,31,84) did nothing visible; **swapping R and G in every record turned the menu accent green** (`uicolor.py swaprg`). Display memory can't be read for the menu: USB mode redraws the screen |
| E28 | **Data the firmware reads from flash after start-up must be hooked where it is read, not patched at stage B** (2026-11-12). Tuning area: start-up load blob1 0x858394 (called from 0x8550d4) and reload 0x857e44; language block: 0x86334c. The first `--cc` card hooked only the reload and its conversion DSCF2759 still had the v2 values; with the start-up hook DSCF2763 has v3 (`ccfit.py`). Verify a hook with a same-RAW conversion, not with a live USB poke (the live rename had masked this) |
| E21 | USB PTP dispatcher blob2 `FUN_00f4521c`: high byte of the opcode → table (0x10xx 0xf4c028, 0x90xx 0xf4c09c, 0x98xx 0xf4c114), low byte → index. Vendor slots 0x9010–0x9012 are free ("not supported" 0xf4bff0). Full protocol in NOTES 2026-11-09 |

## Where it stands

**Superseded 2026-11-11: solved, see Status, E25, E26 and F21.** The text below is the pre-solution picture (its
"section 0 stops" premise was wrong) and is kept only as history.

* **Works (camera):** ROM loads `ffboot.bin` with Fn + dial press (E1); our stub drains the ROM's pending abort (E4) and
  the whole stock loader runs and jumps to section 0 (E5); stage A hook at the loader's final jump runs (F14, F18).
* **Fails:** section 0 stops between its entry and the first blob1 call (0x40bac). Not a CPU exception (F18: all
  vectors trapped, no report). It touches only the interrupt controller there (E14) and power stays on (E18).
* **Ruled out:** LED diagnostics (F19), DRAM persistence through the stock flash loader (F20). The ROM file API is
  **not** broken: F5/F6 called it with an unusable stack (E23).
* **Learned from the ROM dump (E22, E23; `re/work/rom/`, NOTES 2026-11-10):** both boot paths set up clocks, PLL,
  DRAM, MPU (regions 0-1 only, overwritten by the loader) and the interrupt controller in the same routine from the
  same parameter block. The SD path adds only SDHCI controller 0xfff44000. So the ROM does **not** leave the
  interrupt controller differently configured; the "unclocked block" theory has no support in the ROM.
* **Still open:** (1) SDHCI 0xfff44000 left active after the SD read (e.g. a pending interrupt or SDMA state);
  (2) the source of the pending asynchronous abort (E4); (3) timing: the SD chain starts the firmware seconds later
  than a flash boot (sub-MCU / power-controller deadline?). Next SD card idea, judged by EXIF only: in the stub,
  reset SDHCI 0xfff44000 (software reset register +0x2f, standard SDHCI) and clear its interrupt status before the
  hand-over, and shorten the time to hand-over.
* **Next SD experiment (2026-11-11): breadcrumb card** `re/build/sdchain_crumbs/`: progress, hardware snapshots and
  exceptions written to DRAM 0x43f00000, read over USB after the shutter restart (`sdcrumbs.py`). No LED reading.
* **Changed priorities (2026-11-11):** tuning experiments no longer need SD boot: RAM parameter edits over USB take
  effect live (E24, `re/tools/tune.py`). SD boot now matters only for testing code changes without flashing.

## Done: boot ROM read over USB (debug firmware flashed 2026-11-10)

`re/build/ptpdebug_385/FPUPDATE.DAT` (label 3.85, sha256 64f7d923…): Classic Chrome v2 + three PTP vendor operations
added to blob2 (405 bytes; `re/tools/build_ptpdebug.py`): 0x9010 PEEK, 0x9011 POKE, 0x9012 CALL. Emulated through the
real dispatcher (`re/tools/emu_ptpdebug.py`, 11 checks), file decodes to v2 + patch, checksums verified, blob1 and all
other regions identical to v2. PC client `re/tools/ptpdebug.py` (pyusb). Rollback = reflash v2 (3.83).
**Done 2026-11-10: flashed, PEEK works, ROM dumped (sha256 matches fujimod).** Steps:
1. Flash it (DISP/BACK + power on; check `xxd -s 0x204 -l 8` = `0300 0000 8500 0000`).
2. `ptpdebug.py info` → "debug PEEK: works".
3. `ptpdebug.py dumprom rom.bin` → 16 KiB; compare sha256 with fujimod's 7dc7e332….
4. Static analysis of the ROM: SD-boot path (what it sets up and leaves behind), mount + file API (E20), source of
   the pending abort. Read live registers (interrupt controller, clock/reset blocks) over USB in a normal boot to
   compare with what an SD boot would need.
5. Only then design the next SD card, and judge it by EXIF only.

Zero-risk alternative (user's call): ask fujimod's maintainer for the EXR ROM image or its mount/command-table
addresses.

## Archive: diagnostic cards built for section 0 (results F18, F19)

* `re/build/sdchain_sec0trap/` (ffboot 57dae4c0…): `sec0_trap.py` points section 0's vectors at an LED reporter until
  stage B and restores them there. Result F18.
* `re/build/sdchain_sec0cp/` (ffboot aa2865e8…): + `sec0_cp.py` per-routine LED checkpoints. Result F19 (unreadable).
* Both emulated with `re/tools/emu_sec0_trap.py [--cp]`; decoding `led_video.py --layout sec0`. Kept for reference
  only (rule 6).
