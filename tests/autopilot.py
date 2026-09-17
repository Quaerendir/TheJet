"""A simple pilot for long test runs: steer towards the nearest column pair that is empty in the
rows about to reach the jet, shoot every tenth frame. Decisions depend only on the engine's state,
so the same inputs can be fed to the original running in py65."""
from __future__ import annotations

from thejet.engine import COLS, Input


def autopilot(mem: bytes | bytearray, jet_x: int, frame: int, fire_every: int = 10) -> Input:
    col = (jet_x - 63) >> 2

    def safe(c: int) -> bool:
        return all(mem[(r + 2) * COLS + c] == 0 and mem[(r + 2) * COLS + c + 1] == 0 for r in range(11, 18))

    candidates = [c for c in range(0, COLS - 1) if safe(c)]
    target = min(candidates, key=lambda c: (abs(c - col), c)) if candidates else col
    tx = 64 + 4 * target
    stick = 0x0F
    if tx > jet_x:
        stick &= ~8
    elif tx < jet_x:
        stick &= ~4
    return Input(stick, 0 if fire_every and frame % fire_every == 0 else 1)
