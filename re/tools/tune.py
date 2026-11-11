"""Live Classic Chrome tuning over USB (X-Pro1 with the debug firmware from build_ptpdebug.py).

The camera's image-processing parameter area is in RAM at 0x40d3b580 + ID (filled from flash at start-up). Changes
made here last until the camera is switched off and are used by the next shot / in-camera RAW conversion (NOTES
2026-11-11). Workflow: connect USB → tune.py set ... → unplug → convert the same RAW in camera → compare_jpeg.py.

usage (run with ~/.venvs/xpro1-re/bin/python):
  tune.py show [GROUP|all]                 live vs flashed vs stock values (matrices decoded as ×1024 fixed point)
  tune.py get ID [N]                       raw live bytes
  tune.py set ID HEXBYTES                  write bytes (e.g. set 0xe4ec 02)
  tune.py setm GROUP NAME VALUE            one matrix entry as a number (e.g. setm cc3x3 m01 -0.05)
  tune.py setmat GROUP v00 v01 ... v22     whole 3x3 (or 2x2: m00 m01 m10 m11) as numbers
  tune.py restore [GROUP|all]              back to the flashed (v2) values: one group, or every CC parameter and
                                           every ID written in this camera session (from the log)
  tune.py diff                             every live byte that differs from flash (per-camera ranges excluded)
  tune.py lut FILE.cube [--dry-run]        load a 3D LUT's best camera approximation into PRO Neg. Std (see below)
  tune.py selftest                         offline test against a fake camera
Groups: cc3x3 (sRGB, preset 5), cc3x3alt (preset 10), cc2x2 (chroma 2x2), chromagain, detail, hstone, curveno
(PRO Neg Hi = Classic Chrome); ns3x3, ns3x3alt, ns2x2, nssel, nscurveno (PRO Neg Std, used by `lut`).
`lut`: the camera has no 3D-LUT stage. lut_fit.camera_fit_opt fits one 3x3 matrix + one 27-knot tone curve so that
PRO Neg Std ≈ LUT(PROVIA) and prints the expected error. It then writes PRO Neg Std's own presets (3x3 sRGB/alt,
2x2 := PROVIA's, chroma gain/detail/H-S selectors := PROVIA's) and puts the curve into the unreferenced curve slot #41
(blob1 RAM 0x80baa8), pointing PRO Neg Std's 42 curve selectors at it (the curve-16 special-mode ones stay).
PROVIA and PRO Neg Hi are untouched, so one RAW converted three ways compares baseline / Classic Chrome port / LUT.
Safety: before writing, the live value must equal the flashed value or the value this tool last wrote (else --force).
Writes into per-camera calibration ranges and outside IDs 0..0xffff are refused (unless --force). Every write is
logged to re/work/tune_log.jsonl. Switching the camera off restores everything.
"""
import json, os, struct, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, 'public'))
DB_RAM = 0x40d3b580
DB_FILE = 0xae025c
DB_LEN = 0x10000
INSTALLED = os.path.join(ROOT, 're', 'build', 'ptpdebug_385', 'FPUPDATE.DAT')   # firmware on the camera
STOCK = os.path.join(ROOT, 'FPUPDATE.DAT')                                       # official 3.82
LOG = os.path.join(ROOT, 're', 'work', 'tune_log.jsonl')
# per-camera data the firmware lays over the area at start-up (measured 2026-11-10): never write here by default
PROTECTED = [(0x0000, 0x0400), (0x0cb0, 0x0d90), (0x1660, 0x2840), (0x4b70, 0x4d70)]
M3 = ['m00', 'm01', 'm02', 'm10', 'm11', 'm12', 'm20', 'm21', 'm22']
GROUPS = {
    'cc3x3':    ('matrix', [0xdb4b + 2 * k for k in range(9)], M3),
    'cc3x3alt': ('matrix', [0xdba5 + 2 * k for k in range(9)], M3),
    'cc2x2':    ('matrix', [0xe3c9, 0xe3cd, 0xe3cf, 0xe3cb], ['m00', 'm01', 'm10', 'm11']),
    'chromagain': ('byte', [0xe4ec], ['preset']),
    'detail':   ('byte', [0xffc6], ['preset']),
    'hstone':   ('byte', [0xe13b], ['preset']),
    'curveno':  ('byte', list(range(0xde13, 0xde25)) + list(range(0xde91, 0xdea3)) + [0xdf91, 0xdf98, 0xdf9f, 0xdfad],
                 None),
    # PRO Neg Std (colour mode 6): presets 4 / 9 / 2x2 4 are used by no other film simulation (2026-11-11)
    'ns3x3':    ('matrix', [0xdb39 + 2 * k for k in range(9)], M3),
    'ns3x3alt': ('matrix', [0xdb93 + 2 * k for k in range(9)], M3),
    'ns2x2':    ('matrix', [0xe3c1, 0xe3c5, 0xe3c7, 0xe3c3], ['m00', 'm01', 'm10', 'm11']),
    'nssel':    ('byte', [0xe13a, 0xe4eb, 0xffc5], None),      # H/S family plane 0, chroma gain, detail selectors
    'nscurveno': ('byte', list(range(0xde01, 0xde13)) + list(range(0xde7f, 0xde91)) +
                  [0xdf90, 0xdf97, 0xdf9e, 0xdfa5, 0xdfac, 0xdfb3], None),
}
PROVIA = {'3x3': [0xdb03 + 2 * k for k in range(9)], '3x3alt': [0xdb5d + 2 * k for k in range(9)],
          '2x2': [0xe3a9, 0xe3ad, 0xe3af, 0xe3ab], 'hs': 0xe137, 'chromagain': 0xe4e8, 'detail': 0xfff0}
