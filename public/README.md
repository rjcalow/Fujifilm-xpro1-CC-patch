# Classic Chrome for the Fujifilm X-Pro1

A patch that adds **Classic Chrome** to the X-Pro1 (firmware **3.82**) by replacing the **PRO Neg. Hi** film
simulation. The Classic Chrome data comes from Fujifilm's own X-E2 firmware, a sibling camera that received Classic
Chrome in a firmware update.

> **Warning: unofficial, experimental, at your own risk.** Flashing modified firmware can brick a camera, and there is
> currently **no SD-card recovery for the X-Pro1** (SD dual boot now works for testing, see the main README, but
> it does not repair a camera that won't start). This patch has been flashed on **one** camera so far. Read
> "Risks" before using it.

## Status

| | |
|---|---|
| Camera / firmware | X-Pro1, official firmware 3.82 only |
| Tested | 1 camera. v1 and **v2** (current, adds the chroma-gain fix) both flash, boot and shoot normally with the look applied. In-camera RAW conversion uses the patched look. The camera still reports Ver3.82 |
| Selecting it | choose **PRO Neg. Hi**. The menu, icon and EXIF still say "PRO Neg. Hi" |
| Other film simulations | unchanged (byte-identical) |
| Known difference from real Classic Chrome | v1: colours (strong reds especially) a little too saturated, because PRO Neg. Hi's extra chroma gain (up to ×1.15) was left in place. Fixed in v2. Blues/cyans were also not muted enough in v1; re-check on v2 |
| Original PRO Neg. Hi | lost while the patch is installed; re-flash the official file to get it back |

v1 measured on the test camera against PROVIA (same scene, same camera): saturation of foliage, grass and brick is down
about 18–21%, and blues are unchanged. An X-T20 shooting real Classic Chrome renders blues much greyer.

## What you need
* Your own copy of the **official** X-Pro1 firmware 3.82 `FPUPDATE.DAT` from Fujifilm's support site
  (SHA-256 `709e26f6dd77e922660010628fb20937b269be871b188b8810eb2cb4d5d33236`). No Fujifilm firmware is distributed here.
* Python 3.8 or newer (standard library only).

## Build the patched firmware
```
python3 xpro1_cc_patch.py FPUPDATE.DAT patched/FPUPDATE.DAT
```
The script refuses any input other than the official 3.82 file. It checks every value it replaces, re-compresses
and decodes back, fixes the checksum, and only continues if the content is byte-identical to the expected v2 build
(SHA-256 `4414a997…a08` before labelling). It then labels the file **3.83** and writes it
(SHA-256 `0df1cefec2a9188c82bf09e50736ea03e0ce9b4914561795808dd9bd1fac1cad`). It takes about 15 seconds.
v2 differs from the camera-tested v1 (`fb0dc86b…`) by one parameter byte (and that byte's copy in the code image).

**Why 3.83:** the camera only accepts an update whose version is newer than the installed one. With a file labelled
3.82 a camera already on 3.82 says the latest firmware is installed. The label is two header fields (0x204 major,
0x208 minor) outside the checksums; changing it does not change the firmware itself. `--version 3.84` etc. picks
another label if the camera ever reports 3.83 as installed.

## Install (same procedure as an official update)
1. Fully charged battery. Format a card **in the camera**.
2. Copy the patched `FPUPDATE.DAT` to the root of the card.
3. Hold **DISP/BACK** and switch the camera **ON**, still holding the button. The firmware update screen appears.
4. Confirm and **do not interrupt** (no power-off, no card or battery removal) until it finishes.

**Rollback:** the official 3.82 file is refused by a camera that is on 3.82 (or reports 3.83 after this patch). Make a
relabelled copy of the unmodified official firmware and install that:
```
python3 xpro1_cc_patch.py --stock FPUPDATE.DAT rollback/FPUPDATE.DAT --version 3.84
```
Only the version label differs from Fujifilm's file. Pick a label newer than whatever the camera shows on the update screen.

## Risks
* **Bricking.** If the camera couldn't decode the modified firmware, it wouldn't start, and the SD-card updater lives
  inside that firmware. On the test camera v1 and v2 both decoded and run fine, but this is one camera.
* **Power loss during the update** bricks any camera, modified or not.
* **Colour accuracy.** The tone curve is Fujifilm's exact Classic Chrome curve. The colour matrices are adapted from
  the X-E2 to the X-Pro1, not tuned by Fujifilm for this sensor. Blues are too strong (see Status).
* Not tested: the second colour-space setting (probably Adobe RGB, whose matrix is an approximation), in-camera RAW
  conversion, movies, or any firmware other than 3.82.
* The firmware has no cryptographic signature check; the camera only verifies simple checksums. A wrongly built file
  is therefore not stopped by cryptography. Use the script, which self-checks, and never hand-edit the output.

## What it changes
| Part | Change |
|---|---|
| Tone curve | Fujifilm's X-E2 Classic Chrome curve (#38) is placed in an unused slot of the X-Pro1's curve table. All 40 tone-curve references of PRO Neg. Hi point to it. |
| 3×3 colour matrix (PRO Neg. Hi) | Classic Chrome's change from PROVIA on the X-E2, applied to the X-Pro1's PROVIA matrix |
| 2×2 chroma matrix (PRO Neg. Hi) | same method; much lower chroma gain, which gives the muted look |
| Three small settings | detail preset, highlight/shadow family and chroma-gain preset set to PROVIA's values, as the X-E2 does for Classic Chrome (the chroma-gain preset is new in v2) |

No executable code is changed. 76 bytes of image-processing parameters and one 72-byte curve entry differ; the
code image containing them is re-compressed, and the update file's checksum is recomputed.

## How it works (technical notes)
* **Container:** a plain header (model IDs, version, checksum), then the flash image stored bit-inverted (XOR 0xFF),
  then a small plain trailer. This is a "type-4" header: payload checksum at 0x20c = `~Σ(bit-inverted payload bytes)`,
  trailer checksum = `~Σ(raw trailer bytes)` (32-bit). There is no signature.
* **Compression ("method 4"):** a 20-byte header (`unpacked, packed, ceil(packed/0x4000), 0x4000, 4`), then tokens
  `0nnnnnnn` = n literals, `1ddddddd ddddllll` = copy l (1–15) from distance d (1–2047). Decoding is done by a hardware
  engine. Fujifilm's encoder never lets a token cross a 16 KiB page boundary, and this patch keeps that rule.
* **Film simulations:** the film-sim setting maps to an internal "colour mode" (PROVIA 0 … PRO Neg Hi 7; Classic Chrome
  is 8 on the X-E2). The image pipeline indexes tables of *parameter IDs* by colour mode. Each ID is a byte offset into
  an image-processing parameter area that is stored in the update file. Values are gains (0x40 = 1.0), 13-bit signed
  matrix coefficients (0x400 = 1.0), or preset numbers. Tone curves are 28-knot 14-bit tables compiled into the code image.
* The X-Pro1 and X-E2 use the same film-sim numbering (0–12). The X-E2 appends Classic Chrome as 13 / colour mode 8.

## Credits and related work
* Reverse engineering and patch: this project. All values were derived from official Fujifilm firmware files.
* [fujimod](https://github.com/justjake/fujimod) (FujiHack community): independent documentation of the same
  update format, SD-card boot and recovery work for many Fujifilm cameras. Its advice applies: test modified firmware by
  SD dual-booting first where your camera supports it. (fujimod does not support the X-Pro1 yet; this repository's
  own experimental SD dual boot does, see the main README.)

Fujifilm, X-Pro1, X-E2 and Classic Chrome are trademarks of FUJIFILM Corporation. This project is not affiliated with or
endorsed by Fujifilm.
