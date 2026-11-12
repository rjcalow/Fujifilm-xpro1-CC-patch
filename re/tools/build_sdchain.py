# SD chain boot for the X-Pro1 (3.82): ffsys.bin + ffboot.bin, no ffuser.bin and no ROM file-API calls.
# ffboot.bin = our stub (re/sdchain, cross-compiled) + raw-DEFLATE of the stock boot loader (file 0x4025c, 0x40000 B).
# The stub (run by the boot ROM after Fn + command-dial press at power-on) relocates to DRAM 0x41f00000, inflates the
# loader to address 0, checks its CRC32 and jumps to 0: the camera then boots normally from flash.
# usage: build_sdchain.py <FPUPDATE.DAT> <chain.bin (compiled stub)> <outdir> [--markers | --trace | --hook | --sec0trap]
#   --sec0trap: diagnostic; --hook (with LED feedback) + section 0 exception reporter (sec0_trap.py)
#   --sec0cp: --sec0trap + LED checkpoints before section 0's five start-up calls (sec0_cp.py)
#   --crumbs: breadcrumbs in DRAM instead of LED (crumbs.py); use with the chain_crumbs.bin stub; read: sdcrumbs.py
#   --uiswap: with --crumbs, swap red/green in every UI colour record at stage B (green menu accent)
#   --cc: with --crumbs, Classic Chrome v3 chroma values + menu name CLASSIC CHROME through run-time hooks (cchook.py);
#         the flash firmware must be a v2 build (ccswap_v2 or ptpdebug_385)
#   --hook: production; patch the loaded firmware in RAM before it starts (loader_hook.py; default: Ver3.89 marker)
#   --markers: patch LED progress markers into the RAM copy of the stock loader (needs keystone-engine):
#     loader main reached → GREEN; loader finished, jumping to the firmware → GREEN + ORANGE;
#     loader error handler (0x450c) → ORANGE blinking. Trampolines live in unused 0xff filler at loader 0x9000.
import hashlib, os, struct, sys, zlib
args = sys.argv[1:]; markers = '--markers' in args; trace = '--trace' in args; hook = '--hook' in args
sec0cp = '--sec0cp' in args; uiswap = '--uiswap' in args; cc = '--cc' in args; sec0trap = '--sec0trap' in args or sec0cp; crumbs = '--crumbs' in args
for f in ('--markers', '--trace', '--hook', '--sec0trap', '--sec0cp', '--crumbs', '--uiswap', '--cc'):
    if f in args: args.remove(f)
dat, stub_path, out = args[:3]
raw = open(dat, 'rb').read(); img = bytes(x ^ 0xff for x in raw)
loader = img[0x4025c:0x4025c + 0x40000]
assert hashlib.sha256(loader).hexdigest() == 'ff31ef67c7b024a33ea3757cbff3d9564618c9660a90bbbbfecffaf6a31f24a7', 'loader differs from 3.82'
if crumbs:
    sys.path.insert(0, os.path.dirname(__file__)); import crumbs as crumbs_mod
    L = bytearray(loader); info = crumbs_mod.patch(L, img[0x8025c:0x8025c + 0xd7a0], uiswap=uiswap, cc_img=img if cc else None); loader = bytes(L)
    print('crumbs:', info)
    stub_check = open(stub_path, 'rb').read()
    assert struct.pack('<2I', 0xfff44024, 0xfff44028) in stub_check, '--crumbs needs the chain_crumbs.bin stub (-DCRUMBS)'
if hook or sec0trap:
    sys.path.insert(0, os.path.dirname(__file__)); import loader_hook
    L = bytearray(loader)
    if sec0trap:
        import sec0_trap
        info = loader_hook.patch(L, diag=True, stage_b_call=sec0_trap.RESTORE)
        info.update(sec0_trap.patch(L, img[0x8025c:0x8025c + 0xd7a0]))
        if sec0cp:
            import sec0_cp
            info.update(sec0_cp.patch(L, img[0x8025c:0x8025c + 0xd7a0], sec0_trap.PRE))
    else:
        info = loader_hook.patch(L)
    loader = bytes(L)
    print('hook:', {k: hex(v) for k, v in info.items()})