CURVE0 = 0x80b700                                   # blob1 RAM: tone-curve table entry #0 (PROVIA)
SLOT41 = 0x80baa8                                   # entry #41: referenced by nothing (checked 2026-11-11)
SLOT41_KNOTS = SLOT41 + 16                          # 27 × u16 knots, then the u16 0 terminator (left alone)
SLOT41_FLASHED = bytes.fromhex('0802c30206042505330634073809110bca0c3c102e13ca15f91ad51e38228e2544289a2afb2cdd2e'
                               'a6302134d0364c39c13b073eff3f')


def s13(v): v &= 0x1fff; return v - 0x2000 if v & 0x1000 else v
def enc13(x):
    v = int(round(x * 1024))
    if not -4096 <= v <= 4095: sys.exit(f'{x} is outside the 13-bit range (-4.0 .. +3.999)')
    return v & 0x1fff


def area(path):
    raw = open(path, 'rb').read()
    return bytes(255 - x for x in raw[DB_FILE:DB_FILE + DB_LEN])


class Tuner:
    def __init__(self, dev, flashed, stock, log=LOG):
        self.dev, self.flashed, self.stock, self.log = dev, flashed, stock, log

    # --- memory access (byte granular on top of 32-bit PEEK/POKE)
    def read(self, pid, n):
        a = (DB_RAM + pid) & ~3; end = (DB_RAM + pid + n + 3) & ~3
        blk = self.dev.peek(a, end - a); o = DB_RAM + pid - a
        return blk[o:o + n]

    def _write(self, pid, data):
        a = (DB_RAM + pid) & ~3; end = (DB_RAM + pid + len(data) + 3) & ~3
        blk = bytearray(self.dev.peek(a, end - a)); o = DB_RAM + pid - a
        blk[o:o + len(data)] = data
        for w in range(0, len(blk), 4):
            self.dev.poke(a + w, struct.unpack('<I', blk[w:w + 4])[0])
        if self.read(pid, len(data)) != bytes(data): raise RuntimeError(f'read-back mismatch at {pid:#x}')

    def last_written(self):
        out = {}
        if os.path.exists(self.log):
            for line in open(self.log):
                e = json.loads(line)
                if e.get('boot') != self.boot_id() or 'id' not in e: continue
                for i, b in enumerate(bytes.fromhex(e['new'])): out[e['id'] + i] = b
        return out

    def boot_id(self):
        # identifies one camera power-on, so that "last written by tune.py" never refers to an earlier session
        return getattr(self, '_boot', None) or self._mark_boot()

    def _mark_boot(self):
        # session marker in RAM: the CALL result slot 0xf45c04 (unused by tune.py) is 0 after power-on; the first
        # tune.py run of a session stores a time-based tag there
        cur = struct.unpack('<I', self.dev.peek(0xf45c04, 4))[0]
        if cur == 0:
            cur = (int(time.time()) & 0xffffff) | 0x7e000000
            self.dev.poke(0xf45c04, cur)
        self._boot = f'{cur:08x}'
        return self._boot

    def set(self, pid, data, force=False, why=''):
        data = bytes(data)
        if not force:
            if not (0 <= pid and pid + len(data) <= DB_LEN): sys.exit(f'ID {pid:#x}+{len(data)} outside 0..0xffff (--force)')
            for lo, hi in PROTECTED:
                if pid < hi and pid + len(data) > lo: sys.exit(f'ID {pid:#x} is in per-camera data {lo:#x}-{hi:#x} (--force)')
        live = self.read(pid, len(data)); known = self.last_written()
        for i, b in enumerate(live):
            ok = b == self.flashed[pid + i] or known.get(pid + i) == b
            if not ok and not force:
                sys.exit(f'live byte at {pid + i:#x} is {b:#04x}: neither flashed ({self.flashed[pid + i]:#04x}) nor last '
                         f'written by tune.py; refusing (--force to override)')
        self._write(pid, data)
        os.makedirs(os.path.dirname(self.log), exist_ok=True)
        with open(self.log, 'a') as f:
            f.write(json.dumps({'t': time.strftime('%Y-%m-%d %H:%M:%S'), 'boot': self.boot_id(), 'id': pid,
                                'old': live.hex(), 'new': data.hex(), 'why': why}) + '\n')
        print(f'{pid:#06x}: {live.hex()} → {data.hex()}  {why}')

    # --- tone-curve slot #41 (blob1 RAM, outside the parameter area)
    def slot_knots(self):
        return list(struct.unpack('<27H', self.dev.peek(SLOT41_KNOTS, 56)[:54]))

    def set_slot(self, knots, why=''):
        data = struct.pack('<27H', *[int(k) for k in knots])
        live = self.dev.peek(SLOT41_KNOTS, 56)[:54]
        assert struct.unpack('<I', self.dev.peek(SLOT41, 4))[0] == 41, 'curve slot #41 not where expected'
        if live != SLOT41_FLASHED and live != self.last_slot():
            sys.exit('curve slot #41 holds neither its flashed knots nor the last ones tune.py wrote; refusing')
        blk = bytearray(self.dev.peek(SLOT41_KNOTS, 56)); blk[:54] = data
        for w in range(0, 56, 4): self.dev.poke(SLOT41_KNOTS + w, struct.unpack('<I', blk[w:w + 4])[0])
        if self.dev.peek(SLOT41_KNOTS, 56)[:54] != data: raise RuntimeError('curve slot read-back mismatch')
        with open(self.log, 'a') as f:
            f.write(json.dumps({'t': time.strftime('%Y-%m-%d %H:%M:%S'), 'boot': self.boot_id(), 'addr': SLOT41_KNOTS,
                                'old': live.hex(), 'new': data.hex(), 'why': why}) + '\n')
        print(f'curve slot #41 knots: {struct.unpack("<3H", live[:6])}… → {tuple(knots[:3])}…  {why}')

    def last_slot(self):
        last = None
        if os.path.exists(self.log):
            for line in open(self.log):
                e = json.loads(line)
                if e.get('boot') == self.boot_id() and e.get('addr') == SLOT41_KNOTS: last = bytes.fromhex(e['new'])
        return last

    def matrix(self, ids, src=None):
        import numpy as np
        get = (lambda i: self.read(i, 2)) if src is None else (lambda i: src[i:i + 2])
        return np.array([s13(struct.unpack('<H', get(i))[0]) / 1024 for i in ids])

    def lut(self, path, dry=False):
        import numpy as np, lut_fit
        M_P = self.matrix(PROVIA['3x3'], self.flashed).reshape(3, 3)
        M_Palt = self.matrix(PROVIA['3x3alt'], self.flashed).reshape(3, 3)
        k0 = struct.unpack('<27H', self.dev.peek(CURVE0 + 16, 56)[:54])
        assert struct.unpack('<I', self.dev.peek(CURVE0, 4))[0] == 0, 'curve table entry #0 not where expected'
        print(f'fitting {os.path.basename(path)} to PROVIA (matrix preset 1, curve #0) ...')
        M, kn, st = lut_fit.camera_fit_opt(path, M_P, k0)
        for k, (m, p) in st.items(): print(f'  ΔE76 {k:22s} median {m:5.2f}  p90 {p:5.2f}')
        Malt = M @ np.linalg.inv(M_P) @ M_Palt
        print('  3x3 sRGB', np.round(M, 4).tolist()); print('  3x3 alt ', np.round(Malt, 4).tolist())
        print('  curve knots', [int(v) for v in kn])
        if dry: print('dry run: nothing written'); return
        name = os.path.basename(path)
        self.set_slot(kn, f'lut {name}: tone curve')
        for grp, mat in (('ns3x3', M), ('ns3x3alt', Malt)):
            for nm, v in zip(M3, mat.reshape(-1)): self.setm(grp, nm, float(v))
        for i, src in zip(GROUPS['ns2x2'][1], PROVIA['2x2']):
            self.set(i, self.flashed[src:src + 2], why=f'lut {name}: 2x2 := PROVIA')
        for dst, src in ((0xe13a, PROVIA['hs']), (0xe4eb, PROVIA['chromagain']), (0xffc5, PROVIA['detail'])):
            self.set(dst, self.flashed[src:src + 1], why=f'lut {name}: selector := PROVIA')
        for i in GROUPS['nscurveno'][1]:
            if self.flashed[i] != 16: self.set(i, b'\x29', why=f'lut {name}: curve selector → #41')
        print('done: select PRO Neg. Std (or convert a RAW with it). `tune.py restore all` or power-off undoes it.')

    # --- groups
    def show(self, name):
        kind, ids, names = GROUPS[name]
        print(f'[{name}]')
        if kind == 'matrix':
            for nm, pid in zip(names, ids):
                v = [struct.unpack('<H', self.read(pid, 2))[0]] + \
                    [struct.unpack('<H', src[pid:pid + 2])[0] for src in (self.flashed, self.stock)]
                mark = '' if v[0] == v[1] else '   ← changed live'
                print(f'  {nm} id {pid:#06x}: live {s13(v[0]) / 1024:+.4f}  flashed {s13(v[1]) / 1024:+.4f}  '
                      f'stock {s13(v[2]) / 1024:+.4f}{mark}')
        else:
            live = self.read(ids[0], ids[-1] - ids[0] + 1)
            for pid in ids:
                l = live[pid - ids[0]]; mark = '' if l == self.flashed[pid] else '   ← changed live'
                print(f'  id {pid:#06x}: live {l}  flashed {self.flashed[pid]}  stock {self.stock[pid]}{mark}')

    def setm(self, name, entry, value, force=False):
        kind, ids, names = GROUPS[name]
        if kind != 'matrix': sys.exit(f'{name} is not a matrix group')
        pid = ids[names.index(entry)]
        self.set(pid, struct.pack('<H', enc13(value)), force, f'{name} {entry} = {value:+.4f}')

    def restore(self, name):
        targets = set()
        if name == 'all':
            for g in GROUPS.values():
                for pid in g[1]: targets.update(range(pid, pid + (2 if g[0] == 'matrix' else 1)))
            targets.update(self.last_written())
        else:
            g = GROUPS[name]
            for pid in g[1]: targets.update(range(pid, pid + (2 if g[0] == 'matrix' else 1)))
        n = 0
        for pid in sorted(targets):
            if self.read(pid, 1)[0] != self.flashed[pid]:
                self.set(pid, self.flashed[pid:pid + 1], force=True, why='restore'); n += 1
        if name == 'all' and self.dev.peek(SLOT41_KNOTS, 56)[:54] != SLOT41_FLASHED:
            self.set_slot(struct.unpack('<27H', SLOT41_FLASHED), why='restore'); n += 1
        print(f'restored {n} byte(s) to the flashed values')

    def diff(self):
        live = self.dev.peek(DB_RAM, DB_LEN)
        d = [i for i in range(DB_LEN) if live[i] != self.flashed[i] and not any(lo <= i < hi for lo, hi in PROTECTED)]
        if self.dev.peek(SLOT41_KNOTS, 56)[:54] != SLOT41_FLASHED: print('  curve slot #41: knots changed live')
        if not d: print('live area = flashed (outside per-camera ranges)'); return
        for i in d: print(f'  {i:#06x}: live {live[i]:#04x}  flashed {self.flashed[i]:#04x}  stock {self.stock[i]:#04x}')


