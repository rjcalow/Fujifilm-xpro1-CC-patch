# Build the PRO Neg Hi -> Classic Chrome swap for X-Pro1 (NOT-space image + patched blob1). No checksum handling here.
import struct, json, sys, numpy as np
sys.path.insert(0,'/home/ricardo/Documents/xpro1 firmware/re/tools'); import lz, lzenc_chunked as lzenc
OUT='/home/ricardo/Documents/xpro1 firmware/re/build'
img=bytearray(open('work/not.bin','rb').read()); DB=0xae025c
b1=bytearray(open('work/blob1.bin','rb').read()); B1=0x774000; MIR=0x812470
b2=open('work/blob2.bin','rb').read(); B2=0xe0ec80
x2=open('x4/blob2.bin','rb').read(); X2B=0xf6a9c0; x2img=open('x4/not.bin','rb').read(); X2DB=0xe025c
x2b1=open('x4/blob1.bin','rb').read(); X2B1=0x8a0400
U=lambda a:struct.unpack('<H',b2[a-B2:a-B2+2])[0]
def s13(v): v&=0x1fff; return v-0x2000 if v&0x1000 else v
def enc13(x):
    v=int(round(x*1024)); assert -4096<=v<=4095, v; return v&0x1fff
log=[]
def setdb(ID,newbytes,what):
    old_f=bytes(img[DB+ID:DB+ID+len(newbytes)]); old_m=bytes(b1[MIR-B1+ID:MIR-B1+ID+len(newbytes)])
    assert old_f==old_m, (hex(ID),old_f,old_m)
    img[DB+ID:DB+ID+len(newbytes)]=newbytes; b1[MIR-B1+ID:MIR-B1+ID+len(newbytes)]=newbytes
    log.append(dict(what=what,id=hex(ID),file_off=hex(DB+ID),blob1_mirror=hex(MIR+ID),old=old_f.hex(),new=bytes(newbytes).hex()))
def m3x(bl,BB,im,D,base,p):
    ids=[struct.unpack('<H',bl[base+(p-1)*0x12+2*k-BB:][:2])[0] for k in range(9)]
    return np.array([s13(im[D+i]|(im[D+i+1]<<8)) for i in ids]).reshape(3,3)/1024, ids
def m2x(bl,BB,im,D,base,p):
    ids=[struct.unpack('<H',bl[base+(p-1)*8+2*k-BB:][:2])[0] for k in range(4)]
    a,d,b,c=[s13(im[D+i]|(im[D+i+1]<<8))/1024 for i in ids]; return np.array([[a,b],[c,d]]),ids
# --- source (X-E2) and target (X-Pro1) matrices
E_P1,_=m3x(x2,X2B,x2img,X2DB,0x1468e80,1); E_CC9,_=m3x(x2,X2B,x2img,X2DB,0x1468e80,9)
E2_P1,_=m2x(x2,X2B,x2img,X2DB,0x1466fa0,1); E2_CC,_=m2x(x2,X2B,x2img,X2DB,0x1466fa0,11)
img0=bytes(img)
P_s,_=m3x(b2,B2,img0,DB,0xf33b94,img0[DB+U(0xf34108)])        # X-Pro1 PROVIA sRGB 3x3
P_a,_=m3x(b2,B2,img0,DB,0xf33b94,img0[DB+U(0xf34300)])        # X-Pro1 PROVIA alt 3x3
P_2,_=m2x(b2,B2,img0,DB,0xf2e0d0,img0[DB+U(0xf2dd80)])        # X-Pro1 PROVIA 2x2
REL3=E_CC9@np.linalg.inv(E_P1); REL2=E2_CC@np.linalg.inv(E2_P1)
CC_s=REL3@P_s; CC_a=REL3@P_a; CC_2=REL2@P_2
# --- NegHi slots (index 4) on X-Pro1
pre_s=img0[DB+U(0xf34108+8)]; pre_a=img0[DB+U(0xf34300+8)]; pre_2=img0[DB+U(0xf2dd80+8)]
assert (pre_s,pre_a,pre_2)==(5,10,5)
_,ids_s=m3x(b2,B2,img0,DB,0xf33b94,pre_s); _,ids_a=m3x(b2,B2,img0,DB,0xf33b94,pre_a); _,ids_2=m2x(b2,B2,img0,DB,0xf2e0d0,pre_2)
for k,ID in enumerate(ids_s): setdb(ID,struct.pack('<H',enc13(CC_s.flat[k])),f'3x3 sRGB (preset 5) m{k//3}{k%3}')
for k,ID in enumerate(ids_a): setdb(ID,struct.pack('<H',enc13(CC_a.flat[k])),f'3x3 alt (preset 10) m{k//3}{k%3} [approximate]')
for ID,v,nm in zip(ids_2,(CC_2[0,0],CC_2[1,1],CC_2[0,1],CC_2[1,0]),('m00','m11','m01','m10')): setdb(ID,struct.pack('<H',enc13(v)),f'2x2 chroma (preset 5) {nm}')
setdb(0xffc6,bytes([1]),'detail preset NegHi -> PROVIA value (1)')
setdb(0xe13b,bytes([1]),'H/S tone family plane0 NegHi -> PROVIA value (1)')
# --- tone: put X-E2 curve #38 into the unreferenced X-Pro1 slot holding curve #40, point NegHi tone IDs at 38
slot=None
for k in range(29):
    if struct.unpack('<I',b1[0x80b700-B1+k*0x48:][:4])[0]==40: slot=0x80b700+k*0x48
