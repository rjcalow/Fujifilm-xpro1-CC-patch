# Classic Chrome for the Fujifilm X-Pro1

A patch that adds **Classic Chrome** to the X-Pro1 (firmware **3.82**) by replacing the **PRO Neg. Hi** film
simulation. The Classic Chrome data comes from Fujifilm's own X-E2 firmware, a sibling camera that received Classic
Chrome in a firmware update.

> **Warning: unofficial, experimental, at your own risk.** Flashing modified firmware can brick a camera, and there is
> currently **no SD-card recovery for the X-Pro1**. This patch has been flashed on **one** camera so far. Read
> "Risks" before using it.

## Status

| | |
|---|---|
| Camera / firmware | X-Pro1, official firmware 3.82 only |
| Tested | 1 camera: flashes, boots, shoots normally; the look is applied |
| Selecting it | choose **PRO Neg. Hi**. The menu, icon and EXIF still say "PRO Neg. Hi" |
| Other film simulations | unchanged (byte-identical) |
| Known difference from real Classic Chrome | **blues/cyans are not muted enough** (a blue-grey fence stays teal); warm colours and greens are muted as expected |
| Original PRO Neg. Hi | lost while the patch is installed; re-flash the official file to get it back |

Measured on the test camera against PROVIA (same scene, same camera): saturation of foliage, grass and brick is down
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
and decodes back, fixes the checksum, and only writes the output if it is byte-identical to the camera-tested build
(SHA-256 `fb0dc86b2f9e4fd49e8aa0714ee0d85d1a41118c29c10a51489b93778bb5ca3c`). It takes about 15 seconds.

## Install (same procedure as an official update)
1. Fully charged battery. Format a card **in the camera**.
2. Copy the patched `FPUPDATE.DAT` to the root of the card.
3. Hold **DISP/BACK** and switch the camera **ON**, still holding the button. The firmware update screen appears.
4. Confirm and **do not interrupt** (no power-off, no card or battery removal) until it finishes.

**Rollback:** do the same with the official `FPUPDATE.DAT`.

## Risks
* **Bricking.** If the camera couldn't decode the modified firmware, it wouldn't start, and the SD-card updater lives
  inside that firmware. On the test camera it decoded fine, and the output is byte-identical to that build, but this
  is one camera.
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
| Two small settings | detail preset and highlight/shadow family set to PROVIA's values, as the X-E2 does for Classic Chrome |

No executable code is changed. 75 bytes of image-processing parameters and one 72-byte curve entry differ; the
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
  SD dual-booting first where your camera supports it. (The X-Pro1 is not supported there yet.)

Fujifilm, X-Pro1, X-E2 and Classic Chrome are trademarks of FUJIFILM Corporation. This project is not affiliated with or
endorsed by Fujifilm.