class USB:
    def __init__(self):
        import ptpdebug
        self.p = ptpdebug.PTP(); self.p.open(); self.POKE = ptpdebug.POKE

    def peek(self, a, n): return self.p.peek(a, n)

    def poke(self, a, v):
        r, _, _ = self.p.op(self.POKE, a, v)
        if r != 0x2001: raise RuntimeError(f'POKE {a:#x} → {r:#06x}')


class Fake:
    B1 = 0x774000

    def __init__(self, flashed):
        self.db = bytearray(flashed); self.slot = 0
        self.b1 = bytearray(open(os.path.join(ROOT, 're', 'work', 'blob1.bin'), 'rb').read())

    def peek(self, a, n):
        if a == 0xf45c04: return struct.pack('<I', self.slot)
        if self.B1 <= a < self.B1 + len(self.b1): return bytes(self.b1[a - self.B1:a - self.B1 + n])
        return bytes(self.db[a - DB_RAM:a - DB_RAM + n])

    def poke(self, a, v):
        if a == 0xf45c04: self.slot = v; return
        if self.B1 <= a < self.B1 + len(self.b1): self.b1[a - self.B1:a - self.B1 + 4] = struct.pack('<I', v); return
        self.db[a - DB_RAM:a - DB_RAM + 4] = struct.pack('<I', v)