src=x2b1[0xb839d8-X2B1+38*0x48:0xb839d8-X2B1+39*0x48]; assert struct.unpack('<I',src[:4])[0]==38
oldc=bytes(b1[slot-B1:slot-B1+0x48]); b1[slot-B1:slot-B1+0x48]=src
log.append(dict(what='tone curve table: slot of unreferenced curve #40 := X-E2 curve #38 entry',blob1_addr=hex(slot),old=oldc.hex(),new=src.hex()))
neg=json.load(open('negHi_curve_ids.json'))
for ID in neg:
    v=img[DB+ID]
    if v==16: continue           # special mode where every film sim uses curve 16: keep
    setdb(ID,bytes([38]),f'NegHi tone curve number {v} -> 38')
# --- re-compress blob1 into its partition
enc=lzenc.encode(bytes(b1)); src_len=len(enc)+20
hdr=struct.pack('<5I',len(b1),src_len,-(-src_len//0x4000),0x4000,4)
P0,PEND=0x10025c,0x24025c
assert src_len<=PEND-P0, hex(src_len)
img[P0:PEND]=hdr+enc+bytes(PEND-P0-src_len)   # NOT-space filler 0x00 (= 0xff raw), as in stock
dec,p,err=lz.decode(bytes(img),P0+20,src_len-20); assert err is None and bytes(dec)==bytes(b1)
# --- outputs
open(f'{OUT}/ccswap_not.bin','wb').write(img); open(f'{OUT}/ccswap_blob1.bin','wb').write(b1)
json.dump(dict(ops=log,blob1_compressed_size=hex(src_len),stock_compressed_size='0x13ba85',partition=hex(PEND-P0),
  matrices=dict(cc_3x3_srgb=CC_s.round(4).tolist(),cc_3x3_alt_approx=CC_a.round(4).tolist(),cc_2x2=CC_2.round(4).tolist())),open(f'{OUT}/ccswap_build_log.json','w'),indent=1)
diff=[i for i in range(len(img)) if img[i]!=img0[i]]
print(f'ops {len(log)}; blob1 compressed {src_len:#x} (stock 0x13ba85, partition 0x140000); round-trip OK')
print(f'changed bytes in NOT-space image: {len(diff)}, range {hex(diff[0])}..{hex(diff[-1])}')
outside=[i for i in diff if not (P0<=i<PEND or DB<=i<DB+0x10000)]
print('changed bytes outside blob1 partition and tuning area:',len(outside))
print('CC 3x3 sRGB',CC_s.round(3).tolist()); print('CC 3x3 alt (approx)',CC_a.round(3).tolist()); print('CC 2x2',CC_2.round(3).tolist())
