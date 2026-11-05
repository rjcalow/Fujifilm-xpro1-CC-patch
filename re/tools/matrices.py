import sys,numpy as np,collections
def find(path,base,dtype='<i2'):
    b=open(path,'rb').read(); b=b[:len(b)//2*2]
    a=np.frombuffer(b,dtype=dtype).astype(np.int64)
    hits=[]
    for one in (256,1024,2048,4096,8192):
        n=len(a)-9
        r0=a[0:n]+a[1:n+1]+a[2:n+2]; r1=a[3:n+3]+a[4:n+4]+a[5:n+5]; r2=a[6:n+6]+a[7:n+7]+a[8:n+8]
        diag=(a[0:n]>one*0.6)&(a[4:n+4]>one*0.6)&(a[8:n+8]>one*0.6)&(a[0:n]<one*4)&(a[4:n+4]<one*4)&(a[8:n+8]<one*4)
        offd=np.ones(n,bool)
        for k in (1,2,3,5,6,7): offd&=(a[k:n+k]!=0)
        tol=max(2,one//256)
        m=(abs(r0-one)<=tol)&(abs(r1-one)<=tol)&(abs(r2-one)<=tol)&diag
        for i in np.flatnonzero(m): hits.append((base+2*int(i),one,a[i:i+9].tolist(),bool(offd[i])))
    return hits
if __name__=='__main__':
    hits=find(sys.argv[1],int(sys.argv[2],0))
    hits.sort()
    # cluster
    groups=[];cur=[]
    for h in hits:
        if cur and h[0]-cur[-1][0]<=64 and h[1]==cur[-1][1]: cur.append(h)
        else:
            if cur: groups.append(cur)
            cur=[h]
    if cur: groups.append(cur)
    for g in groups:
        st=sorted(set(g[k+1][0]-g[k][0] for k in range(len(g)-1)))
        print(f"{g[0][0]:#x} one={g[0][1]} n={len(g)} strides={st[:4]} first={g[0][2]}")