def selftest():
    import tempfile
    flashed, stock = area(INSTALLED), area(STOCK)
    fake = Fake(flashed); log = os.path.join(tempfile.mkdtemp(), 'log.jsonl')
    t = Tuner(fake, flashed, stock, log)
    t.set(0xe4ec, b'\x02'); assert fake.db[0xe4ec] == 2 and fake.db[0xe4ed] == flashed[0xe4ed]
    t.set(0xe4ec, b'\x03')                                     # second write allowed (last written by us)
    t.setm('cc3x3', 'm01', -0.05)                              # odd ID, crosses a word boundary
    assert struct.unpack('<H', bytes(fake.db[0xdb4d:0xdb4f]))[0] == enc13(-0.05)
    assert bytes(fake.db[0xdb4b:0xdb4d]) == flashed[0xdb4b:0xdb4d] and bytes(fake.db[0xdb4f:0xdb51]) == flashed[0xdb4f:0xdb51]
    fake.db[0xe13b] ^= 0xff                                    # someone else changed it → refuse
    try: t.set(0xe13b, b'\x01'); raise AssertionError('should refuse')
    except SystemExit as e: assert 'refusing' in str(e)
    fake.db[0xe13b] ^= 0xff
    for pid in (0x0003, 0x1700):                               # protected per-camera ranges
        try: t.set(pid, b'\x00'); raise AssertionError('should refuse protected')
        except SystemExit as e: assert 'per-camera' in str(e)
    t.restore('all'); assert bytes(fake.db) == flashed
    t.show('cc3x3'); t.show('chromagain'); t.diff()
    # full LUT load into PRO Neg Std, then restore
    b1_before = bytes(fake.b1)
    t.lut(os.path.join(ROOT, 'luts', 'ColorReps-classic-chrome.cube'))
    assert struct.unpack('<27H', fake.b1[SLOT41_KNOTS - Fake.B1:SLOT41_KNOTS - Fake.B1 + 54]) != struct.unpack('<27H', SLOT41_FLASHED)
    sel = GROUPS['nscurveno'][1]
    assert all(fake.db[i] == (16 if flashed[i] == 16 else 41) for i in sel), 'curve selectors'
    assert fake.db[0xe13a] == flashed[0xe137] and fake.db[0xe4eb] == flashed[0xe4e8] and fake.db[0xffc5] == flashed[0xfff0]
    assert [fake.db[i:i + 2] for i in GROUPS['ns2x2'][1]] == [flashed[i:i + 2] for i in PROVIA['2x2']]
    untouched = PROVIA['3x3'] + PROVIA['3x3alt'] + GROUPS['cc3x3'][1] + GROUPS['cc2x2'][1] + GROUPS['curveno'][1] + [0xe4ec, 0xe13b, 0xffc6]
    assert all(fake.db[i] == flashed[i] for i in untouched), 'PROVIA / PRO Neg Hi must not change'
    changed_b1 = [i for i in range(len(fake.b1)) if fake.b1[i] != b1_before[i]]
    assert changed_b1 and all(SLOT41_KNOTS - Fake.B1 <= i < SLOT41_KNOTS - Fake.B1 + 54 for i in changed_b1), 'blob1 writes only in slot #41 knots'
    t.diff(); t.restore('all')
    assert bytes(fake.db) == flashed and bytes(fake.b1) == b1_before, 'restore all → flashed'
    print('selftest OK')


