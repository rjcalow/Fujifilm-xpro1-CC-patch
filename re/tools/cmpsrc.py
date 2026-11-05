import re,sys,collections
def load(p):
    A=[];L=[]
    for l in open(p):
        m=re.match(r'^([0-9a-f]{8}) (\S+) ?(.*)$',l.rstrip())
        if m: A.append(int(m.group(1),16)); L.append((m.group(2),m.group(3)))
    return A,L
def src(L,i,reg):
    for j in range(i-1,max(0,i-12),-1):
        mn,op=L[j]
        if op.startswith(reg+','):
            m=re.match(reg+r', \[(\w+), #(0x[0-9a-f]+|\d+)\]',op)
            if mn.startswith('ldr') and m: return f"[{m.group(1)},#{m.group(2)}]"
            return mn
    return None
if __name__=='__main__':
    A,L=load(sys.argv[1]); N=int(sys.argv[2],0)
    c=collections.Counter(); ex=collections.defaultdict(list)
    for i,(mn,op) in enumerate(L):
        m=re.match(r'(r\d+|ip|lr|sb|sl|fp), #(0x[0-9a-f]+|\d+)$',op)
        if mn.startswith('cmp') and m and int(m.group(2),0)==N:
            s=src(L,i,m.group(1))
            if s and s.startswith('['):
                off=s.split('#')[1].rstrip(']'); c[off]+=1; ex[off].append(hex(A[i]))
    for off,n in c.most_common(40): print(off,n,ex[off][:6])
