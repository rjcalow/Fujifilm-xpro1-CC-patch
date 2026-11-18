"""Map every X-Pro1 menu (firmware 3.82) from the firmware itself: write re/MENU_MAP.md.

Static only (no camera). Reads:
  work/blob1.bin           blob1 at RAM 0x774000 (settings nodes, value lists, conversion tables)
  work/not.bin             decoded update image (module 0x41 at file 0x46025c -> RAM 0x1420000, language blocks)
  decompiled/xpro1_blob1_0x774000.c.gz   getter FUN_0078fb50 (where each setting is stored, bit width)
  decompiled/xpro1_mod41_0x1420000.c.gz  FUN_01476b8c / FUN_014796fc (screen kind -> page layout, item records)

What it combines (background and how to change things: re/MENUS.md):
  1. blob1 node tree: nodes {group, setting, widget type, flag, parent, list}; a list is (value, child node | 0)
     pairs ending 0x7ffffffe. Roots: main MENU 0x776b24, Q menu 0x776214 and four smaller ones.
  2. Conversion tables 0x78ba10[setting]: rows {c0 stored value, c1, c2 internal value}, end {0xffff x3}.
     A list value is a row number of its setting's table.
  3. Storage: FUN_0078fb50 is a switch with one case per setting reading a bit field of the settings bank
     (0x9caf00.. + bank*0x12a, image settings also + slot*7 for the custom-setting slot).
  4. Module 0x41 screens: per screen kind a page layout {count, (record, flag) x 7} per page (15 bytes, 4 variants
     of 0x60 bytes) and an item-record array {item, title text, graphic, flag, label table A, label table B}.
     A main-menu page node lists its items in screen order, so blob1 items and module 0x41 slots line up one to one
     once the always-hidden items (HIDDEN below) are skipped.

usage: ~/.venvs/xpro1-re/bin/python tools/menumap.py [--out MENU_MAP.md]     (run from re/)
"""
import argparse, gzip, os, re, struct, sys

RE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(RE, 'tools')); sys.path.insert(0, RE)
import uitext                                                    # noqa: E402

B1 = 0x774000
M41, M41_FILE, M41_SIZE = 0x1420000, 0x46025c, 0x80000
END = 0x7ffffffe
CONV_PTRS, CONV_N = 0x78ba10, 506

# Menu-page nodes and the module-0x41 screen kind that draws them (found by order alignment, MENUS.md §3).
PAGES = [  # (title, node, kind)
    ('SHOOTING MENU', 0x779754, 0x00),
    ('PLAYBACK MENU', 0x775a3c, 0x04),
    ('SET-UP MENU', 0x7765ec, 0x06),
]
# Items listed in the blob1 pages but never shown on this body (blob2 row-state calls with state 2/1, MENUS.md §5).
HIDDEN = {113: 'blob2 FUN_00f12184: FUN_00f0f2c8(5,0x71,2) in both branches',
          79: 'blob2 FUN_00f184b8: FUN_00f0f2c8(5,0x4f,2) unconditional',
          68: 'blob2 FUN_00f10220: FUN_00f0f2c8(5,0x44,2) unconditional',
          134: 'blob2 FUN_00f10220: FUN_00f0f2c8(5,0x86,1); no slot in the module-0x41 layout'}
OTHER_ROOTS = [
    ('Q MENU (Q button, 4x4)', 0x776214),
    ('ISO from a button (assumed: Fn / ISO shortcut)', 0x77758c),
    ('Reduced playback menu (probably unused: shared code)', 0x777624),
    ('Unknown root, setting 0x113 (probably unused)', 0x7793c4),
]
WIDGET = {1: 'menu root', 2: 'two-field', 3: 'sub-page (FS BKT)', 5: 'slider', 6: 'sub-page', 7: 'list',
          8: 'sub-page?', 10: 'slider 11', 11: 'slider 11', 16: 'Q grid', 19: 'grid (WB shift)', 42: 'text entry'}

