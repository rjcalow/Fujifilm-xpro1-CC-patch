"""Known-good card builds: ffboot.bin SHA-256 by converter options (official 3.82 input, camera-tested boot stub
chain_crumbs.bin 19069ea8…, flashed firmware re/build/ptpdebug_385). A change to the engine or a feature that is
not meant to alter an existing card must keep these; a change that is meant to must update them (and NOTES.md).

2026-11-17: all cards changed on purpose. The FILM SIMULATION name table is now copied instead of written past its
end: its word 10 (0x1483c48) is entry 0 of the WHITE BALANCE name table, where the earlier cards put the
CLASSIC CHROME name. Earlier builds: default 6693177b… (camera-confirmed 2026-11-15), --no-rawconv 8d8364dc…,
--look borrow 127c321c…, --no-green b8547c4b… (tools/build_sdchain.py --fsim11 now gives the new builds too).
All entries below pass the emulator checks. Camera-confirmed: four-looks 4261ad85… (2026-11-17, before all entries got
RAW CONVERSION rows); the entries below not yet.
"""
KNOWN = {   # options (default values left out) → ffboot.bin SHA-256 (or its first 16 hex digits)
    frozenset(): '72d00748c77b9db78183f69554a7049cc1e77004cc4b06b17d522c76a098c214',
    frozenset({'--no-rawconv'}): 'e048ffa2ae4eef944958e671cc95d629741ba00ede1d7bdf3479aee51ae21264',
    frozenset({'--look=borrow'}): '429be0fb7c79f6cafc798d196ccb7b048add23aafab046b469aabbe38c377c94',
    frozenset({'--no-green'}): 'd76d9ee112108ceb441c56566647fe9f0aaf6f9d123fe4eb593a2cf48721bc9e',
    frozenset({'--four-looks'}): '28479b21e3cb202697e5ac3d52103ca987ff2ae81dccd550d5420f768a48cbd3',   # + RAW rows for all
    # (4261ad85… = the camera-confirmed four-looks card with only Classic Chrome in RAW CONVERSION)
}
DEFAULTS = {'--sim': 'classic_chrome', '--look': 'own'}
WITH_VALUE = ('--sim', '--look', '--flash', '--stub', '--add')


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
