import sys,numpy as np
def runs(path,base,minlen=128):
    b=open(path,'rb').read(); b=b[:len(b)//2*2]
    out=[]
    for par in (0,):
        a=np.frombuffer(b,dtype='<u2').astype(np.int64)
        inc=(np.diff(a)>=0)
        # find maximal runs of non-decreasing
        i=0;n=len(inc)
        idx=np.flatnonzero(~inc)
        starts=np.concatenate(([0],idx+1)); ends=np.concatenate((idx+1,[len(a)]))
        for s,e in zip(starts,ends):
            L=e-s
            if L>=minlen:
                seg=a[s:e]
                if seg[-1]-seg[0] >= 200 and len(np.unique(seg))>L//4:
                    out.append((base+2*s,L,int(seg[0]),int(seg[-1])))
    return out
if __name__=='__main__':
    path,base=sys.argv[1],int(sys.argv[2],0)
    r=runs(path,base)
    # group consecutive runs with similar length and spacing
    r.sort()
    groups=[];cur=[]
    for x in r:
        if cur and x[0]-cur[-1][0] <= 2*cur[-1][1]+64 and abs(x[1]-cur[-1][1])<=4:
            cur.append(x)
        else:
            if len(cur)>=4: groups.append(cur)
            cur=[x]
    if len(cur)>=4: groups.append(cur)
    for g in groups:
        sp=g[1][0]-g[0][0]
        print(f"{g[0][0]:#x} n={len(g):3d} len~{g[0][1]} stride={sp:#x} ranges={[(x[2],x[3]) for x in g[:3]]}")