# Names of settings below the main-menu items (from their sub-screen's records, value counts and labels).
SUB_NAMES = {
    0xfb: 'ISO AUTO CONTROL', 0xfc: 'ISO AUTO: DEFAULT SENSITIVITY', 0xfe: 'ISO AUTO: MAX. SENSITIVITY',
    0x100: 'ISO AUTO: MIN. SHUTTER SPEED', 0x95: 'custom ISO AUTO CONTROL', 0x96: 'custom ISO AUTO: DEFAULT SENS.',
    0x97: 'custom ISO AUTO: MAX. SENS.', 0x98: 'custom ISO AUTO: MIN. SHUTTER',
    0x3f: 'FILM SIMULATION BKT: FILM 1', 0x40: 'FILM SIMULATION BKT: FILM 2', 0x41: 'FILM SIMULATION BKT: FILM 3',
    0x4d: 'WB SHIFT (R/B grid)', 0x4e: 'WB SHIFT R (0x4e+2*WB mode)', 0x4f: 'WB SHIFT B (0x4f+2*WB mode)',
    0x131: 'COLOR TEMPERATURE (K)',
    0x93: 'EDIT/SAVE CUSTOM SETTING: C1..C7 page', 0xa2: 'custom: SAVE CURRENT SETTINGS', 0x94: 'custom: ISO',
    0x99: 'custom: DYNAMIC RANGE', 0x9a: 'custom: FILM SIMULATION', 0x9b: 'custom: WHITE BALANCE',
    0x9c: 'custom: COLOR TEMPERATURE', 0x9d: 'custom: COLOR', 0x9e: 'custom: SHARPNESS', 0x9f: 'custom: HIGHLIGHT TONE',
    0xa0: 'custom: SHADOW TONE', 0xa1: 'custom: NOISE REDUCTION',
    0xa7: 'MOUNT ADAPTOR: LENS 1..6 page', 0xa8: 'lens: FOCAL LENGTH', 0xa9: 'focal length digit 1',
    0xaa: 'focal length digit 2', 0xab: 'focal length digit 3', 0xb2: 'lens: DISTORTION CORRECTION',
    0xba: 'lens: COLOR SHADING (per corner)', 0xbb: 'colour shading axis 1', 0xbc: 'colour shading axis 2',
    0xed: 'lens: PERIPHERAL ILLUMINATION CORR.',
    0xd: 'Fn BUTTON', 0xe: 'second button (same 15 options)',
    0x6b: 'DISP. CUSTOM SETTING: EVF/LCD (22 toggles 0x6c..0x81)',
    0x82: 'DISP. CUSTOM SETTING: OVF (15 toggles 0x83..0x91)',
    0x144: 'FLASH MODE', 0x66: 'FLASH COMPENSATION', 0x111: 'MF ASSIST: PEAK level (LOW/HIGH)',
    0x150: 'RAW: PUSH/PULL PROCESSING', 0x151: 'RAW: DYNAMIC RANGE', 0x152: 'RAW: FILM SIMULATION (film code)',
    0x153: 'RAW: WHITE BALANCE', 0x154: 'RAW: COLOR TEMPERATURE', 0x155: 'RAW: WB SHIFT', 0x156: 'RAW: WB SHIFT R',
    0x157: 'RAW: WB SHIFT B', 0x158: 'RAW: COLOR (+ mono/sepia codes)', 0x159: 'RAW: SHARPNESS',
    0x15a: 'RAW: NOISE REDUCTION', 0x15b: 'RAW: HIGHLIGHT TONE', 0x15c: 'RAW: SHADOW TONE', 0x15d: 'RAW: COLOR SPACE',
    0x160: 'PHOTOBOOK: book page', 0x163: 'IMAGE SEARCH', 0x164: 'search BY DATE', 0x165: 'search BY FACE',
    0x166: 'search BY FAVORITES', 0x167: 'search BY TYPE OF DATA', 0x16e: 'hidden item 79: field 1',
    0x16f: 'hidden item 79: field 2',
    0x25: 'DATE/TIME: format', 0x26: 'year', 0x27: 'month', 0x28: 'day', 0x29: 'hour', 0x2a: 'minute',
    0x2c: 'TIME DIFFERENCE: LOCAL', 0x2d: 'local: summer time', 0x2e: 'local: hours', 0x2f: 'local: minutes',
    0x37: 'SENSOR CLEANING: WHEN SWITCHED ON', 0x38: 'SENSOR CLEANING: WHEN SWITCHED OFF',
    0x1a2: 'EDIT FILE NAME: sRGB prefix', 0x1a3: 'EDIT FILE NAME: Adobe RGB prefix',
    0x128: 'LCD BRIGHTNESS', 0xa3: 'SELECT CUSTOM SETTING',
}
for _k in range(22): SUB_NAMES.setdefault(0x6c + _k, f'EVF/LCD display item {_k}')
# Titles the record gives as an icon string only.
TITLE_FIX = {58: 'LANGUAGE (title text is the icon string 125)'}


