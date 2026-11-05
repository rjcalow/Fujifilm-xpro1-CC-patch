# greedy encoder for the Fuji LZ: literal run [0nnnnnnn], match [1ddddddddddd llll] (d 1..2047, l 1..15)
def encode(data):
    out=bytearray(); lit=bytearray(); i=0; n=len(data)
    idx={}
    def flush():
        nonlocal lit
        while lit:
            c=lit[:127]; out.append(len(c)); out.extend(c); lit=lit[127:]
    while i<n:
        best_l=0;best_d=0
        if i+3<=n:
            key=bytes(data[i:i+3])
            for j in reversed(idx.get(key,[])[-32:]):
                dd=i-j
                if dd>2047: break
                l=0
                while l<15 and i+l<n and data[j+l]==data[i+l]: l+=1
                if l>best_l: best_l,best_d=l,dd
                if l==15: break
        if best_l>=3:
            flush(); out += bytes([0x80|(best_d>>4),((best_d&0xf)<<4)|best_l])
            for k in range(best_l):
                if i+k+3<=n: idx.setdefault(bytes(data[i+k:i+k+3]),[]).append(i+k)
            i+=best_l
        else:
            if i+3<=n: idx.setdefault(bytes(data[i:i+3]),[]).append(i)
            lit.append(data[i]); i+=1
    flush(); return bytes(out)
