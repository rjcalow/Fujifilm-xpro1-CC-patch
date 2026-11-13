"""Read memory from an X-Pro1 running the ROM dump card (build_dumpcard.py) over USB. Read-only: the only debug
operation used is PTP 0x9010 PEEK. Standalone; needs Python 3 + pyusb (pip install pyusb) and libusb.

usage:
  romdump.py info                          what is running: dump card (and its hook status) / debug firmware / stock
  romdump.py rom [OUT.bin]                 the 16 KiB boot ROM at 0x80000000, read twice and compared, with sha256
                                           (default OUT: xpro1_bootrom.bin)
  romdump.py dump REGION OUT.bin           a named region (see REGIONS below)
  romdump.py peek ADDR LEN [-o OUT.bin]    any range: hex dump, or raw to a file
                                           (outside REGIONS only with --force)

Reading an address that nothing answers can hang the camera: take the battery out to recover (nothing is stored,
so nothing is lost). That is why addresses outside the known regions need --force.
The camera must be connected by USB in its PTP mode, and no other program may hold it. On Linux desktops:
  gio mount -s gphoto2 ; pkill -f gvfs-gphoto2-volume-monitor        (if you get "Resource busy")
"""
import hashlib, struct, sys, time
try:
    import usb.core, usb.util
except ImportError:
    sys.exit('needs pyusb: pip install pyusb (and libusb from your system)')

VID = 0x04cb                                    # Fujifilm
PEEK = 0x9010
CHUNK = 0x4000
ID_AT, STATUS_AT = 0xb000, 0xb01c               # build_dumpcard.py: ID block and hook status in the loader filler
ID = b'XPRO1 ROMDUMP\0\0\0'
ROM_AT, ROM_LEN = 0x80000000, 0x4000
# boot ROM of the X-Pro1, shared by the EXR / EXR Pro bodies (sha256 published by fujimod; matched on one X-Pro1)
ROM_SHA256 = '7dc7e332a90802d9069d54be4487df0cc731820c9942692245e9ce5a5cec31d7'
REGIONS = {                                     # name: (address, length, what)
    'rom':  (ROM_AT, ROM_LEN, 'boot ROM (mask ROM, 16 KiB)'),
    'ram':  (0x00000000, 0x02000000, 'low RAM 0..32 MiB: loader, firmware sections as running, UI data'),
    'dram': (0x40000000, 0x10000000, 'all DRAM, 256 MiB (~50 s; holds image buffers, possibly your photos)'),
}


class PTP:
    def __init__(self):
        dev = usb.core.find(idVendor=VID)
        if dev is None: sys.exit('No Fujifilm USB device (04cb:*) found. Camera on, USB cable in, PTP mode?')
        self.dev = dev
        cfg = dev.get_active_configuration()
        intf = next(i for i in cfg if i.bInterfaceClass == 6)            # still image class
        try:
            if dev.is_kernel_driver_active(intf.bInterfaceNumber): dev.detach_kernel_driver(intf.bInterfaceNumber)
        except (NotImplementedError, usb.core.USBError): pass
        usb.util.claim_interface(dev, intf.bInterfaceNumber)
        ep = lambda d: next(e for e in intf if usb.util.endpoint_direction(e.bEndpointAddress) == d
                            and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK)
        self.out, self.inp = ep(usb.util.ENDPOINT_OUT), ep(usb.util.ENDPOINT_IN)
        self.tid = 0
        print(f'device {dev.idVendor:04x}:{dev.idProduct:04x} {usb.util.get_string(dev, dev.iProduct)!r}')

    def _read_container(self, timeout=10000):
        buf = bytes(self.inp.read(0x10000 + 12 + 512, timeout=timeout))
        length, typ, code, tid = struct.unpack('<IHHI', buf[:12])
        while len(buf) < length:
            buf += bytes(self.inp.read(0x10000 + 512, timeout=timeout))
        return typ, code, tid, buf[12:length]

    def op(self, code, *params):
        self.tid += 1
        self.out.write(struct.pack('<IHHI', 12 + 4 * len(params), 1, code, self.tid)
                       + b''.join(struct.pack('<I', p & 0xffffffff) for p in params), timeout=5000)
        data = b''
        typ, rcode, tid, payload = self._read_container()
        if typ == 2:
            data = payload
            typ, rcode, tid, payload = self._read_container()
        if typ != 3: raise RuntimeError(f'unexpected container type {typ}')
        return rcode, data

    def open(self):
        r, _ = self.op(0x1002, 1)                                         # OpenSession
        if r not in (0x2001, 0x201e): raise RuntimeError(f'OpenSession → {r:#06x}')

    def close(self):
        self.op(0x1003)

    def try_peek(self, addr, n):
        r, data = self.op(PEEK, addr, n)
        return data if r == 0x2001 and len(data) == n else None

    def peek(self, addr, n, progress=False):
        out = []; done = 0; t = time.time()
        while done < n:
            k = min(n - done, CHUNK)
            r, data = self.op(PEEK, addr + done, k)
            if r == 0x2005: sys.exit('PEEK not supported: the camera is running its normal firmware (see romdump.py info)')
            if r != 0x2001 or len(data) != k: raise RuntimeError(f'PEEK {addr + done:#x}: response {r:#06x}, {len(data)} of {k} bytes')
            out.append(data); done += k
            if progress and done % 0x1000000 == 0: print(f'  {done >> 20} MiB  {time.time() - t:.0f} s', flush=True)
        return b''.join(out)


