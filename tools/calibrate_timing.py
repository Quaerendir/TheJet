#!/usr/bin/env python3
"""Check the engine against the original in a cycle-exact emulator (libatari800) and calibrate
the frame budget of the engine's cycle model (SPEC.md §7, `Timing`).

Both run the sample board with its tanks removed (the shells are the only randomness, so the
emulator and the engine then play the same game) under the inputs of tests/autopilot.py:

  1. at every frame end at which neither side is in the middle of a scan, the 800 bytes of
     screen memory and the game variables must be identical (the engine's tick ends just
     before the next vertical blank, the emulator's frame at the end of the vertical blank:
     the two coincide only while the main loop waits);
  2. at the frame ends at which the emulator's scan is in progress, its SCAN_PTR is turned
     into CPU cycles with the engine's own cost model: at the end of an iteration's first
     frame that is the main loop's share of the vertical blank after the VBI routines
     (`vblank_rest`); at the end of its second frame it is that twice plus the share of the
     displayed part (`visible` minus the DLI's wait, `dli_line` per line of VSCROL+1).

    python3 tools/calibrate_timing.py path/to/libatari800.so [--frames 3000]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import mean, median, pstdev

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
from atari800_timing import Atari, JETS, JET_X  # noqa: E402
from autopilot import autopilot  # noqa: E402
from build_xex import build_standalone  # noqa: E402
from thejet.engine import ROW_20, Engine, Input, parse_board  # noqa: E402

SCREEN, VARS, RTCLOK = 0x3B43, 0x3989, 0x14
PRELUDE = 20                                     # ML_FRAME between SCROLL and SCAN: colours, A = RTCLOK+1, PHA


def engine_vars(e: Engine) -> bytes:
    return bytes([e.vscrol & 0xFF, e.row_toggle, e.parity, e.flash, e.snd_shell, e.snd_splash, e.snd_shot,
                  e.snd_death, e.jet_x, *e.missile_x, *e.missile_y, e.trig_prev])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('lib', type=Path)
    ap.add_argument('--frames', type=int, default=3000)
    ap.add_argument('--xex', type=Path, default=Path('/tmp/thejet_notanks.xex'))
    args = ap.parse_args()
    rows = [r.replace('<', ' ').replace('>', ' ') for r in parse_board((ROOT / 'board.txt').read_text())]
    args.xex.write_bytes(build_standalone((ROOT / 'thejet.obj').read_bytes(), rows))
    a = Atari(args.lib, args.xex)
    for _ in range(400):
        a.step()
        if a[JET_X] == 0x70 and a[JETS] == 2:
            break
    for _ in range(60):
        a.step(trig=1)
    for _ in range(20):                              # press: GAME_INIT, then the first game VBI decrements
        a.step(trig=0)                               # MISSILE_Y from 0 to $FF
        if a[0x3997] == 0xFF:
            break
    else:
        sys.exit('the game did not start')
    e = Engine(rows, rnd=lambda: 0, rtclok=(a[RTCLOK] - 1) & 0xFF)
    e.record_costs = True
    e.tick(Input(trig=0))                            # the engine's first VBI = the one the emulator just ran
    compared = differing = 0
    rest: list[int] = []
    vis: dict[int, list[int]] = {}
    cadence: dict[int, int] = {}
    last_iter, since = 0, 0
    prev_vbi = e.vbi_cycles
    for f in range(args.frames):
        inp = autopilot(e.mem, e.jet_x, f)
        vbi_before = prev_vbi
        e.tick(inp)
        prev_vbi = e.vbi_cycles
        a.step(stick=inp.stick, trig=inp.trig)
        since += 1
        if e.iteration != last_iter:
            cadence[since] = cadence.get(since, 0) + 1
            last_iter, since = e.iteration, 0
        idx = (a[0xB0] | (a[0xB1] << 8)) - SCREEN
        scanning = 32 <= idx < ROW_20
        if not scanning and e.scan_index == ROW_20:
            compared += 1
            amem = bytes(a[SCREEN + i] for i in range(800))
            avars = bytes(a[VARS + 1 + i] for i in range(18))
            if amem != bytes(e.mem) or avars != engine_vars(e):
                differing += 1
                if differing <= 5:
                    diff = [i for i in range(800) if amem[i] != e.mem[i]]
                    print(f'frame {f}: {len(diff)} screen bytes differ, first {diff[:5]}; '
                          f'vars {avars.hex()} vs {engine_vars(e).hex()}')
        elif scanning and idx in e.scan_trace:
            k = (e.frame - e.iteration_start) & 0xFF        # 0: the iteration's first frame end, 1: second
            used = e.scroll_cycles + PRELUDE + e.scan_trace[idx]
            if k == 0:
                rest.append(used + e.vbi_cycles)            # = vblank: the VBI's own cycles added back
            elif k == 1:
                vis.setdefault(e.vscrol, []).append(used + vbi_before + e.vbi_cycles)
        if a[JETS] == 0xFF or e.status.value != 'playing':
            print('game over at frame', f)
            break
    print(f'{f + 1} frames; frames per main-loop iteration: {dict(sorted(cadence.items()))}')
    print(f'{compared} quiet frame ends compared, {differing} differ')
    if rest:
        r = mean(rest)
        print(f'vblank (after the OS routines, before the game VBI): n={len(rest)} mean {r:.0f} '
              f'sd {pstdev(rest):.0f} min {min(rest)} max {max(rest)}')
        pts = []
        for v in sorted(vis):
            fv = [c - 2 * r for c in vis[v]]
            print(f'  visible(vscrol={v}): n={len(fv)} mean {mean(fv):.0f} median {median(fv):.0f} '
                  f'sd {pstdev(fv):.0f}')
            if v < 7:                                        # 7 = the shift iterations: the scroll's cost
                pts.append((v + 1, median(fv)))              # model is only approximate there
        if len(pts) >= 2:
            n = len(pts)
            sx, sy = sum(p[0] for p in pts), sum(p[1] for p in pts)
            sxx, sxy = sum(p[0] ** 2 for p in pts), sum(p[0] * p[1] for p in pts)
            slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
            icpt = (sy - slope * sx) / n
            print(f'fit: visible = {icpt:.0f} - {-slope:.0f} * (vscrol + 1)   '
                  f'(Timing(vblank={r:.0f}, visible={icpt:.0f}, dli_line={-slope:.0f}))')


if __name__ == '__main__':
    main()
