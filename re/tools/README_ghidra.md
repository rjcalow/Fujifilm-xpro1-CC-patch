# Ghidra headless decompile (used for the Classic Chrome extraction)

Needs JDK 25 + Ghidra 12.2 (portable unzips are fine). For each blob:

    analyzeHeadless <projdir> <name> -import blob2.bin -loader BinaryLoader \
        -loader-baseAddr 0xf6a9c0 -processor ARM:LE:32:v7 -scriptPath re/tools/gscripts \
        -preScript MakeFuncs.java -postScript MakeFuncs.java -postScript DumpC.java out/blob2.c

Load bases: X-Pro1 blob1 0x774000, blob2 0xe0ec80; X-E2 blob1 0x8a0400, blob2 0xf6a9c0; X-Pro2 blob1 0xa51000, blob2 0x1263000.
MakeFuncs creates functions at every `push {...,lr}` (raw binaries have no symbols); DumpC writes all functions as C
with `//@@FUNC <addr> <name>` separators, which getfunc.py / cmtables.py read.

cc_port.py / cc_patchlist.py expect to run from a directory holding `work/` (X-Pro1: not.bin, blob1.bin, blob2.bin)
and `x4/` (X-E2: same files), as produced by unpack.sh.
