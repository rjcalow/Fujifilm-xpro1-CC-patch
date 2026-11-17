"""Moved: the SD-boot chain lives in re/classic_chrome/engine/chain.py. This name stays for the tools that import it
(romdump/build_dumpcard.py, build_sdchain.py, sdcrumbs.py, emu_dumpcard.py, emu_cchook.py)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from classic_chrome.engine.chain import *          # noqa: F401,F403
