import capstone,sys
src,base,out=sys.argv[1],int(sys.argv[2],0),sys.argv[3]
b=open(src,'rb').read()
md=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_ARM); md.skipdata=True
with open(out,'w') as f:
    for a,sz,mn,op in md.disasm_lite(b,base):
        f.write(f"{a:08x} {mn} {op}\n")
