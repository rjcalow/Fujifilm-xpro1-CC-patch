#!/bin/sh
# usage: tools/unpack.sh FPUPDATE.DAT outdir   (needs python3 + capstone for disasm.py)
set -e
D=$(dirname "$0"); mkdir -p "$2"
python3 -I -c "import sys;d=open(sys.argv[1],'rb').read();open(sys.argv[2],'wb').write(bytes(x^0xff for x in d))" "$1" "$2/not.bin"
python3 -I "$D/extract.py" "$2/not.bin" "$2"
