"""Dump camera DRAM over USB (debug firmware PEEK). usage: dramdump.py OUT.bin [START [LEN]]  (default whole 256 MB)"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpdebug
out = sys.argv[1]; start = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x40000000
n = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x10000000
p = ptpdebug.PTP(); p.open(); t = time.time()
with open(out, 'wb') as f:
    for a in range(start, start + n, 0x100000):
        f.write(p.peek(a, min(0x100000, start + n - a)))
        if (a - start) % 0x1000000 == 0: print(f'{a:#x} {time.time() - t:.0f}s', flush=True)
p.op(0x1003); print('done', out, f'{time.time() - t:.0f}s')
