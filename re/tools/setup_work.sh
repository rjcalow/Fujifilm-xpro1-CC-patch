#!/bin/sh
# Persistent RE environment (scratch folders get wiped). usage: sh re/tools/setup_work.sh
#   venv: ~/.venvs/xpro1-re (capstone, keystone-engine, unicorn, ziglang, numpy)
#   re/work/ (gitignored): not.bin, blob1/blob2, loader.bin, sec0.bin + .asm listings, compiled SD stubs
set -e
R=$(cd "$(dirname "$0")/.." && pwd); W=$R/work; PY=$HOME/.venvs/xpro1-re/bin/python
[ -x "$PY" ] || { python3 -m venv "$HOME/.venvs/xpro1-re"; "$HOME/.venvs/xpro1-re/bin/pip" install -q capstone keystone-engine unicorn ziglang numpy; }
mkdir -p "$W"
"$PY" -I -c "import sys;d=open(sys.argv[1],'rb').read();n=d[:0x240]+bytes(x^0xff for x in d[0x240:]);open(sys.argv[2]+'/not.bin','wb').write(n);open(sys.argv[2]+'/loader.bin','wb').write(n[0x4025c:0x4025c+0x40000]);open(sys.argv[2]+'/sec0.bin','wb').write(n[0x8025c:0x8025c+0xd7a0])" "$R/../FPUPDATE.DAT" "$W"
"$PY" -I "$R/tools/extract.py" "$W/not.bin" "$W"
for f in loader:0 sec0:0x40000 blob1:0x774000 blob2:0xe0ec80; do "$PY" -I "$R/tools/disasm.py" "$W/${f%%:*}.bin" "${f#*:}" "$W/${f%%:*}.asm"; done
sh "$R/sdchain/build.sh" "$PY" "$W/chain"