def main(a):
    if not a or a[0] in ('-h', '--help'): sys.exit(__doc__)
    force = '--force' in a; a = [x for x in a if x != '--force']
    if a[0] == 'selftest': return selftest()
    t = Tuner(USB(), area(INSTALLED), area(STOCK))
    cmd = a[0]
    if cmd == 'show':
        for g in (GROUPS if len(a) < 2 or a[1] == 'all' else [a[1]]): t.show(g)
    elif cmd == 'get':
        pid = int(a[1], 0); n = int(a[2], 0) if len(a) > 2 else 1
        print(f'{pid:#06x}: live {t.read(pid, n).hex(" ")}  flashed {t.flashed[pid:pid + n].hex(" ")}')
    elif cmd == 'set': t.set(int(a[1], 0), bytes.fromhex(a[2]), force)
    elif cmd == 'setm': t.setm(a[1], a[2], float(a[3]), force)
    elif cmd == 'setmat':
        _, ids, names = GROUPS[a[1]]; vals = [float(x) for x in a[2:]]
        if len(vals) != len(names): sys.exit(f'{a[1]} needs {len(names)} values in order {" ".join(names)}')
        for nm, v in zip(names, vals): t.setm(a[1], nm, v, force)
    elif cmd == 'restore': t.restore(a[1] if len(a) > 1 else 'all')
    elif cmd == 'diff': t.diff()
    elif cmd == 'lut': t.lut(a[1], dry='--dry-run' in a)
    else: sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
