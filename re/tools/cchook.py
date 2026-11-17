"""Moved: the run-time hooks (tuning values, texts) live in re/classic_chrome/engine/hooks.py. This name stays for
build_sdchain.py --cc and emu_cchook.py."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from classic_chrome.engine.hooks import *          # noqa: F401,F403
