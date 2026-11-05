# Find "bounded index into constant table" sites: cmp rX,#N ... [rB, rX, lsl #k] / add rD,rB,rX,lsl#k / mla
import re,sys,struct
def load_asm(p):
    L=[];A=[]
    for l in open(p):
        m=re.match(r'^([0-9a-f]{8}) (\S+) ?(.*)$',l.rstrip())
        if m: A.append(int(m.group(1),16)); L.append((m.group(2),m.group(3)))
    return A,L
def regconst(A,L,i,reg,blob,B):
    lo=None
    for j in range(i-1,max(0,i-40),-1):
        mn,op=L[j]
        if mn.startswith('movt') and op.startswith(reg+','):
            hi=int(op.split('#')[1],0)
            for k in range(j-1,max(0,j-12),-1):
                mn2,op2=L[k]
                if mn2.startswith('movw') and op2.startswith(reg+','):
                    return (hi<<16)|int(op2.split('#')[1],0)
            return None
        m=re.match(reg+r', \[pc, #(0x[0-9a-f]+|-?\d+)\]',op)
        if mn.startswith('ldr') and m:
            la=A[j]+8+int(m.group(1),0)
            if B<=la<B+len(blob)-4: return struct.unpack('<I',blob[la-B:la-B+4])[0]
            return None
        if op.startswith(reg+',') and not mn.startswith(('cmp','tst','str')): return None
    return None
def scan(asm,bin_,B,Ns):
    A,L=load_asm(asm); blob=open(bin_,'rb').read(); out=[]
    for i,(mn,op) in enumerate(L):
        m=re.match(r'^cmp$',mn) and re.match(r'(r\d+|ip|lr|sb|sl), #(0x[0-9a-f]+|\d+)$',op)
        if not m: continue
        N=int(m.group(2),0)
        if N not in Ns: continue
        x=m.group(1)
        for j in range(i+1,min(len(L),i+14)):
            mn2,op2=L[j]
            p=re.search(r'\[(r\d+|ip|lr|sb|sl), '+x+r'(?:, lsl #(\d+))?\]',op2)
            q=re.match(r'(r\d+|ip|lr|sb|sl), (r\d+|ip|lr|sb|sl), '+x+r'(?:, lsl #(\d+))?$',op2) if mn2.startswith('add') else None
            r=re.match(r'(r\d+|ip|lr|sb|sl), '+x+r', (r\d+|ip|lr|sb|sl), (r\d+|ip|lr|sb|sl)$',op2) if mn2.startswith('mla') else None
            base=None;sh=None;kind=None
            if p: base=p.group(1); sh=int(p.group(2) or 0); kind=mn2
            elif q: base=q.group(2); sh=int(q.group(3) or 0); kind='add'
            elif r: base=r.group(3); kind='mla'
            if base:
                bv=regconst(A,L,j,base,blob,B)
                if bv is None and kind=='mla':
                    bv=None
                out.append((A[i],N,A[j],kind,sh,bv))
                break
    return out
if __name__=='__main__':
    asm,bin_,B=sys.argv[1],sys.argv[2],int(sys.argv[3],0); Ns=[int(x,0) for x in sys.argv[4].split(',')]
    for a,N,s,k,sh,bv in scan(asm,bin_,B,Ns):
        if bv is not None: print(f"cmp@{a:#x} N={N} use@{s:#x} {k} lsl{sh} base={bv:#x}")
