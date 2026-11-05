# usage: extract.py not.bin outdir [hdr_off ...]
# Decompresses Fuji LZ blobs from a NOT-ed firmware image. With no offsets, the model is auto-detected.
import sys,struct,os; sys.path.insert(0,os.path.dirname(__file__)); import lz
KNOWN={'xpro1':(0x10025c,0x24025c),'xpro2':(0x23025c,0x41025c),'xe2':(0x16025c,0x32025c)}
d=open(sys.argv[1],'rb').read(); outdir=sys.argv[2]
if len(sys.argv)>3: offs=[int(x,0) for x in sys.argv[3:]]
else:
    def ok(o): dst,src,nch,blk,x=struct.unpack('<5I',d[o:o+20]); return blk==0x4000 and x==4 and nch==-(-src//0x4000)
    offs=next((v for v in KNOWN.values() if all(ok(o) for o in v)),None)
    assert offs, 'unknown model: pass LZ header offsets explicitly'
for k,base in enumerate(offs,1):
    dst,src,nch,blk,x=struct.unpack('<5I',d[base:base+20])
    o,p,err=lz.decode(d,base+20,src-20)
    assert err is None and len(o)==dst and p==base+src, (base,err,hex(len(o)))
    _,load,size,entry=struct.unpack('<4I',o[:16])
    open(f'{outdir}/blob{k}.bin','wb').write(o)
    print(f"blob{k}: comp@{base:#x} src={src:#x} dst={dst:#x} chunks={nch:#x} load={load:#x} entry={entry:#x}")