class FW:
    def __init__(self):
        self.b1 = open(os.path.join(RE, 'work', 'blob1.bin'), 'rb').read()
        nb = open(os.path.join(RE, 'work', 'not.bin'), 'rb').read()
        self.m41 = nb[M41_FILE:M41_FILE + M41_SIZE]
        self.texts = {}

    def w1(self, a): return struct.unpack_from('<I', self.b1, a - B1)[0]
    def wm(self, a): return struct.unpack_from('<I', self.m41, a - M41)[0]
    def bm(self, a): return self.m41[a - M41]

    def text(self, i, icons=False):
        if i not in self.texts:
            try: self.texts[i] = uitext.text(1, i)[1]
            except Exception: self.texts[i] = None
        t = self.texts[i]
        if t is None: return f'#{i}'
        return t.strip() if icons else ''.join(c for c in t if ord(c) < 0xe000).strip()

    # --- blob1 node tree --------------------------------------------------------------------------------------
    def isptr(self, v): return B1 <= v < 0x790000 and v % 4 == 0

    def node(self, a):
        if not self.isptr(a): return None
        g, s, t, f, par, lst = (self.w1(a + 4 * i) for i in range(6))
        if not (self.isptr(lst) and (par == 0 or self.isptr(par)) and s < 0x400 and g < 0x400 and t < 0x100):
            return None
        L = []
        for i in range(300):
            v, c = self.w1(lst + 8 * i), self.w1(lst + 8 * i + 4)
            if v == END: return dict(a=a, g=g, s=s, t=t, f=f, par=par, lst=lst, L=L)
            if not (c == 0 or self.isptr(c)): return None
            L.append((v, c))
        return None

    def conv(self, s):
        p = self.w1(CONV_PTRS + 4 * s) if s < CONV_N else 0
        if not p: return None, []
        rows = []
        while len(rows) < 100:
            r = tuple(self.w1(p + 12 * len(rows) + 4 * i) for i in range(3))
            if r == (0xffff,) * 3: break
            rows.append(r)
        return p, rows


# --- parsers for the two decompiles --------------------------------------------------------------------------
def _func(src, addr):
    i = src.index(f'//@@FUNC {addr:08x}'); j = src.index('//@@FUNC', i + 10); return src[i:j]


def _case_blocks(txt):
    blocks, cur, buf = {}, [], []
    def flush():
        nonlocal cur, buf
        if cur and buf:
            for c in cur: blocks[c] = buf
        cur, buf = [], []
    for line in txt.split('\n'):
        m = re.match(r'\s*case (0x[0-9a-f]+|\d+):\s*$', line)
        if m:
            if buf: flush()
            cur.append(int(m.group(1), 0)); continue
        if re.match(r'\s*default:', line) or line.startswith('LAB_'): flush(); continue
        if cur: buf.append(line)
    flush()
    return blocks


