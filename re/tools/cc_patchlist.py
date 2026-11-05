import json,struct
R='/home/ricardo/Documents/xpro1 firmware/re/classic_chrome'
cc=json.load(open(f'{R}/cc_port_data.json'))
img=open('work/not.bin','rb').read(); DB=0xae025c
b1=open('work/blob1.bin','rb').read(); B1=0x774000; MIR=0x812470
x4b1=open('x4/blob1.bin','rb').read(); X4B1=0x8a0400
ops=[]
def db16(name,ID,newval,conf='high'):
    old=img[DB+ID:DB+ID+2]; new=struct.pack('<H',newval)
    ops.append(dict(item=name,confidence=conf,param_id=hex(ID),
      adjust_area=dict(not_space_file_offset=hex(DB+ID),old=old.hex(),new=new.hex(),raw_file_old=bytes(x^0xff for x in old).hex(),raw_file_new=bytes(x^0xff for x in new).hex()),
      blob1_mirror=dict(blob1_addr=hex(MIR+ID),old=b1[MIR-B1+ID:MIR-B1+ID+2].hex(),new=new.hex())))
def db8(name,ID,newval,conf='high'):
    old=img[DB+ID:DB+ID+1]; new=bytes([newval])
    ops.append(dict(item=name,confidence=conf,param_id=hex(ID),
      adjust_area=dict(not_space_file_offset=hex(DB+ID),old=old.hex(),new=new.hex(),raw_file_old=bytes(x^0xff for x in old).hex(),raw_file_new=bytes(x^0xff for x in new).hex()),
      blob1_mirror=dict(blob1_addr=hex(MIR+ID),old=b1[MIR-B1+ID:MIR-B1+ID+1].hex(),new=new.hex())))
# 3x3 sRGB: NegHi preset 5 IDs 0xdb4b.. (row-major m00..m22)
for k,v in enumerate(cc['port']['xp1_cc_m3_srgb_raw']): db16(f'3x3 colour matrix sRGB m{k//3}{k%3}',0xdb4b+2*k,v)
# 3x3 alt colour space: preset 10 (low confidence)
for k,v in enumerate(cc['port']['xp1_cc_m3_adobe_raw']): db16(f'3x3 colour matrix alt-colour-space m{k//3}{k%3}',0xdba5+2*k,v,'low')
# 2x2 chroma: storage a,d,b,c
for nm,ID,v in zip(('m00(a)','m11(d)','m01(b)','m10(c)'),(0xe3c9,0xe3cb,0xe3cd,0xe3cf),cc['port']['xp1_cc_m2_raw_storage_order']): db16(f'2x2 chroma matrix {nm}',ID,v)
db8('detail preset (00f2ccb8/FUN_00f2c044) NegHi -> PROVIA value',0xffc6,1)
db8('H/S tone family plane0 (00f32c08) NegHi -> PROVIA value',0xe13b,1)
# tone curve: blob1 entry for curve#27 -> XE2 #38 body
e38=x4b1[0xb839d8-X4B1+38*0x48:0xb839d8-X4B1+39*0x48]
tgt=0x80be98; old=b1[tgt-B1:tgt-B1+0x48]
assert struct.unpack('<I',old[:4])[0]==27
new=old[:4]+e38[4:]
ops.append(dict(item='tone curve: X-Pro1 curve #27 (PRO Neg Hi) body := X-E2 curve #38 (Classic Chrome)',confidence='high',
  blob1=dict(blob1_addr=hex(tgt),length=hex(0x48),old=old.hex(),new=new.hex(),note='blob1 is LZ-compressed in FPUPDATE.DAT: patch decompressed blob1, re-encode (fits: 0x13bbe0 <= 0x140000)')))
json.dump(dict(strategy='data-only: PRO Neg Hi slot becomes Classic Chrome (menu/EXIF still say PRO Neg Hi)',ops=ops),open(f'{R}/xpro1_proneghi_to_classic_chrome_patch.json','w'),indent=1)
print(len(ops),'patch operations written')
for o in ops: print(' ',o['confidence'],o['item'],o.get('param_id',''),(o.get('adjust_area') or {}).get('old',''),'->',(o.get('adjust_area') or {}).get('new',''))
