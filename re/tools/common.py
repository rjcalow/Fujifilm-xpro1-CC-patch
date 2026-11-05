import sys,collections
W=32
def good(w):
    if len(set(w))<8: return False
    arm=sum(1 for k in range(3,W,4) if w[k]&0xf0==0xe0)
    return arm<3
def load(spec):
    out=[]
    for s in spec:
        f,base=s.split('@'); out.append((f,int(base,0),open(f,'rb').read()))
    return out
A=load(sys.argv[1].split(','))   # X-Pro1 sources
Bs=load(sys.argv[2].split(','))  # X-Pro2 sources
idx={}
for f,base,b in A:
    for i in range(0,len(b)-W,4):
        w=b[i:i+W]
        if good(w): idx.setdefault(w,(f,base+i))
print('indexed',len(idx),file=sys.stderr)
hits=[]
for f,base,b in Bs:
    i=0
    while i<len(b)-W:
        w=b[i:i+W]
        if w in idx:
            fa,aa=idx[w]
            # extend
            ra=None
            for ff,bb,buf in A:
                if ff==fa: ra=(buf,aa-bb)
            buf,ao=ra; l=W
            while i+l<len(b) and ao+l<len(buf) and b[i+l]==buf[ao+l]: l+=1
            hits.append((l,fa,aa,f,base+i)); i+=(l//4)*4
        else: i+=4
hits.sort(reverse=True)
for l,fa,aa,fb,ab in hits[:int(sys.argv[3])]:
    print(f"len={l:#7x}  xp1 {fa.split('/')[-1]}:{aa:#x}  xp2 {fb.split('/')[-1]}:{ab:#x}")
print('total hits',len(hits),file=sys.stderr)
