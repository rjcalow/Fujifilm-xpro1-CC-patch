import sys,struct
def decode(src, pos, limit, out=None, verbose=0):
    out = bytearray() if out is None else out
    end = pos+limit
    while pos < end:
        b = src[pos]
        if b & 0x80:
            tok = (b<<8)|src[pos+1]; pos += 2
            dist = (tok & 0x7ff0) >> 4; ln = tok & 0xf
            if verbose: print(f"M d={dist} l={ln} @{len(out):#x}")
            if dist == 0 or dist > len(out):
                return out, pos, f"bad dist {dist} at out={len(out):#x}"
            for _ in range(ln): out.append(out[-dist])
        else:
            n = b; pos += 1
            if verbose: print(f"L {n} {src[pos:pos+n].hex()}")
            out += src[pos:pos+n]; pos += n
    return out, pos, None
if __name__=='__main__':
    d=open(sys.argv[1],'rb').read(); start=int(sys.argv[2],0); n=int(sys.argv[3],0)
    o,p,err=decode(d,start,n,verbose=1); print(err); print(o[:256].hex())
