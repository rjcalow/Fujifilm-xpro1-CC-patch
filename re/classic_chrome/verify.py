#!/usr/bin/env python3
"""Check a built card before it goes on the camera.

    ~/.venvs/xpro1-re/bin/python re/classic_chrome/verify.py FPUPDATE.DAT CARD_DIR [converter options]

Runs the emulator checks on CARD_DIR/ffboot.bin (real firmware code under unicorn; needs re/work from
re/tools/setup_work.sh) and, when the converter options are given, compares the build with the known-good builds
(validate/regression.py):
  validate/emu_chain.py  SD-boot chain: stub, loader, power-on fix, traps, stage B, green accent
  validate/emu_card.py   menus + RAW conversion: stage-B words, conversion engine, module hooks, language hook,
                         blob2 chains, module 0x44 switch
  validate/emu_look.py   look: tuning hooks, blob2 table, the pipeline's selection functions (own look only)
Options: --flash FILE (flashed firmware, default re/build/ptpdebug_385/FPUPDATE.DAT), --work DIR (default re/work).
Prints one line per check and ends with ALL OK or FAILED (exit code 0 / 1).
"""
import hashlib, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from classic_chrome.engine.firmware import DEFAULT_FLASH, RE
from classic_chrome.validate import regression


def run(official, card_dir, opts=(), flash=DEFAULT_FLASH, work=os.path.join(RE, 'work'), quiet=False):
    boot = os.path.join(card_dir, 'ffboot.bin')
    digest = hashlib.sha256(open(boot, 'rb').read()).hexdigest()
    py = sys.executable
    o = list(opts)
    from classic_chrome.convert import lineup_keys
    keys, peaking = lineup_keys(o)
    sims = ','.join(keys)
    look = o[o.index('--look') + 1] if '--look' in o else 'own'
    steps = [('emu_chain', [official, boot, work]), ('emu_card', [official, boot, work, flash, sims] + (['--no-rawconv'] if '--no-rawconv' in o else []))]
    if look == 'own' and 'classic_chrome' in keys:
        steps.append(('emu_look', [official, boot, work, flash] + (['--peaking'] if peaking else [])))
    if len(keys) > 1 or peaking:
        steps.append(('emu_extras', [official, boot, work, flash, sims] + (['--peaking'] if peaking else [])))
    ok = True
    for name, args in steps:
        r = subprocess.run([py, os.path.join(HERE, 'validate', name + '.py')] + args, capture_output=True, text=True)
        out = r.stdout + r.stderr
        good = r.returncode == 0 and 'ALL OK' in out
        ok &= good
        fails = [l for l in out.splitlines() if l.startswith('FAIL')]
        print(f'{"OK  " if good else "FAIL"} {name}' + ('' if good else '\n' + ('\n'.join(fails) or out[-1500:])))
    known = regression.matches(digest, list(opts))
    if known is None: print(f'--   known-good build: none recorded for these options (ffboot {digest[:16]}…)')
    else:
        print(f'{"OK  " if known else "FAIL"} known-good build ({digest[:16]}…)'); ok &= known
    print('ALL OK' if ok else 'FAILED')
    return ok


def main(a):
    flash = DEFAULT_FLASH; work = os.path.join(RE, 'work')
    if '--flash' in a: k = a.index('--flash'); flash = a[k + 1]
    if '--work' in a: k = a.index('--work'); work = a[k + 1]; del a[k:k + 2]
    if len(a) < 2: sys.exit(__doc__)
    sys.exit(0 if run(a[0], a[1], a[2:], flash, work) else 1)


if __name__ == '__main__':
    main(sys.argv[1:])
