"""The engine against the original 6502 code running in py65 (tools/run_original.py): the same
board, inputs and random numbers, frame by frame; the harness fires its vertical blank where the
engine's cycle model put it, so the comparison covers the mid-scan interrupts too."""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
pytest.importorskip('py65')
import run_original as ro  # noqa: E402
from autopilot import autopilot  # noqa: E402
from thejet.engine import ROW_20, Engine, Input, Timing, board_bytes, parse_board  # noqa: E402

OBJ = (ROOT / 'thejet.obj').read_bytes()
ARTICLE = parse_board((ROOT / 'board.txt').read_text())
MIXED = ['#  " % $ ! "   #', '#>   "" <  >   #', '#              #', '# "" "" "" ""  #'] * 12
TANKS = ['#>     <  >    #', '#              #'] * 20


def engine_vars(e: Engine) -> bytes:
    """The bytes VAR_UNUSED..PAUSED as the engine would hold them (HIT_CHAR and the unused one zeroed)."""
    return bytes([0, e.vscrol & 0xFF, e.row_toggle, e.parity, e.flash, e.snd_shell, e.snd_splash, e.snd_shot,
                  e.snd_death, e.jet_x, *e.missile_x, *e.missile_y, e.trig_prev, 0, e.death, e.fuel_lo,
                  e.fuel_hi, e.jets & 0xFF, *e.score, e.paused])


def compare(rows: list[str], frames: int, seed: int, pilot: bool = True) -> tuple[int, int, float]:
    o = ro.Original(OBJ + board_bytes(rows), seed=seed)
    o.start_game()
    r = random.Random(seed)
    e = Engine(rows, rnd=lambda: r.randrange(256), rtclok=o.mem[0x14])
    worst = 0.0
    for f in range(frames):
        inp = autopilot(e.mem, e.jet_x, f) if pilot else Input(0x07 if f < 7 else 0x0F, 0 if f % 9 == 0 else 1)
        e.tick(inp)
        split = e.last_split if e.scan_index < ROW_20 else None
        o.step_frame(stick=inp.stick, trig=inp.trig, split=split)
        assert o.screen == bytes(e.mem), f'screen differs at frame {f}'
        ov = o.vars
        assert (ov[1:19], ov[20:]) == (engine_vars(e)[1:19], engine_vars(e)[20:]), f'variables differ at frame {f}'
        assert o.missiles == bytes(e.missiles), f'missile memory differs at frame {f}'
        assert o.pokey == bytes(e.pokey), f'POKEY registers differ at frame {f}'
        if e.status.value not in ('playing', 'paused'):
            break
    return f + 1, e.iteration, worst


@pytest.mark.parametrize('rows,frames', [(ARTICLE, 1500), (MIXED, 1500), (TANKS, 1200)])
def test_identical_frame_by_frame(rows, frames):
    n, its, _ = compare(rows, frames, seed=3)
    assert its >= n // 3 - 1


def test_scripted_inputs_until_game_over():
    n, its, _ = compare(ARTICLE, 900, seed=5, pilot=False)
    assert n < 900 and its > 100                                # the script flies into the wall three times


def test_cycle_model_matches_py65():
    """The engine's cycle accounting of SCROLL and SCAN against py65's count for the same passes."""
    rows = MIXED
    o = ro.Original(OBJ + board_bytes(rows), seed=11, cycles_per_frame=10 ** 9)   # no interrupts in the work
    o.start_game()
    r = random.Random(11)
    e = Engine(rows, rnd=lambda: r.randrange(256), rtclok=o.mem[0x14], timing=Timing(vblank_rest=10 ** 7))
    mpu = o.mpu
    for it in range(40):
        inp = autopilot(e.mem, e.jet_x, it)
        e.tick(inp)
        o.stick, o.trig = inp.stick, inp.trig
        o.mem[0x278], o.mem[0x284] = inp.stick, inp.trig
        # run the original: the VBI (pending after start_game), then SCROLL and SCAN timed separately
        if it:
            o._vbi()
        while mpu.pc != 0x31B7:
            mpu.step()
        c0 = mpu.processorCycles
        while mpu.pc != 0x31BA:
            mpu.step()
        c1 = mpu.processorCycles
        while mpu.pc != 0x31C9:
            mpu.step()
        c2 = mpu.processorCycles
        while mpu.pc != 0x31CD:
            mpu.step()
        c3 = mpu.processorCycles
        while not o._spinning():
            mpu.step()
        assert abs((c1 - c0) - e.scroll_cycles) <= 300, f'SCROLL cycles: py65 {c1 - c0}, engine {e.scroll_cycles}'
        assert abs((c3 - c2) - e.scan_cycles) <= 40, f'SCAN cycles: py65 {c3 - c2}, engine {e.scan_cycles}'
        assert o.screen == bytes(e.mem)
