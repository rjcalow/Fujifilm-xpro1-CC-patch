import struct
def movwt(b,base):
    n=len(b)//4; ws=struct.unpack(f'<{n}I',b[:n*4]); out=[]
    for i in range(n-1):
        w=ws[i]
        if w&0x0ff00000==0x03000000 and w>>28==0xe:
            rd=(w>>12)&0xf; lo=((w>>4)&0xf000)|(w&0xfff)
            for j in range(1,6):
                if i+j>=n: break
                v=ws[i+j]
                if v&0x0ff00000==0x03400000 and (v>>12)&0xf==rd:
                    out.append((base+i*4,((((v>>4)&0xf000)|(v&0xfff))<<16)|lo)); break
    return out