def storage_table():
    """setting -> {addr, slot, mask, shift, bits} from blob1 FUN_0078fb50 (the settings getter)."""
    src = gzip.open(os.path.join(RE, 'decompiled', 'xpro1_blob1_0x774000.c.gz'), 'rt').read()
    res = {}
    for c, buf in _case_blocks(_func(src, 0x0078fb50)).items():
        e = None
        for l in buf:
            if 'param_2 * 0x12a' not in l: continue
            m = re.search(r'\(&DAT_([0-9a-f]+)\)\[param_2 \* 0x12a( \+ param_4 \* 7)?\]', l)
            if m: addr, slot = int(m.group(1), 16), bool(m.group(2))
            else:
                m = re.search(r'\*\((byte|ushort|uint|int|char) \*\)\(param_2 \* 0x12a \+ (param_4 \* 7 \+ )?(0x[0-9a-f]+)\)', l)
                if not m: continue
                addr, slot = int(m.group(3), 16), bool(m.group(2))
            typ = 16 if 'ushort' in l else 8
            mk = re.findall(r'& (0x[0-9a-f]+|\d+)', l); sh = re.findall(r'>> (\d+)', l)
            M = int(mk[-1], 0) if mk else (1 << typ) - 1
            s = int(sh[-1]) if sh else 0
            M &= (1 << typ) - 1
            e = dict(addr=addr, slot=slot, mask=M, shift=s, bits=bin(M >> s).count('1'), width=typ)
            break
        res[c] = e
    return res


def screen_kinds(fw):
    """kind -> (layout base, record array) from module 0x41 FUN_01476b8c / FUN_014796fc."""
    src = gzip.open(os.path.join(RE, 'decompiled', 'xpro1_mod41_0x1420000.c.gz'), 'rt').read()
    def cases(txt, pat):
        out = {}
        for c, buf in _case_blocks(txt).items():
            for l in buf:
                m = re.search(pat, l)
                if m: out[c] = int(m.group(1), 16); break
        return out
    lay = cases(_func(src, 0x01476b8c), r'DAT_([0-9a-f]+)\)\[param_2 \* 0xf')
    lay[1] = 0x142ccea                                        # kind 1 falls through to the code after the switch
    arr = cases(_func(src, 0x014796fc), r'DAT_([0-9a-f]+) \+ \(iVar1')
    kinds = {}
    for k in sorted(set(lay) | set(arr)):
        L, A = lay.get(k), arr.get(k)
        pages = []
        if L and A:
            for p in range(8):
                cnt = fw.bm(L - 1 + p * 15)
                if cnt == 0 or cnt > 7: break
                pages.append([fw.bm(L + p * 15 + r * 2) for r in range(cnt)])
        kinds[k] = dict(layout=L, records=A, pages=pages)
    return kinds


def record(fw, arr, k):
    it, tx, g, f, A, Bt = (fw.wm(arr + 24 * k + 4 * i) for i in range(6))
    return dict(item=it, text=tx, gfx=g, flag=f, A=A, B=Bt)


# --- output ----------------------------------------------------------------------------------------------------
def fmt_rows(rows, maxn=14):
    f = lambda x: '–' if x == END else (str(x - (1 << 32)) if x >= 0x80000000 else str(x))
    s = ' '.join('{' + ','.join(f(x) for x in r) + '}' for r in rows[:maxn])
    return s + (f' … ({len(rows)} rows)' if len(rows) > maxn else '')


def fmt_vals(vals, maxn=16):
    s = ','.join(str(v) for v in vals[:maxn])
    return s + (f',… ({len(vals)})' if len(vals) > maxn else '')


def fmt_store(st):
    if not st: return ''
    lo = st['shift']; hi = lo + st['bits'] - 1
    where = f"{st['addr']:#x}{'+7·slot' if st['slot'] else ''}"
    return f"{where} bits {hi}..{lo} ({st['bits']} bit{'s' if st['bits'] != 1 else ''})"


