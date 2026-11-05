import sys,struct
FMT={1:'B',2:'H',4:'I'}
def elems(buf,pos,w,n): return struct.unpack('<'+FMT[w]*n,buf[pos:pos+w*n])
def interesting(v):
    if len(set(v))<4: return False
    d=[v[k+1]-v[k] for k in range(len(v)-1)]
    if len(set(d))==1: return False          # arithmetic sequence
    if max(v)==0: return False
    return True
def codemask(buf):
    import struct as st
    n=len(buf)//64; m=bytearray(n+1)
    for c in range(n):
        ws=st.unpack('<16I',buf[c*64:c*64+64])
        if sum(1 for x in ws if (x>>28)==0xe)>=8: m[c]=1
    return m
def run(A,Ab,B,Bb,N,label):
    hits=[]; ma=codemask(A); mb=codemask(B)
    def iscode(m,pos,ln): return any(m[k] for k in range(pos//64,(pos+ln)//64+1))
    for w in (1,2,4):
        idx={}
        for p in range(0,len(A)-w*(N+1),w):
            key=A[p:p+w*N]
            if iscode(ma,p,w*(N+1)): continue
            if key in idx: idx[key]=None; continue
            idx[key]=p
        for q in range(0,len(B)-w*(N+1),w):
            key=B[q:q+w*N]
            p=idx.get(key)
            if p is None: continue
            if iscode(mb,q,w*(N+1)): continue
            if p>=w and q>=w and A[p-w:p]==B[q-w:q]: continue   # not the left edge of the shared run
            v=elems(B,q,w,N+1); va=elems(A,p,w,N+1)
            if w==4 and sum(1 for x in v[:N] if (x>>28)==0xe)>=3: continue  # ARM code
            if w==4 and sum(1 for x in v[:N] if 0x700000<=x<0x2000000)>=3: continue  # pointers
            if not interesting(v[:N]): continue
            if v[N]==va[N]: continue          # table continues identically -> not an appended entry
            hits.append((w,Ab+p,Bb+q,v[:N],v[N],va[N]))
    for w,pa,pb,v,extra,anext in hits:
        print(f"{label} w={w} XP1 {pa:#x} XE2 {pb:#x} shared={list(v)} XE2_next={extra} XP1_next={anext}")
if __name__=='__main__':
    N=int(sys.argv[1])
    A=[('work/blob1.bin',0x774000),('work/blob2.bin',0xe0ec80),('work/pre_db.bin',0)]
    B=[('x4/blob1.bin',0x8a0400),('x4/blob2.bin',0xf6a9c0),('x4/pre_db.bin',0)]
    for fa,ab in A:
        a=open(fa,'rb').read()
        for fb,bb in B:
            run(a,ab,open(fb,'rb').read(),bb,N,f"{fa.split('/')[1][:6]}->{fb.split('/')[1][:6]}")
