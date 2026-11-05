import sys,pickle
sys.path.insert(0,'tools'); import insertions
def sim(a,b):
    if len(a)!=len(b) or not a: return 0
    eq=sum(1 for x,y in zip(a,b) if x==y)
    zpat=sum(1 for x,y in zip(a,b) if (x==0)==(y==0))
    return 0.5*eq/len(a)+0.5*zpat/len(a)
def scan(A,Ab,B,Bb,label,minrun=48):
    r=insertions.runs(A,B); out=[]
    for j,i,L in r:
        if L<minrun: continue
        jb=j+L; ia=i+L
        for s in (4,6,8,10,12,16,20,24,32,40,48,64,80,96,128,192,256,384,512,768,1024):
            if L<3*s: break
            prevB=B[jb-s:jb]; nextB=B[jb:jb+s]; nextA=A[ia:ia+s]
            # periodicity inside the shared run
            per=sim(B[jb-2*s:jb-s],prevB)
            if per<0.6: continue
            sb=sim(prevB,nextB); sa=sim(A[ia-s:ia],nextA)
            if sb>=0.6 and sa<0.45 and nextB.count(0)<s and len(set(nextB))>2:
                out.append((Bb+jb,Ab+ia,s,L,round(sb,2),round(sa,2))); break
    for o in out: print(f"{label} XE2 {o[0]:#x} XP1 {o[1]:#x} rec={o[2]} sharedlen={o[3]:#x} (L/rec={o[3]/o[2]:.1f}) simXE2={o[4]} simXP1={o[5]}")
if __name__=='__main__':
    pairs=[('work/blob1.bin',0x774000,'x4/blob1.bin',0x8a0400,'b1'),('work/blob2.bin',0xe0ec80,'x4/blob2.bin',0xf6a9c0,'b2'),
           ('work/pre_db.bin',0,'x4/pre_db.bin',0,'img')]
    for a,ab,b,bb,l in pairs: scan(open(a,'rb').read(),ab,open(b,'rb').read(),bb,l)
