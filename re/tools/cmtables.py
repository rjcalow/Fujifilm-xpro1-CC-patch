# Extract colour-mode-indexed parameter-ID tables from Ghidra C, and resolve their values in the adjustment DB.
import re,struct,sys,json
cfile,binf,B,imgf,dbbase,cmoff,getter=sys.argv[1],sys.argv[2],int(sys.argv[3],0),sys.argv[4],int(sys.argv[5],0),sys.argv[6],sys.argv[7]
blob=open(binf,'rb').read(); img=open(imgf,'rb').read()
parts=re.split(r'^//@@FUNC ',open(cfile).read(),flags=re.M)[1:]
U16=lambda a: struct.unpack('<H',blob[a-B:a-B+2])[0]
out=[]
for p in parts:
    hdr,body=p.split('\n',1); fn=hdr.split()[0]
    flat=re.sub(r'\s*\n\s*',' ',body)
    cm=re.escape(f'+ {cmoff})')
    if not re.search(cm,flat): continue
    # locals that hold colour mode
    locs=set(re.findall(r'(\w+) = \*\(\w+ \*\)\(\w+ '+cm,flat))
    cmexpr=r'(?:\*\(\w+ \*\)\(\w+ '+cm+(('|'+'|'.join(map(re.escape,locs))) if locs else '')+r')'
    for m in re.finditer(r'&DAT_([0-9a-f]{8}) \+ \(?([^;]*?)\) \* 2\)',flat):
        t=int(m.group(1),16); e=m.group(2)
        if not re.search(cmexpr,e): continue
        stride=None
        sm=re.search(r'\* (10|0xa|8|9|0xb|11|0x13|20|0x14)\b',e)
        if sm: stride=int(sm.group(1),0)
        out.append((fn,t,e.strip(),stride))
    for m in re.finditer(r'&DAT_([0-9a-f]{8}) \+ '+cmexpr+r' \* 2\)',flat):
        out.append((fn,int(m.group(1),16),'cm',None))
seen=set(); rows=[]
for fn,t,e,stride in out:
    if (fn,t) in seen: continue
    seen.add((fn,t)); rows.append((fn,t,e,stride))
for fn,t,e,stride in sorted(rows,key=lambda r:r[1]):
    print(f"fn {fn} table {t:#x} idx: {e[:110]}")
    nrows=1 if not stride else 6
    for k in range(nrows):
        ids=[U16(t+2*(k*(stride or 10)+i)) for i in range(10)]
        if k and (all(x==0 for x in ids) or any(x>0xe000 or (0<x<0x3000) for x in ids)): break
        vals=[img[dbbase+x] if x else None for x in ids]
        print(f"    row{k}: ids "+' '.join(f'{x:04x}' for x in ids)+"\n           vals "+' '.join(f'{v:4}' if v is not None else '   -' for v in vals)+f"   CC id={ids[8]:#06x} val={vals[8]}")