def spare(st, rows):
    if not st or st['bits'] > 6: return ''
    used = {r[0] for r in rows if r[0] != END}
    free = [v for v in range(1 << st['bits']) if v not in used]
    return ','.join(map(str, free)) if free else 'none'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(RE, 'MENU_MAP.md'))
    a = ap.parse_args()
    fw = FW()
    store = storage_table()
    kinds = screen_kinds(fw)

    nodes = {}
    for adr in range(B1, 0x790000 - 24, 4):
        n = fw.node(adr)
        if n: nodes[adr] = n

    names = dict(SUB_NAMES)        # setting -> name
    item_names = {}                # item id -> name
    ovf = kinds[0x16]              # OVF display toggles: child value k = record k of kind 0x16 (assumed)
    for k in range(15):
        names.setdefault(0x83 + k, f"OVF: {fw.text(record(fw, ovf['records'], k)['text'])} (item {k}, assumed)")
    out = []
    P = out.append
    P('# X-Pro1 menu map (generated)\n')
    P('Generated by `re/tools/menumap.py` from the official 3.82 firmware (static). **Do not edit by hand**: change')
    P('the tool and re-run it. How the pieces fit and how to change them: [`MENUS.md`](MENUS.md). RAM addresses;')
    P('blob1 at 0x774000, module 0x41 at 0x1420000.\n')
    P('Columns: **item** = global item ID (the value in the page list); **setting** = settings ID (conversion table')
    P('0x78ba10[setting], getter blob1 0x78fb50); **node** = blob1 node; **w** = widget type (node word 2);')
    P('**values** = the list (conversion-table row numbers, menu order); **table** = rows {c0 stored, c1, c2 internal}')
    P('(– = 0x7ffffffe); **storage** = bit field in settings bank 0 (bank n: + n·0x12a; +7·slot = per custom-setting')
    P('slot); **spare** = stored values the field can hold that no row uses.\n')

    # main menu pages
    sub_rows = []
    def walk_children(n, depth, path):
        for v, c in n['L']:
            if not c or c not in nodes: continue
            ch = nodes[c]
            if ch['par'] != n['a'] and depth > 0:
                sub_rows.append((path, v, ch, 'shared node (parent is elsewhere)')); continue
            sub_rows.append((path, v, ch, ''))
            if depth < 4: walk_children(ch, depth + 1, path + [names.get(ch['s'], f"{ch['s']:#x}")])

    for title, adr, kind in PAGES:
        n = nodes[adr]
        K = kinds[kind]
        slots = [k for page in K['pages'] for k in page]
        items = [(v, c) for v, c in n['L'] if v not in HIDDEN]
        assert len(items) == len(slots), (title, len(items), len(slots))
        P(f'## {title}\n')
        P(f'Page node {adr:#x} (setting {n["s"]:#x}, group {n["g"]:#x}), list {n["lst"]:#x}; drawn by module 0x41 screen '
          f'kind {kind:#x}: layout {K["layout"]:#x} (page p at +15·p: count, then 7 × (record, flag)), '
          f'records {K["records"]:#x} (24 bytes each). {len(K["pages"])} pages, {len(slots)} items.\n')
        P('| page.row | item | title (text ID) | record | setting | node | w | values | table | storage | spare |')
        P('|---|---|---|---|---|---|---|---|---|---|---|')
        it = iter(slots); pos = 0
        page_of = [(p, r) for p, page in enumerate(K['pages']) for r in range(len(page))]
        for v, c in n['L']:
            if v in HIDDEN:
                ch = nodes.get(c) if c else None
                st = store.get(ch['s']) if ch else None
                p_, rows = fw.conv(ch['s']) if ch else (None, [])
                P(f"| hidden | {v} | *({HIDDEN[v]})* | – | {ch['s']:#x} | {c:#x} | {ch['t']} | {fmt_vals([x for x, _ in ch['L']])} | "
                  f"{fmt_rows(rows, 6)} | {fmt_store(st)} | {spare(st, rows)} |" if ch else
                  f"| hidden | {v} | *({HIDDEN[v]})* | – | (action) | – | | | | | |")
                if ch: names.setdefault(ch['s'], f'hidden item {v}')
                continue
            k = next(it); p, r = page_of[pos]; pos += 1
            rec = record(fw, K['records'], k)
            name = TITLE_FIX.get(v) or fw.text(rec['text'])
            item_names[v] = name
            if c:
                ch = nodes[c]; names.setdefault(ch['s'], name)
                st = store.get(ch['s']); tp, rows = fw.conv(ch['s'])
                vals = [x for x, cc in ch['L']]
                P(f"| {p + 1}.{r + 1} | {v} | {name} ({rec['text']}) | {k} | {ch['s']:#x} | {c:#x} | {ch['t']} | "
                  f"{fmt_vals(vals)} | {(f'{tp:#x}: ' + fmt_rows(rows, 8)) if tp else ''} | {fmt_store(st)} | {spare(st, rows)} |")
                walk_children(ch, 0, [name])
            else:
                P(f"| {p + 1}.{r + 1} | {v} | {name} ({rec['text']}) | {k} | (action) | – | | | | | |")
        P('')

    # sub-settings under the main menu
    P('## Settings below the main-menu items\n')
    P('Children of an item node, depth-first (a list value with a child node opens that node). Shared nodes (used')
    P('under several values, e.g. WB SHIFT under every WB mode) are listed once.\n')
    P('| path | value | setting | name | node | w | values | table | storage | spare |')
    P('|---|---|---|---|---|---|---|---|---|---|')
    seen = set()
    for path, v, ch, note in sub_rows:
        if ch['a'] in seen: continue
        seen.add(ch['a'])
        st = store.get(ch['s']); tp, rows = fw.conv(ch['s'])
        vals = [x for x, cc in ch['L']]
        P(f"| {' › '.join(path)} | {v} | {ch['s']:#x} | {names.get(ch['s'], '?')}{(' — ' + note) if note else ''} | "
          f"{ch['a']:#x} | {ch['t']} | {fmt_vals(vals)} | {(f'{tp:#x}: ' + fmt_rows(rows, 6)) if tp else ''} | "
          f"{fmt_store(st)} | {spare(st, rows)} |")
    P('')

    # other roots
    for title, adr in OTHER_ROOTS:
        n = nodes[adr]
        P(f'## {title}\n')
        P(f'Root node {adr:#x} (setting {n["s"]:#x}, group {n["g"]:#x}, widget {n["t"]}), list {n["lst"]:#x}.\n')
        P('| # | item/value | setting | name | node | w | values | table | storage | spare |')
        P('|---|---|---|---|---|---|---|---|---|---|')
        page = n['s'] == 5             # only menu-page lists hold item IDs; other lists hold values / indices
        for i, (v, c) in enumerate(n['L']):
            if not c:
                P(f"| {i + 1} | {v} | {'(action)' if page else '(value)'} | {item_names.get(v, '?') if page else ''} | | | | | | |")
                continue
            ch = nodes[c]; st = store.get(ch['s']); tp, rows = fw.conv(ch['s'])
            nm = names.get(ch['s']) or (item_names.get(v, '?') if page else '?')
            if v in HIDDEN: nm += f' — hidden ({HIDDEN[v]})'
            P(f"| {i + 1} | {v} | {ch['s']:#x} | {nm} | {c:#x} | {ch['t']} | {fmt_vals([x for x, _ in ch['L']])} | "
              f"{(f'{tp:#x}: ' + fmt_rows(rows, 6)) if tp else ''} | {fmt_store(st)} | {spare(st, rows)} |")
        P('')

    # nodes no root reaches: pop-ups opened directly by code (buttons, first start, playback)
    reached = set()
    def mark(adr):
        if adr in reached or adr not in nodes: return
        reached.add(adr)
        for v, c in nodes[adr]['L']:
            if c: mark(c)
    for adr in [0x776b24] + [r for _, r in OTHER_ROOTS]: mark(adr)
    P('## Nodes no root reaches (pop-ups opened by code)\n')
    P('Found by the node scan but not under any root: opened directly by a button handler or another screen, or')
    P('unused. Names are guesses where marked "?". (0x78ba18 / 0x78bce4 / 0x78c1dc are false matches in table data.)\n')
    P('| node | group | setting | name | w | values | table | storage | spare |')
    P('|---|---|---|---|---|---|---|---|---|')
    for adr in sorted(a_ for a_ in nodes if a_ not in reached and nodes[a_]['s']):
        n = nodes[adr]; st = store.get(n['s']); tp, rows = fw.conv(n['s'])
        nm = names.get(n['s'], '?')
        if adr == 0x77a27c: nm = 'LANGUAGE pop-up (first start?)'
        if adr == 0x775c64: nm = 'Fn BUTTON, second copy (parent = shooting page, not in its list)'
        P(f"| {adr:#x} | {n['g']:#x} | {n['s']:#x} | {nm} | {n['t']} | {fmt_vals([x for x, _ in n['L']])} | "
          f"{(f'{tp:#x}: ' + fmt_rows(rows, 6)) if tp else ''} | {fmt_store(st)} | {spare(st, rows)} |")
    P('')

    # conversion-table rows that exist but are not offered by the setting's menu list(s)
    P('## Table rows defined but not offered\n')
    P('Rows of a setting\'s conversion table that are not all 0x7ffffffe but appear in none of the setting\'s lists:')
    P('options the firmware already describes (shared code with other bodies, or retired). Adding the row number')
    P('to the list is the whole menu side of offering one; what the camera then does is untested.\n')
    P('| setting | name | lists | unlisted rows {c0,c1,c2} |')
    P('|---|---|---|---|')
    by_set = {}
    for adr, n in nodes.items():
        if n['s'] != 5: by_set.setdefault(n['s'], []).append(n)
    for s, ns in sorted(by_set.items()):
        tp, rows = fw.conv(s)
        if not rows: continue
        listed = {v for n in ns for v, _ in n['L']}
        miss = [i for i, r in enumerate(rows) if r != (END,) * 3 and i not in listed]
        if miss:
            P(f"| {s:#x} | {names.get(s, '?')} | {' '.join(hex(n['a']) for n in ns)} | "
              f"{' '.join(f'row {i} ' + fmt_rows([rows[i]]) for i in miss)} |")
    P('')

    # module 0x41 screen kinds
    P('## Module 0x41 screen kinds\n')
    P('`FUN_01476b8c(kind, page, row)` → record index = byte at layout + page·15 + row·2 + variant·0x60')
    P('(variant = `[0x12af4f8]`, 0–3); `FUN_014796fc` / `0x1479630` read the record\'s fields. Variant 0 shown;')
    P('later variants are listed only for kinds that define them. Each screen\'s draw function passes a fixed kind.\n')
    P('| kind | layout | records | pages (record: title) |')
    P('|---|---|---|---|')
    for k, K in kinds.items():
        desc = ' / '.join(' | '.join(f"{r}: {fw.text(record(fw, K['records'], r)['text'])}" for r in page)
                          for page in K['pages']) if K['pages'] else '(no record array)'
        P(f"| {k:#x} | {K['layout'] and hex(K['layout'])} | {K['records'] and hex(K['records'])} | {desc} |")
    P('')

    # every setting
    P('## Every setting ID with a node, a conversion table or a storage field\n')
    users = {}
    for adr, n in nodes.items(): users.setdefault(n['s'], []).append(adr)
    P('| setting | name | nodes | table (rows) | storage | spare |')
    P('|---|---|---|---|---|---|')
    allset = sorted(set(users) | {s for s in range(CONV_N) if fw.w1(CONV_PTRS + 4 * s)} | set(store))
    for s in allset:
        if s == 5: continue
        tp, rows = fw.conv(s); st = store.get(s)
        P(f"| {s:#05x} | {names.get(s, '')} | {' '.join(hex(x) for x in sorted(users.get(s, [])))} | "
          f"{(f'{tp:#x} ({len(rows)})') if tp else ''} | {fmt_store(st)} | {spare(st, rows)} |")
    P('')

    # free bits in the bank
    P('## Settings-bank bytes and free bits (bank 0, from the getter only)\n')
    P('Bits that no getter case reads. Code that touches the bank directly (copy, reset, EXIF) is not covered, so')
    P('check the byte\'s other readers before using a free bit. Per-slot fields repeat at +7·slot (slots 0–6).\n')
    used = {}
    for s, st in store.items():
        if not st: continue
        reps = range(7) if st['slot'] else [0]
        for k in reps:
            for bit in range(st['shift'], st['shift'] + st['bits']):
                adr = st['addr'] + 7 * k + bit // 8
                used.setdefault(adr, {})[bit % 8] = s
    lo, hi = min(used), max(used)
    P('| byte | bit 7 … 0 (setting ID in hex using the bit, · = free) |')
    P('|---|---|')
    for adr in range(lo, hi + 1):
        u = used.get(adr, {})
        if not u: continue
        P(f"| {adr:#x} | {' '.join((f'{u[b]:x}' if b in u else '·') for b in range(7, -1, -1))} |")
    P('')
    open(a.out, 'w').write('\n'.join(out) + '\n')
    print('wrote', a.out, len(out), 'lines')


if __name__ == '__main__':
    main()
