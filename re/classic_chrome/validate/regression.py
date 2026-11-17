"""Known-good card builds: ffboot.bin SHA-256 by converter options (official 3.82 input, camera-tested boot stub
chain_crumbs.bin 19069ea8…, flashed firmware re/build/ptpdebug_385). A change to the engine or a feature that is
not meant to alter an existing card must keep these; a change that is meant to must update them (and NOTES.md).
"""
KNOWN = {   # options (default values left out) → ffboot.bin SHA-256 (or its first 16 hex digits)
    frozenset(): '6693177b4405451e6f2c05417db73861f56ca23dafa026d58ad38266eb8b8e4e',   # camera-confirmed 2026-11-15
    frozenset({'--no-rawconv'}): '8d8364dc67be74ad3a881746b562e3438356a3feecb27a9e30f882c805b5d759',
    frozenset({'--look=borrow'}): '127c321cc06cbc30',
    frozenset({'--no-green'}): 'b8547c4b92011fba',
}
DEFAULTS = {'--sim': 'classic_chrome', '--look': 'own'}
WITH_VALUE = ('--sim', '--look', '--flash', '--stub')


def expected(opts):
    """Known hash (or prefix) for these converter options, or None (unknown combination, own --flash / --stub)."""
    o, key = list(opts), set()
    while o:
        a = o.pop(0)
        if a in WITH_VALUE:
            v = o.pop(0)
            if a in ('--flash', '--stub'): return None
            if DEFAULTS.get(a) != v: key.add(f'{a}={v}')
        else: key.add(a)
    return KNOWN.get(frozenset(key))


def matches(digest, opts):
    """True / False if the build is known, None if it is not."""
    e = expected(opts)
    return None if e is None else digest.startswith(e)
