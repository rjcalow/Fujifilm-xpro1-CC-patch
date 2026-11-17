# Four looks for the original Fujifilm X-Pro1

The experimental **3.93** updater puts four named colour looks in the shooting Film Simulation menu on normal power-on. Classic Chrome occupies the original PRO Neg. Hi slot. Superia 400, Reggie's Portra and Kodachrome II use three previously hidden mode IDs. The shooting menu has 13 entries in total, including PRO Neg. Std.

## What's in the recipes

| Shooting menu entry | Rendering used for still JPEGs |
| --- | --- |
| CLASSIC CHROME | The project's X-E2-derived Chrome curve with its v3 chroma tuning. Select it for plain Chrome with your own settings. |
| SUPERIA 400 | An original look inspired by Fuji Superia X-TRA 400. It uses ASTIA's colour matrices, the gentler PRO Neg. Std tone curve and a PROVIA-derived chroma matrix with a modest boost to cool colours. |
| REGGIE'S PORTRA | Classic Chrome, Auto WB shifted R+2/B−4, Colour +2, Highlight −1, Shadow −1, Sharpness −2. |
| KODACHROME II | PRO Neg. Std, Auto WB shifted R+1/B−2, Colour −2, Highlight +1, Shadow +2, Sharpness +2. |

The two named recipes apply their overrides to the shooting settings sent to the image processor. The saved WB fine-tune and colour settings remain available when you switch back to plain Chrome. **Dynamic range and noise reduction are manual.** For Reggie's Portra, select DR Auto and NR −2. For Kodachrome II, select DR400 and NR −2 (ISO 800 or higher for DR400). Reggie's original X-Trans IV recipe also calls for NR −4, grain and Color Chrome effects. The X-Pro1 adaptation uses the controls available on this body. [Reggie Ballesteros's original recipe](https://reggiebphotography.com/blog/the-most-versatile-fujifilm-x-trans-iv-film-simulation-recipe-reggies-portra) · [Ritchie Roesch's Kodachrome II for X-Trans I](https://fujixweekly.com/2021/08/01/fujifilm-x-trans-i-x-pro1-x-e1-film-simulation-recipe-kodachrome-ii/)

**Manual focus:** HIGH focus peaking stays white. Two HIGH gain values increase from 64 to 120, alongside an earlier HIGH tuning change from 40 to 48. The gain is a signal-strength setting. The width of an outline still depends on the scene. On the test body, the owner found the white edges easier to see at 3× with a manual Helios lens.

## Build on your computer

Use a checkout of this repository, Python 3 and the original X-Pro1 **3.82** body updater from Fujifilm. Save the official file as `FPUPDATE.DAT` in your working directory. The script uses the repository's existing firmware decoder, encoder and Classic Chrome research. [Fujifilm's X-Pro1 download](https://www.fujifilm-x.com/global/support/download/firmware/cameras/x-pro1/)

Run from the repository root, with a fresh output directory:

```sh
python -m pip install keystone-engine==0.9.2
mkdir four-looks
python public/xpro1_four_looks.py FPUPDATE.DAT four-looks/FPUPDATE.DAT
```

| File | SHA-256 |
| --- | --- |
| Official 3.82 input | `709e26f6dd77e922660010628fb20937b269be871b188b8810eb2cb4d5d33236` |
| Four-look 3.93 output (38,274,200 bytes) | `540766f06bc19f059013a65b3e5efb398abf5f457f780bd7b1bf192ed4d17aef` |

The patcher checks the exact input, expected firmware layout, recompression round-trip, container checksums and final SHA-256 before writing. It requires a new output file. No intermediate custom updater or SD boot files are needed.

## Testing, installation and recovery

A fresh download of official 3.82 produced an updater byte-for-byte identical to the file flashed on one X-Pro1. The owner reports 3.93 is working. The emulator exercised all 13 stored selections, the two new recipe labels, recipe changes and switching back, both colour spaces and the 19 highlight/shadow gain values. The emulator checks shooting parameters and ARM routines. Physical colour accuracy, playback RAW conversion for the added entries, and recovery after a failed flash are unverified.

To repeat the emulator checks against the file you built:

```sh
python -m pip install unicorn==2.1.4
python re/tools/emu_four_looks.py FPUPDATE.DAT four-looks/FPUPDATE.DAT
```

**Flashing writes the camera's internal firmware and can brick the body.** Use a fully charged battery. Copy the generated `FPUPDATE.DAT` to the root of a camera-formatted SD card. Hold **DISP/BACK** while powering on, choose **BODY**, and check the target is **3.93**. Leave the battery and card in place until the camera reports completion. Power off, then start normally and open the shooting Film Simulation menu. [Fujifilm's update instructions](https://www.fujifilm-x.com/global/support/download/firmware/cameras/x-pro1/)

If the camera still boots and its updater works, the project's stock-relabel option can prepare a return to stock. Select PROVIA before rollback. The stock updater needs a version label above the installed one, for example `3.94` after `3.93`. A camera that cannot start its updater may need service. [Stock-relabel instructions](README.md#install-same-procedure-as-an-official-update)
