# Disassemble a function (stops at the first return) or N instructions, with pc-relative literals resolved.
# usage: fnasm.py <image.bin> <load base> <addr>[:count] ...
import sys, struct, capstone
img = open(sys.argv[1], 'rb').read(); base = int(sys.argv[2], 0)
md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
w = lambda a: struct.unpack('<I', img[a - base:a - base + 4])[0]
for spec in sys.argv[3:]:
    a, n = (spec.split(':') + [None])[:2]; a = int(a, 0); stop = n is None; n = int(n or 2000)
    print(f'=== {a:#x}')
    for pc in range(a, a + 4 * n, 4):
        ins = next(md.disasm(img[pc - base:pc - base + 4], pc), None)
        if ins is None: print(f'{pc:08x} .word {w(pc):#010x}'); continue
        s = f'{pc:08x} {ins.mnemonic} {ins.op_str}'
        if ins.mnemonic.startswith('ldr') and '[pc, #' in ins.op_str:
            la = pc + 8 + int(ins.op_str.split('#')[-1].rstrip(']'), 0)
            if base <= la < base + len(img): s += f'   ; ={w(la):#x}'
        print(s)
        if stop and ((ins.mnemonic == 'bx' and ins.op_str == 'lr') or (ins.mnemonic in ('pop', 'ldm') and 'pc' in ins.op_str)):
            break
