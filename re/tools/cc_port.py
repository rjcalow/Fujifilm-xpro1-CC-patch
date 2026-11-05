import struct, json, numpy as np
X2=dict(b2=open('x4/blob2.bin','rb').read(),B2=0xf6a9c0,b1=open('x4/blob1.bin','rb').read(),B1=0x8a0400,img=open('x4/not.bin','rb').read(),DB=0xe025c)
X1=dict(b2=open('work/blob2.bin','rb').read(),B2=0xe0ec80,b1=open('work/blob1.bin','rb').read(),B1=0x774000,img=open('work/not.bin','rb').read(),DB=0xae025c)
def U(c,a,blob='b2'): return struct.unpack('<H',c[blob][a-c['B2' if blob=='b2' else 'B1']:][:2])[0]
def byte(c,i): return c['img'][c['DB']+i]
def raw16(c,i): return c['img'][c['DB']+i]|(c['img'][c['DB']+i+1]<<8)
def s13(v): v&=0x1fff; return v-0x2000 if v&0x1000 else v
def enc13(x): return int(round(x*1024))&0x1fff
def mat(c,base,stride,n,preset):
    ids=[U(c,base+(preset-1)*stride+2*k) for k in range(n)]
    raw=[raw16(c,i) for i in ids]; return ids,raw,[s13(r)/1024 for r in raw]
def m22(vals): a,d,b,cc=vals; return np.array([[a,b],[cc,d]])   # storage order +0 a,+2 d,+4 b,+6 c
def curve(c,tbl,count_addr,no):
    blob=c['b1'];B=c['B1'];n=struct.unpack('<I',blob[count_addr-B:count_addr-B+4])[0]
    for k in range(n):
        e=blob[tbl-B+k*0x48:tbl-B+(k+1)*0x48]
        if struct.unpack('<I',e[:4])[0]==no: return dict(entry=k,hdr=list(e[4:13]),knots=list(struct.unpack('<28H',e[0x10:0x48])),raw=e.hex())
out={}
# ---------- X-E2 source ----------
out['xe2']=dict(
 tone_curve_38=curve(X2,0xb839d8,0xb839d0,38), tone_curve_1_provia=curve(X2,0xb839d8,0xb839d0,1),
 m3_srgb_cc=mat(X2,0x1468e80,0x12,9,9), m3_srgb_provia=mat(X2,0x1468e80,0x12,9,1),
 m3_adobe_cc=mat(X2,0x1468e80,0x12,9,16), m3_adobe_provia=mat(X2,0x1468e80,0x12,9,11),
 m2_srgb_cc=mat(X2,0x1466fa0,8,4,11), m2_srgb_provia=mat(X2,0x1466fa0,8,4,1),
 m2_adobe_cc=mat(X2,0x1466fa0,8,4,13), m2_adobe_provia=mat(X2,0x1466fa0,8,4,6))
# ---------- X-Pro1 target (PROVIA) ----------
pre3s=byte(X1,U(X1,0xf34108)); pre3a=byte(X1,U(X1,0xf34300)); pre2=byte(X1,U(X1,0xf2dd80))
out['xp1']=dict(provia_preset_3x3_srgb=pre3s,provia_preset_3x3_adobe=pre3a,provia_preset_2x2=pre2,
 m3_srgb_provia=mat(X1,0xf33b94,0x12,9,pre3s), m3_adobe_provia=mat(X1,0xf33b94,0x12,9,pre3a), m2_provia=mat(X1,0xf2e0d0,8,4,pre2))
