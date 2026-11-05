# Find shared runs between image A and image B, then report "insertions": places where B matches A,
# then has extra bytes, then resumes matching A exactly where it left off.
import sys,pickle
W=16
def good(w): return len(set(w))>=5
def runs(A,B):
    idx={}
    for i in range(0,len(A)-W,2):
        w=A[i:i+W]
        if good(w) and w not in idx: idx[w]=i
    out=[];j=0
    while j<len(B)-W:
        w=B[j:j+W]
        i=idx.get(w)
        if i is not None:
            l=W
            while j+l<len(B) and i+l<len(A) and A[i+l]==B[j+l]: l+=1
            out.append((j,i,l)); j+=l
        else: j+=2
    return out
if __name__=='__main__':
    A=open(sys.argv[1],'rb').read(); Ab=int(sys.argv[2],0); B=open(sys.argv[3],'rb').read(); Bb=int(sys.argv[4],0)
    r=runs(A,B); pickle.dump(r,open(sys.argv[5],'wb'))
    print('runs',len(r),file=sys.stderr)
    for k in range(len(r)-1):
        j,i,l=r[k]; j2,i2,l2=r[k+1]
        if l>=24 and l2>=24 and i2==i+l and 0<j2-(j+l)<=0x2000:
            ins=j2-(j+l)
            print(f"B {Bb+j+l:#x} (+{ins:#x} inserted)  A {Ab+i+l:#x}   ctxlen {l:#x}/{l2:#x}")
