"""A simple pilot for long test runs: steer towards the column pair that stays empty deepest
above the jet (the trench bends), shoot every tenth frame. Decisions depend only on the engine's
state, so the same inputs can be fed to the original running in py65."""
from __future__ import annotations

from thejet.engine import COLS, Input


def autopilot(mem: bytes | bytearray, jet_x: int, frame: int, fire_every: int = 10) -> Input:
    col = (jet_x - 63) >> 2

    def depth(c: int) -> int:
        """Rows from the jet's row upwards (17, 16, ..) in which both columns are empty."""
        n = 0
        for r in range(17, 3, -1):
            i = (r + 2) * COLS + c
            if mem[i] or mem[i + 1]:
                break
            n += 1
        return n

    def clear(c: int) -> bool:
        return not (mem[18 * COLS + c] or mem[19 * COLS + c])      # rows 16/17: the jet's own rows

    reachable = [c for c in range(COLS - 1)
                 if all(clear(k) for k in range(min(col, c), max(col, c) + 2)) or c == col]
    best = max(reachable, key=lambda c: (depth(c), -abs(c - col)))
    tx = 64 + 4 * best
    stick = 0x0F
    if tx > jet_x:
        stick &= ~8
    elif tx < jet_x:
        stick &= ~4
    return Input(stick, 0 if fire_every and frame % fire_every == 0 else 1)
