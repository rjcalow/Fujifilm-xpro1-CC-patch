import struct,re,collections,sys
def find_base(b):
    n=len(b)//4; ws=struct.unpack(f'<{n}I',b[:n*4])
    strs=[m.start() for m in re.finditer(rb'(?<=\x00)[\x20-\x7e]{3,}\x00',b)]
    pairs=collections.defaultdict(list)
    for k in range(len(strs)-2):
        pairs[(strs[k+1]-strs[k],strs[k+2]-strs[k+1])].append(strs[k])
    c=collections.Counter()
    for i in range(n-2):
        key=(ws[i+1]-ws[i],ws[i+2]-ws[i+1])
        if key in pairs and len(pairs[key])<5 and key[0]>4 and key[1]>4:
            for s in pairs[key]: c[(ws[i]-s)&0xffffffff]+=1
    return c.most_common(3)
if __name__=='__main__':
    d=open(sys.argv[1],'rb').read()
    for a in sys.argv[2:]:
        s,e=[int(x,0) for x in a.split(':')]
        print(a,[(hex(k),v) for k,v in find_base(d[s:e])])