def known(addr, n):
    return any(a <= addr and addr + n <= a + ln for a, ln, _ in REGIONS.values())


def info(p):
    r, data = p.op(0x1001)                                                # GetDeviceInfo
    print(f'GetDeviceInfo: {r:#06x}, {len(data)} bytes')
    blk = p.try_peek(ID_AT, 0x20)
    if blk is None:
        print('PEEK: not available. The camera runs its normal firmware: SD dual boot did not start, or the hook')
        print('      did not run. Take the battery out, put it back, and switch on holding Fn + command-dial press.')
        return False
    if blk[:len(ID)] == ID:
        ver, status = struct.unpack('<I', blk[0x10:0x14])[0], struct.unpack('<I', blk[0x1c:0x20])[0]
        what = {1: 'enabled in RAM by the card', 2: 'answered by the flashed debug firmware (the card left its slot alone)'}
        print(f'ROM dump card v{ver} is running; PEEK {what.get(status, f"status {status:#x}")}')
    else:
        print('PEEK works, but no dump-card ID: a flashed USB debug firmware (re/tools/build_ptpdebug.py) is running')
    return True


def rom(p, out):
    a = p.peek(ROM_AT, ROM_LEN); b = p.peek(ROM_AT, ROM_LEN)
    if a != b: sys.exit('two reads of the boot ROM differ: USB problem? nothing written')
    open(out, 'wb').write(a); h = hashlib.sha256(a).hexdigest()
    print(f'boot ROM {len(a)} bytes → {out}\n  sha256 {h}')
    print('  matches the known X-Pro1 / EXR Pro boot ROM' if h == ROM_SHA256 else
          f'  DIFFERENT from the known X-Pro1 boot ROM ({ROM_SHA256[:16]}…): worth reporting (hash only)')


def main(a):
    force = '--force' in a; a = [x for x in a if x != '--force']
    if not a or a[0] not in ('info', 'rom', 'dump', 'peek'): sys.exit(__doc__ + '\nregions: ' + ', '.join(
        f'{k} ({v[0]:#x}, {v[1]:#x}: {v[2]})' for k, v in REGIONS.items()))
    p = PTP(); p.open()
    try:
        if a[0] == 'info': info(p)
        elif a[0] == 'rom': rom(p, a[1] if len(a) > 1 else 'xpro1_bootrom.bin')
        elif a[0] == 'dump':
            if len(a) != 3 or a[1] not in REGIONS: sys.exit('usage: romdump.py dump ' + '|'.join(REGIONS) + ' OUT.bin')
            addr, n, what = REGIONS[a[1]]
            print(f'{a[1]}: {what}'); d = p.peek(addr, n, progress=True); open(a[2], 'wb').write(d)
            print(f'{len(d)} bytes → {a[2]}  sha256 {hashlib.sha256(d).hexdigest()}')
        else:
            addr, n = int(a[1], 0), int(a[2], 0)
            if addr % 4 or n % 4 or n <= 0: sys.exit('address and length must be multiples of 4')
            if not known(addr, n) and not force: sys.exit(f'{addr:#x}+{n:#x} is outside the known regions; use --force '
                                                          'if you know it is readable (a bad address hangs the camera)')
            d = p.peek(addr, n)
            if '-o' in a: o = a[a.index('-o') + 1]; open(o, 'wb').write(d); print(f'{len(d)} bytes → {o}')
            else:
                for i in range(0, len(d), 16): print(f'{addr + i:08x}  {d[i:i + 16].hex(" ")}')
    finally:
        p.close()


if __name__ == '__main__':
    main(sys.argv[1:])
