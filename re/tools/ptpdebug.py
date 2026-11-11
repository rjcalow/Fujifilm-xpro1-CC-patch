"""PC client for the X-Pro1 USB debug firmware (build_ptpdebug.py). Plain PTP over USB bulk, needs pyusb + libusb.
usage:
  ptpdebug.py info                         device info + whether the debug operations answer
  ptpdebug.py peek ADDR LEN [-o FILE]      read memory (hex dump, or raw to FILE)
  ptpdebug.py poke ADDR VALUE              write one 32-bit word
  ptpdebug.py call ADDR [R0]               call a function, print r0
  ptpdebug.py dumprom OUT.bin              boot ROM 0x80000000..0x80003fff (16 KiB), with sha256
The camera must be in its PTP USB mode and no other program (gphoto2/gvfs) may hold it:
  gio mount -s gphoto2 ; pkill -f gvfs-gphoto2-volume-monitor   (if "Resource busy")
"""
import hashlib, struct, sys
import usb.core, usb.util

VID = 0x04cb
PEEK, POKE, CALL = 0x9010, 0x9011, 0x9012
RESULT = 0xf45c04                       # CALL result slot (build_ptpdebug.handlers)
CHUNK = 0x4000


class PTP:
    def __init__(self):
        dev = usb.core.find(idVendor=VID)
        if dev is None: sys.exit('No Fujifilm USB device (04cb:*) found. Camera on, USB cable, PTP mode?')
        self.dev = dev
        cfg = dev.get_active_configuration()
        intf = next(i for i in cfg if i.bInterfaceClass == 6)            # still image class
        try:
            if dev.is_kernel_driver_active(intf.bInterfaceNumber): dev.detach_kernel_driver(intf.bInterfaceNumber)
        except (NotImplementedError, usb.core.USBError): pass
        usb.util.claim_interface(dev, intf.bInterfaceNumber)
        ep = lambda d, t: next(e for e in intf if usb.util.endpoint_direction(e.bEndpointAddress) == d
                               and usb.util.endpoint_type(e.bmAttributes) == t)
        self.out = ep(usb.util.ENDPOINT_OUT, usb.util.ENDPOINT_TYPE_BULK)
        self.inp = ep(usb.util.ENDPOINT_IN, usb.util.ENDPOINT_TYPE_BULK)
        self.tid = 0
        print(f'device {dev.idVendor:04x}:{dev.idProduct:04x} {usb.util.get_string(dev, dev.iProduct)!r}')

    def _read_container(self, timeout=10000):
        buf = bytes(self.inp.read(0x10000 + 12 + 512, timeout=timeout))
        length, typ, code, tid = struct.unpack('<IHHI', buf[:12])
        while len(buf) < length:
            buf += bytes(self.inp.read(0x10000 + 512, timeout=timeout))
        return typ, code, tid, buf[12:length]

    def op(self, code, *params, data_in=False):
        self.tid += 1
        self.out.write(struct.pack('<IHHI', 12 + 4 * len(params), 1, code, self.tid)
                       + b''.join(struct.pack('<I', p & 0xffffffff) for p in params), timeout=5000)
        data = b''
        typ, rcode, tid, payload = self._read_container()
        if typ == 2:
            data = payload
            typ, rcode, tid, payload = self._read_container()
        if typ != 3: raise RuntimeError(f'unexpected container type {typ}')
        return rcode, data, struct.unpack(f'<{len(payload) // 4}I', payload[:len(payload) // 4 * 4])

    def open(self):
        r, _, _ = self.op(0x1002, 1)
        if r not in (0x2001, 0x201e): raise RuntimeError(f'OpenSession → {r:#06x}')

    def peek(self, addr, n):
        out = b''
        while n > 0:
            k = min(n, CHUNK)
            r, data, _ = self.op(PEEK, addr, k)
            if r != 0x2001: raise RuntimeError(f'PEEK {addr:#x} → response {r:#06x} (0x2005 = stock firmware, no debug ops)')
            if len(data) != k: raise RuntimeError(f'PEEK {addr:#x}: got {len(data)} bytes, asked {k}')
            out += data; addr += k; n -= k
        return out


def main(a):
    if not a: sys.exit(__doc__)
    p = PTP(); p.open()
    cmd = a[0]
    if cmd == 'info':
        r, data, _ = p.op(0x1001)
        print('GetDeviceInfo', hex(r), len(data), 'bytes')
        r, data, _ = p.op(PEEK, RESULT & ~0xfff, 16)
        print('debug PEEK:', 'works' if r == 0x2001 and len(data) == 16 else f'not available (response {r:#06x})')
    elif cmd == 'peek':
        addr, n = int(a[1], 0), int(a[2], 0); d = p.peek(addr, n)
        if '-o' in a: open(a[a.index('-o') + 1], 'wb').write(d); print(f'{len(d)} bytes → {a[a.index("-o") + 1]}')
        else:
            for i in range(0, len(d), 16): print(f'{addr + i:08x}  {d[i:i + 16].hex(" ")}')
    elif cmd == 'poke':
        r, _, _ = p.op(POKE, int(a[1], 0), int(a[2], 0)); print('POKE →', hex(r))
    elif cmd == 'call':
        r, _, _ = p.op(CALL, int(a[1], 0), int(a[2], 0) if len(a) > 2 else 0)
        print('CALL →', hex(r), 'r0 =', hex(struct.unpack('<I', p.peek(RESULT, 4))[0]))
    elif cmd == 'dumprom':
        d = p.peek(0x80000000, 0x4000); open(a[1], 'wb').write(d)
        print(f'boot ROM {len(d)} bytes → {a[1]}  sha256 {hashlib.sha256(d).hexdigest()}')
        print('fujimod EXR/EXR Pro ROM sha256 7dc7e332a90802d9069d54be4487df0cc731820c9942692245e9ce5a5cec31d7')
    p.op(0x1003)


if __name__ == '__main__':
    main(sys.argv[1:])