if trace:
    sys.path.insert(0, os.path.dirname(__file__)); import loader_trace
    L = bytearray(loader); info = loader_trace.patch(L); loader = bytes(L)
    print('trace patches:', {k: hex(v) for k, v in info.items()})
if markers and not trace:
    from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM
    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)
    asm = lambda src, at: bytes(ks.asm(src, at)[0])
    L = bytearray(loader); T = 0x9000
    assert all(b == 0xff for b in L[0x8000:0x10000]), 'trampoline area is not free filler'
    word = lambda a: struct.unpack('<I', L[a:a + 4])[0]
    assert word(0x4044) == 0xeb0001d6 and word(0x405c) == 0xe1a0f003 and word(0x450c) == 0xe92d4800, 'unexpected loader code'
    tramp = '''
    t_main:                                 /* green on, orange off; then the real main (lr = 0x4048) */
        push {r0, r1, r2, r3, lr}
        movw r1, #0x93c0
        movt r1, #0xfff8
        movw r2, #0x0001
        movt r2, #0x0005
        str r2, [r1]
        pop {r0, r1, r2, r3, lr}
        b 0x47a4
    t_final:                                /* green + orange on; then start the firmware (r0 = arg, r3 = entry) */
        push {r1, r2}
        movw r1, #0x93c0
        movt r1, #0xfff8
        mov r2, #0x00050000
        str r2, [r1]
        pop {r1, r2}
        mov pc, r3
    t_err:                                  /* orange blinking forever, green off */
        movw r1, #0x93c0
        movt r1, #0xfff8
    e0: movw r2, #0x0004
        movt r2, #0x0005
        str r2, [r1]
        movw r3, #0x0000
        movt r3, #0x0100
    e1: subs r3, r3, #1
        bne e1
        movw r2, #0x0005
        movt r2, #0x0005
        str r2, [r1]
        movw r3, #0x0000
        movt r3, #0x0100
    e2: subs r3, r3, #1
        bne e2
        b e0
    '''
    code = asm(tramp, T)
    L[T:T + len(code)] = code
    t_main, t_final, t_err = T, T + 4 * 8, T + 4 * 15
    L[0x4044:0x4048] = asm(f'bl {t_main:#x}', 0x4044)
    L[0x405c:0x4060] = asm(f'b {t_final:#x}', 0x405c)
    L[0x450c:0x4510] = asm(f'b {t_err:#x}', 0x450c)
    loader = bytes(L)
    print(f'markers: trampolines {len(code)} B at {T:#x}; patched 0x4044 → {t_main:#x}, 0x405c → {t_final:#x}, 0x450c → {t_err:#x}')
c = zlib.compressobj(9, zlib.DEFLATED, -15, 9); payload = c.compress(loader) + c.flush()
stub = bytearray(open(stub_path, 'rb').read())
m = bytes(stub).find(struct.pack('<I', 0x4e494843)); cfg = m - 0x14
assert m > 0 and bytes(stub).count(struct.pack('<I', 0x4e494843)) == 1 and stub[cfg:m] == bytes(20), 'stub config block not found'
stub += bytes(-len(stub) % 4)
off = len(stub); total = off + len(payload); total += -total % 4
struct.pack_into('<5I', stub, cfg, total, off, len(payload), len(loader), zlib.crc32(loader) & 0xffffffff)
ffboot = bytes(stub) + payload + bytes(total - off - len(payload))
assert len(ffboot) < 0x10000, f'ffboot {len(ffboot)} bytes: the ROM reads only 16 bits of the length'
ffsys = bytearray(img[0x25c:0x25c + 512])
assert hashlib.sha256(ffsys).hexdigest() == '83a3fc5e9e88e6eda0dacb8657cb4c8a83163f2df846bff250b53368e28c9a24'
ffsys[16:20] = struct.pack('<I', 0x301)
os.makedirs(out, exist_ok=True)
for n, b in (('ffsys.bin', bytes(ffsys)), ('ffboot.bin', ffboot)):
    open(os.path.join(out, n), 'wb').write(b); print(f'wrote {n} {len(b)} bytes sha256 {hashlib.sha256(b).hexdigest()}')
print(f'stub {off} B, payload {len(payload)} B (loader 0x40000, crc {zlib.crc32(loader) & 0xffffffff:#010x})')
