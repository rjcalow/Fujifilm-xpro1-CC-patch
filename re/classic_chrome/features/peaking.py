"""Stronger white focus peaking (PR #3): HIGH peaking gain 64 → 120 (two parameters) and an earlier HIGH tuning
value 40 → 48. Tuning-area bytes, written by the tuning hooks (engine/hooks.py), old value checked. The outline
stays white; its width still depends on the scene.
"""
from classic_chrome.engine.card import Part

BYTES = {0xc88c: (40, 48), 0xc8a5: (64, 120), 0xc8a7: (64, 120)}


class Peaking(Part):
    def check(self, fw):
        for i, (old, _) in BYTES.items():
            assert fw.tuning[i] == old, f'tuning {i:#x}: stock {fw.tuning[i]}, expected {old}'
            assert fw.flash_tuning[i] == old, f'tuning {i:#x}: flashed firmware has {fw.flash_tuning[i]}, expected {old}'

    def tuning_bytes(self, fw):
        return dict(BYTES)
