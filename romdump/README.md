# X-Pro1 ROM dump card

**Aim:** get a copy of the X-Pro1's boot ROM for research and hobby (including AI-assisted) reverse-engineering
projects.

Use this SD card to read the boot ROM over USB. It changes the camera's firmware in RAM only, so nothing is
installed. Take the battery out and the camera is back to normal. Unofficial; use at your own risk.

## You need

* An X-Pro1 on firmware **3.82**. If it is older, update it first the normal Fujifilm way.
* `FPUPDATE.DAT` 3.82 from [Fujifilm's X-Pro1 firmware page](https://www.fujifilm-x.com/support/download/firmware/cameras/x-pro1/).
* A Linux PC, a USB cable and an SD card.

## Steps

1. Put `FPUPDATE.DAT` in the repository folder, then run:

   ```
   sh re/tools/setup_work.sh
   ~/.venvs/xpro1-re/bin/pip install pyusb
   ~/.venvs/xpro1-re/bin/python romdump/build_dumpcard.py FPUPDATE.DAT re/build/romdump_card
   ```

   It should say `ffboot.bin matches the reference build`.

2. Copy `ffboot.bin` and `ffsys.bin` from `re/build/romdump_card/` to the root of the SD card. Eject the card
   properly.

3. Take the battery out and put it back. Insert the card.

4. **Hold Fn and press in the command dial** while you switch the camera on.

5. Connect USB and run:

   ```
   ~/.venvs/xpro1-re/bin/python romdump/romdump.py info
   ~/.venvs/xpro1-re/bin/python romdump/romdump.py rom xpro1_bootrom.bin
   ```

   `info` should say `ROM dump card v1 is running`. `rom` saves the 16 KiB boot ROM and checks it against the known
   one.

6. To go back to normal, take the battery out.

## If it doesn't work

* `PEEK: not available`: the camera started normally. Repeat steps 3 and 4.
* `Resource busy`: run `gio mount -s gphoto2; pkill -f gvfs-gphoto2-volume-monitor`.
* Screen stays dark: take the battery out.

Please don't publish the dump; it is Fujifilm's code. Sharing its SHA-256 is fine.
