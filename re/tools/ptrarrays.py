import struct,sys
def arrays(path,B,lens,lo=None,hi=None):
    b=open(path,'rb').read(); n=len(b)//4; ws=struct.unpack(f'<{n}I',b[:n*4])
    lo=lo or B; hi=hi or B+len(b)
    out=[]; i=0
    while i<n:
        j=i
        while j<n and lo<=ws[j]<hi and ws[j]%2==0: j+=1
        L=j-i
        if L in lens:
            v=ws[i:j]
            if len(set(v))>=L-2: out.append((B+i*4,L,v))
        i=max(j,i+1)
    return out
if __name__=='__main__':
    path,B=sys.argv[1],int(sys.argv[2],0); lens=[int(x) for x in sys.argv[3].split(',')]
    for a,L,v in arrays(path,B,lens):
        d=[v[k+1]-v[k] for k in range(L-1)]
        print(f"{a:#x} n={L} first={v[0]:#x} last={v[-1]:#x} deltas={sorted(set(d))[:5]}{'...' if len(set(d))>5 else ''}")