# X-Pro1 PROVIA tone curves (FUN_00f321f0 normal path, family 0)
c1=byte(X1,U(X1,0xf34098)); c2=byte(X1,U(X1,0xf3427c))
out['xp1']['provia_curves']=[c1,c2]
out['xp1']['provia_curve_a']=curve(X1,0x80b700,0x80b6f8,c1); out['xp1']['provia_curve_b']=curve(X1,0x80b700,0x80b6f8,c2)
# ---------- relative port ----------
def M3(v): return np.array(v[2]).reshape(3,3)
rel3s=M3(out['xe2']['m3_srgb_cc'])@np.linalg.inv(M3(out['xe2']['m3_srgb_provia']))
rel3a=M3(out['xe2']['m3_adobe_cc'])@np.linalg.inv(M3(out['xe2']['m3_adobe_provia']))
p3s=rel3s@M3(out['xp1']['m3_srgb_provia']); p3a=rel3a@M3(out['xp1']['m3_adobe_provia'])
rel2=m22(out['xe2']['m2_srgb_cc'][2])@np.linalg.inv(m22(out['xe2']['m2_srgb_provia'][2]))
p2=rel2@m22(out['xp1']['m2_provia'][2])
def enc_m3(m): return [enc13(x) for x in m.flatten()]
def enc_m2(m): return [enc13(m[0,0]),enc13(m[1,1]),enc13(m[0,1]),enc13(m[1,0])]
out['port']=dict(rel3_srgb=rel3s.round(4).tolist(),rel3_adobe=rel3a.round(4).tolist(),rel2=rel2.round(4).tolist(),
  xp1_cc_m3_srgb=p3s.round(4).tolist(),xp1_cc_m3_srgb_raw=enc_m3(p3s),xp1_cc_m3_adobe=p3a.round(4).tolist(),xp1_cc_m3_adobe_raw=enc_m3(p3a),
  xp1_cc_m2=p2.round(4).tolist(),xp1_cc_m2_raw_storage_order=enc_m2(p2))
# tone: relative remap T = CC38 o PROVIA1^-1 applied to X-Pro1 PROVIA curve(s) (knot-wise, same 28-knot grid/header)
k1=np.array(out['xe2']['tone_curve_1_provia']['knots'][:27],float); k38=np.array(out['xe2']['tone_curve_38']['knots'][:27],float)
def T(y): return np.interp(y,k1,k38)
for lab in ('a','b'):
    kp=np.array(out['xp1'][f'provia_curve_{lab}']['knots'][:27],float)
    out['port'][f'xp1_cc_curve_{lab}_knots']=[int(round(v)) for v in T(kp)]+[0]
json.dump(out,open('/home/ricardo/Documents/xpro1 firmware/re/classic_chrome/cc_port_data.json','w'),indent=1,default=lambda o:o.tolist() if hasattr(o,'tolist') else str(o))
# print summary
np.set_printoptions(precision=3,suppress=True)
print('XE2 CC 3x3 sRGB\n',M3(out['xe2']['m3_srgb_cc'])); print('XE2 PROVIA 3x3 sRGB\n',M3(out['xe2']['m3_srgb_provia']))
print('XP1 PROVIA 3x3 sRGB (preset',pre3s,')\n',M3(out['xp1']['m3_srgb_provia'])); print('PORTED XP1 CC 3x3 sRGB\n',p3s,'\n raw',enc_m3(p3s))
print('XP1 PROVIA 3x3 Adobe (preset',pre3a,')\n',M3(out['xp1']['m3_adobe_provia'])); print('PORTED XP1 CC 3x3 Adobe\n',p3a)
print('XE2 CC 2x2 / PROVIA 2x2\n',m22(out['xe2']['m2_srgb_cc'][2]),'\n',m22(out['xe2']['m2_srgb_provia'][2]))
print('XP1 PROVIA 2x2 (preset',pre2,')\n',m22(out['xp1']['m2_provia'][2])); print('PORTED XP1 CC 2x2\n',p2,'\n raw(storage a,d,b,c)',enc_m2(p2))
print('XP1 PROVIA curves',out['xp1']['provia_curves'],'curve a knots',out['xp1']['provia_curve_a']['knots'][:10])
print('XE2 #1 knots',out['xe2']['tone_curve_1_provia']['knots'][:10]); print('XE2 #38 knots',out['xe2']['tone_curve_38']['knots'][:10])
print('PORTED XP1 CC curve a',out['port']['xp1_cc_curve_a_knots'][:10])
