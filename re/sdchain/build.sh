#!/bin/sh
# Compile the SD chain stub. usage: re/sdchain/build.sh <python with ziglang installed> <outdir>
# Writes <outdir>/chain.bin (LED progress build), <outdir>/chain_quiet.bin (-DQUIET: LED only during inflate) and
# <outdir>/chain_crumbs.bin (-DQUIET -DCRUMBS: + breadcrumbs in DRAM, re/tools/crumbs.py).
# Reproducible: chain_quiet.bin rebuilt this way on 2026-11-08 was byte-identical to the one used for the cards
# d9882560… / 7372fdf6… / 0d625083….
set -e
PY=$1; OUT=$2; D=$(dirname "$0"); mkdir -p "$OUT"
for v in chain:"" chain_quiet:-DQUIET "chain_crumbs:-DQUIET -DCRUMBS"; do
    name=${v%%:*}; def=${v#*:}
    "$PY" -m ziglang cc -target arm-freestanding-eabi -mcpu=cortex_r4 -Os $def -ffreestanding -nostdlib -fno-builtin \
        -T "$D/link.ld" "$D/start.S" "$D/main.c" -o "$OUT/$name.elf"
    "$PY" -m ziglang objcopy -O binary "$OUT/$name.elf" "$OUT/$name.bin"
    echo "$OUT/$name.bin $(sha256sum "$OUT/$name.bin" | cut -c1-16)…"
done
