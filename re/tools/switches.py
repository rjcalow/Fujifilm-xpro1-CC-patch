import struct,sys
def switches(f,B,counts):
    b=open(f,'rb').read(); n=len(b)//4; ws=struct.unpack(f'<{n}I',b[:n*4]); res=[]
    for i,w in enumerate(ws):
        if w&0x0ffffff0==0x079ff100 and ws[i-1]&0x0ff00000==0x03500000:
            cnt=(ws[i-1]&0xff)+1
            if cnt not in counts: continue
            cases=[]
            for k in range(cnt):
                t=ws[i+2+k]; j=(t-B)//4
                if not(0<=j<n): cases=None;break
                # summarise case: collect movw/movt pair values within first 6 insns
                lo={};vals=[]
                for q in range(j,min(j+8,n)):
                    x=ws[q]
                    if x&0x0ff00000==0x03000000: lo[(x>>12)&0xf]=((x>>4)&0xf000)|(x&0xfff)
                    elif x&0x0ff00000==0x03400000:
                        r=(x>>12)&0xf; vals.append(((((x>>4)&0xf000)|(x&0xfff))<<16)|lo.get(r,0))
                    elif x&0x0ff00000==0x03a00000: vals.append(('#',x&0xfff))
                    if x&0x0f000000==0x0a000000: break
                cases.append((t,vals))
            if cases: res.append((B+i*4,cnt,cases))
    return res
if __name__=='__main__':
    f,B=sys.argv[1],int(sys.argv[2],0); counts=[int(x) for x in sys.argv[3].split(',')]
    for a,cnt,cases in switches(f,B,counts):
        addrs=[c[1] for c in cases]
        flat=[v for c in addrs for v in c if not isinstance(v,tuple)]
        print(f"{a:#x} n={cnt} distinct_targets={len(set(c[0] for c in cases))} addrs={len(flat)}")
        if len(flat)>=cnt//2:
            for k,(t,v) in enumerate(cases): print(f"    {k:2d} {t:#x} {[hex(x) if not isinstance(x,tuple) else '#'+str(x[1]) for x in v][:4]}")
