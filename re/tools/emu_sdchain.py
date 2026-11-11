# Emulator test for the SD chain loader (re/sdchain → re/build/sdchain/ffboot.bin). Needs: pip install unicorn
# usage: emu_sdchain.py <FPUPDATE.DAT> <ffboot.bin>
# Checks: normal path inflates the stock loader to address 0 byte-identically and jumps to 0; bad CRC → code 4;
# corrupted payload → code 5. Prints the green-LED write sequence (GPIO 0xfff893c0).
import struct, sys
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_PC, UC_CPU_ARM_CORTEX_R5
dat, boot = sys.argv[1:3]
ffboot = open(boot, 'rb').read()
import zlib
raw = open(dat, 'rb').read()
_m = ffboot.find(struct.pack('<I', 0x4e494843)); _s, _o, _l, _n, _c = struct.unpack('<5I', ffboot[_m - 0x14:_m])
loader = zlib.decompress(ffboot[_o:_o + _l], -15)   # expected image (stock or marker-patched)
CFG = ffboot.find(struct.pack('<I', 0x4e494843)) - 0x14
HOOK = None   # optional: address where the loader's patched final jump lands (set by callers)

def run(image, budget=800_000_000):
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM); mu.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_R5)
    mu.mem_map(0, 0x1000000); mu.mem_map(0x40000000, 0x2000000); mu.mem_map(0xfff89000, 0x1000)
    mu.mem_write(0, b'\xaa' * 0x40000); mu.mem_write(0x41f60000, b'\x5a' * 0x20000)
    mu.mem_write(0, image)
    st = {'led': [], 'hits0': 0}
    def code(uc, a, s, u):
        st['hits0'] += 1
        if st['hits0'] == 2: st['jumped'] = True; uc.emu_stop()
    def gpio(uc, acc, a, s, v, u):
        if a == 0xfff893c0: st['led'].append('on' if v & 0x40004 == 0x40000 else 'off' if v & 0x40004 == 0x40004 else hex(v))
    mu.hook_add(UC_HOOK_CODE, code, begin=0, end=0)
    mu.hook_add(UC_HOOK_MEM_WRITE, gpio, begin=0xfff89000, end=0xfff89fff)
    try: mu.emu_start(0, 0xffffffff, count=budget)
    except UcError as e: st['err'] = str(e)
    st['pc'] = mu.reg_read(UC_ARM_REG_PC); st['mem0'] = bytes(mu.mem_read(0, 0x40000))
    return st

st = run(ffboot, 4_000_000_000)
print('normal: jumped', st.get('jumped'), '| loader at 0 identical:', st['mem0'] == loader, '| LED', st['led'], '| err', st.get('err'))
bad = bytearray(ffboot); struct.pack_into('<I', bad, CFG + 0x10, 0x12345678)
st = run(bytes(bad), 300_000_000); print('bad crc: jumped', st.get('jumped'), 'pc', hex(st['pc']), 'LED tail', st['led'][-9:])
bad = bytearray(ffboot); po = struct.unpack('<I', ffboot[CFG + 4:CFG + 8])[0]; bad[po + 200] ^= 0x5a
st = run(bytes(bad), 300_000_000); print('corrupt payload: jumped', st.get('jumped'), 'pc', hex(st['pc']), 'LED tail', st['led'][-11:])
