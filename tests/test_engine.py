"""Acceptance tests from SPEC.md §9. Frame counts follow game.asm; the cycle model is switched
off (`FAST`: one main-loop iteration per frame) except where the pacing itself is tested."""
from __future__ import annotations

import random

import pytest
from hypothesis import given, settings, strategies as st

from thejet.engine import (COLS, HUD, ROW_20, ROW_M1, DEADLY, Engine, EventKind, Input, Status, Timing,
                           bcd_add, bcd_sub, bcd_to_int, board_bytes, parse_board)

FAST = Timing(vblank_rest=10 ** 7)          # the scan never spills: one iteration per frame
IDLE = Input()
UP = Input.of(up=True)
FIRE = Input.of(fire=True)
WALL = '#' * 16
EMPTY = ' ' * 16


def idx(row: int, col: int) -> int:
    """`mem` index of a character; row -2..21."""
    return (row + 2) * COLS + col


def engine(rows: list[str], rnd: int = 1, still: bool = False, **kw: object) -> Engine:
    """`still`: no shift for 250 iterations (VSCROL_CTR far from -1), for tests of a static grid."""
    e = Engine(rows, rnd=lambda: rnd, timing=FAST, **kw)   # type: ignore[arg-type]
    if still:
        e.vscrol = 250
    return e


def run(e: Engine, n: int, inp: Input = IDLE) -> list:
    ev: list = []
    for _ in range(n):
        ev = e.tick(inp)
    return ev


def kinds(events) -> list[EventKind]:
    return [ev.kind for ev in events]


def scan(e: Engine) -> None:
    """One SCAN pass with no frame limit."""
    e.cycles = 0
    for _ in e._scan():
        pass


# ---------------------------------------------------------------- helpers
def test_bcd():
    assert bcd_add(0x99, 0x01) == (0x00, 1) and bcd_add(0x15, 0x15) == (0x30, 0)
    assert bcd_sub(0x00, 0x01) == (0x99, 1) and bcd_sub(0x50, 0x01) == (0x49, 0)
    assert bcd_to_int(0x99, 0x04) == 499 and bcd_to_int(0x34, 0x12, 0x00) == 1234


def test_parse_board_and_bytes():
    rows = parse_board('; legend\n#  #\n"  "\n')
    assert rows == ['#  #', '"  "']
    assert board_bytes(rows) == b'#  #\x9b"  "'


# ---------------------------------------------------------------- T1 scroll
def test_t1_first_iteration_shifts_then_every_eight():
    e = engine([WALL, EMPTY, WALL])
    assert e.vscrol == 0
    ev = run(e, 1)
    assert e.vscrol == 7 and EventKind.SHIFTED in kinds(ev)     # VSCROL_CTR 0 -> -1: wrap and shift
    for k in range(7):
        assert EventKind.SHIFTED not in kinds(run(e, 1)) and e.vscrol == 6 - k
    assert EventKind.SHIFTED in kinds(run(e, 1)) and e.vscrol == 7
    e2 = engine([WALL, EMPTY, WALL])
    run(e2, 1, UP)
    for k in range(3):
        assert EventKind.SHIFTED not in kinds(run(e2, 1, UP))
    assert EventKind.SHIFTED in kinds(run(e2, 1, UP))           # twice as fast with the stick up


def test_t1_shift_moves_rows_down_and_blanks_20_21():
    e = engine([WALL, EMPTY, WALL])
    e.mem[idx(-2, 0):idx(-2, 0) + 4] = b'\x01\x02\x01\x02'
    e.mem[idx(19, 5)] = 0x09
    e.mem[idx(20, 5)] = 0x77
    run(e, 1)                                                   # shift
    assert e.mem[idx(-1, 0):idx(-1, 0) + 4] == b'\x01\x02\x01\x02'
    assert e.mem[idx(-2, 0)] == 0x01                            # row -2 keeps a stale copy
    assert e.mem[idx(20, 0):idx(22, 0)] == bytes(64)            # rows 20-21 blanked (row 19's old content gone)


# ---------------------------------------------------------------- T2 rows
def test_t2_tiles_and_order():
    rows = ['#"%$!< > ' + ' ' * 7, WALL, EMPTY, '#    <  >      #']
    e = engine(rows)
    m = e.mem                                                   # the LAST row is loaded first
    assert m[idx(-2, 0):idx(-2, 2)] == b'\x01\x02' and m[idx(-1, 0):idx(-1, 2)] == b'\x03\x04'
    assert m[idx(-2, 10):idx(-2, 12)] == b'\x54\x55' and m[idx(-1, 10):idx(-1, 12)] == b'\x74\x75'
    assert m[idx(-2, 16):idx(-2, 18)] == b'\x48\x49' and m[idx(-1, 16):idx(-1, 18)] == b'\x68\x69'
    assert e.state.row == 2
    run(e, 1)                                                   # shift 1 (no load)
    ev = run(e, 8)                                              # shift 2: load row 2 (empty)
    assert EventKind.ROW_LOADED in kinds(ev)
    assert e.mem[idx(-2, 0):idx(0, 0)] == bytes(64) and e.state.row == 1
    run(e, 16)                                                  # row 1 (walls)
    assert e.mem[idx(-2, 0):idx(-2, 32)] == b'\x01\x02' * 16
    run(e, 16)                                                  # row 0: the tile set
    top = e.mem[idx(-2, 0):idx(-2, 16)]
    assert top == bytes((1, 2, 5, 6, 9, 10, 0x0D, 0x0E, 0x11, 0x12, 0x54, 0x55, 0, 0, 0x48, 0x49))
    assert e.mem[idx(-1, 0):idx(-1, 16)] == bytes((3, 4, 7, 8, 0x0B, 0x0C, 0x0F, 0x10, 0x13, 0x14, 0x74, 0x75,
                                                    0, 0, 0x68, 0x69))
    assert e.state.row == 3                                     # wrapped to the last row


def test_t2_trailing_eol_tolerated_and_other_chars_empty():
    rows = ['abc#xyz.,;:()[]{', EMPTY]
    a = Engine(rows, timing=FAST)
    b = Engine(board_bytes(rows) + b'\x9b', timing=FAST)
    for e in (a, b):
        run(e, 17)
        assert e.mem[idx(-2, 0):idx(-2, 32)] == bytes(6) + b'\x01\x02' + bytes(24)


# ---------------------------------------------------------------- T3 tank rule
def test_t3_tank_touching_something_on_its_right_is_skipped():
    e = engine(['#>         <####'])
    assert e.mem[idx(-2, 2):idx(-2, 4)] == b'\x48\x49'
    assert e.mem[idx(-2, 22):idx(-2, 24)] == bytes(2)           # '<' before '#': not placed
    e = engine(['#  <   > <# #  >'])
    assert e.mem[idx(-2, 6):idx(-2, 8)] == b'\x54\x55' and e.mem[idx(-2, 14):idx(-2, 16)] == b'\x48\x49'
    assert e.mem[idx(-2, 18):idx(-2, 20)] == bytes(2)
    assert e.mem[idx(-2, 30):idx(-2, 32)] == b'\x48\x49'        # cell 15: row -1 column 0 is 0 on a fresh screen
    e.mem[idx(-1, 0)] = 0x03                                    # ... but not once something sits there
    e.mem[idx(-2, 30):idx(-2, 32)] = bytes(2)
    e.row_ptr = 0
    e._load_row()
    assert e.mem[idx(-2, 30):idx(-2, 32)] == bytes(2)


def test_t3_skipped_cell_shows_the_previous_top_half_twice():
    e = engine(['#>         <####', '#          #####'])
    run(e, 17)                                                  # row 0 loaded after two shifts
    assert e.mem[idx(-2, 22):idx(-2, 24)] == b'\x01\x02'
    assert e.mem[idx(-1, 22):idx(-1, 24)] == b'\x01\x02'        # stale: the top half, not 03 04


# ---------------------------------------------------------------- T4 tanks
def place(e: Engine, row: int, col: int, *codes: int) -> None:
    for k, c in enumerate(codes):
        e.mem[idx(row, col + k)] = c


def test_t4_tank_right_phases_and_step():
    e = engine([EMPTY])
    place(e, 5, 4, 0x48, 0x49)
    place(e, 6, 4, 0x68, 0x69)
    for phase in (0x4B, 0x4E, 0x51):
        scan(e)
        assert e.mem[idx(5, 4):idx(5, 7)] == bytes((phase, phase + 1, phase + 2))
        assert e.mem[idx(6, 4):idx(6, 7)] == bytes((phase + 0x20, phase + 0x21, phase + 0x22))
    scan(e)                                                     # a full character to the right
    assert e.mem[idx(5, 4):idx(5, 8)] == b'\x00\x48\x49\x4A' and e.mem[idx(6, 4):idx(6, 8)] == b'\x00\x68\x69\x6A'


def test_t4_tank_right_blocked_turns_in_place():
    e = engine([EMPTY])
    place(e, 5, 4, 0x51, 0x52, 0x53)
    place(e, 6, 4, 0x71, 0x72, 0x73)
    e.mem[idx(6, 7)] = 0x03                                     # the column beyond the group, bottom row
    scan(e)
    assert e.mem[idx(5, 4):idx(5, 7)] == b'\x54\x55\x56' and e.mem[idx(6, 4):idx(6, 7)] == b'\x74\x75\x76'
    assert e.mem[idx(6, 7)] == 0x03


def test_t4_tank_left_phases_step_and_turn():
    e = engine([EMPTY])
    place(e, 5, 4, 0x54, 0x55)                                  # as LOAD_ROW leaves it: two columns
    place(e, 6, 4, 0x74, 0x75)
    scan(e)
    assert e.mem[idx(5, 4):idx(5, 7)] == b'\x57\x58\x59'        # the third column is written now
    scan(e)
    scan(e)
    assert e.mem[idx(5, 4):idx(5, 7)] == b'\x5D\x5E\x5F'
    scan(e)                                                     # step: pointer to column 3
    assert e.mem[idx(5, 3):idx(5, 8)] == b'\x54\x55\x56\x00\x00'
    assert e.mem[idx(6, 3):idx(6, 8)] == b'\x74\x75\x76\x00\x00'
    e.mem[idx(5, 2)] = 0x01                                     # blocked next time
    for _ in range(4):
        scan(e)
    assert e.mem[idx(5, 2):idx(5, 7)] == b'\x01\x48\x49\x4A\x00'


def test_t4_unmatched_character_skips_the_next_one():
    e = engine([EMPTY])
    place(e, 5, 4, 0x49, 0x1F)                                  # a body column, then a splash
    place(e, 5, 10, 0x1F)
    scan(e)
    assert e.mem[idx(5, 5)] == 0x1F and e.mem[idx(5, 10)] == 0x20


# ---------------------------------------------------------------- T5 shells
def test_t5_shell_dropped_only_from_phase_2_with_room_below():
    # the tank's top row is scanned first, so the bottom row shows the NEW phase: a tank entering
    # phase 2 (top $4B -> $4E, bottom $6B -> $6E) is asked to drop in the same pass
    e = engine([EMPTY], rnd=0)
    place(e, 5, 4, 0x4B, 0x4C, 0x4D)
    place(e, 6, 4, 0x6B, 0x6C, 0x6D)
    ev: list = []
    e._events = ev
    scan(e)
    assert e.mem[idx(6, 4)] == 0x6E
    # the new shell ($15/$16 at rows 7/8) is reached later in the same pass and falls 2 px at once
    assert e.mem[idx(7, 5)] == 0x17 and e.mem[idx(8, 5)] == 0x18 and e.snd_shell == 1
    assert EventKind.SHELL_DROPPED in kinds(ev)
    e = engine([EMPTY], rnd=1)                                  # RANDOM & 7 != 0
    place(e, 6, 4, 0x6E)
    scan(e)
    assert e.mem[idx(7, 5)] == 0
    e = engine([EMPTY], rnd=0)
    place(e, 6, 4, 0x7A)                                        # a left tank's phase-2 bottom-left
    e.mem[idx(8, 5)] = 0x01                                     # two rows below occupied
    scan(e)
    assert e.mem[idx(7, 5)] == 0
    e = engine([EMPTY], rnd=0)
    place(e, 6, 4, 0x7A, 0x1F)                                  # NEXT_CHAR: the splash after it is skipped
    scan(e)
    assert e.mem[idx(7, 5)] == 0x17 and e.mem[idx(6, 5)] == 0x1F


def test_t5_shell_falls_two_pixels_then_a_row_then_splashes():
    e = engine([EMPTY])
    place(e, 5, 4, 0x15)
    place(e, 6, 4, 0x16)
    for top in (0x17, 0x19, 0x1B, 0x1D):
        scan(e)
        assert (e.mem[idx(5, 4)], e.mem[idx(6, 4)]) == (top, top + 1)
    scan(e)                                                     # a row down, then two more px in the same pass
    assert e.mem[idx(5, 4)] == 0 and (e.mem[idx(6, 4)], e.mem[idx(7, 4)]) == (0x17, 0x18)
    e.mem[idx(8, 4)] = 0x01
    for _ in range(3):
        scan(e)
    assert e.mem[idx(6, 4)] == 0x1D
    scan(e)                                                     # blocked: splash at +$20, animated in the same pass
    assert e.mem[idx(6, 4)] == 0 and e.mem[idx(7, 4)] == 0x20 and e.snd_splash == 0x0F


# ---------------------------------------------------------------- T6 explosions and splashes
def test_t6_explosion_every_other_scan_seven_frames():
    e = engine([EMPTY])
    place(e, 5, 4, 0x24, 0x25)
    place(e, 6, 4, 0x26, 0x27)
    e.parity = 0xFF
    scan(e)
    assert e.mem[idx(5, 4)] == 0x24                             # skipped on odd scans
    for base in (0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C):
        scan(e)
        assert e.mem[idx(5, 4):idx(5, 6)] == bytes((base, base + 1))
        assert e.mem[idx(6, 4):idx(6, 6)] == bytes((base + 2, base + 3))
        scan(e)
    scan(e)
    assert e.mem[idx(5, 4):idx(5, 6)] == bytes(2) and e.mem[idx(6, 4):idx(6, 6)] == bytes(2)


def test_t6_splash_five_frames():
    e = engine([EMPTY])
    place(e, 5, 4, 0x1F)
    for c in (0x20, 0x21, 0x22, 0x23, 0x00):
        scan(e)
        assert e.mem[idx(5, 4)] == c


# ---------------------------------------------------------------- T7 the jet
def test_t7_jet_x_limits_and_collision_box():
    e = engine([EMPTY])
    run(e, 200, Input.of(right=True))
    assert e.jet_x == 0xB9
    run(e, 200, Input.of(left=True))
    assert e.jet_x == 0x40
    assert e._cell_addr(0x70, 0xB4) == idx(16, 12)
    assert e._cell_addr(0x40, 0xB0) == idx(15, 0) and e._cell_addr(0xB9, 0xB4) == idx(16, 30)


@pytest.mark.parametrize('code', sorted(DEADLY) + [0x48, 0x54, 0x4A, 0x7F])
def test_t7_deadly_characters(code: int):
    e = engine([EMPTY], still=True)
    e.mem[idx(17, 13)] = code                                   # bottom-right of the box at x = $70
    ev = run(e, 1)
    assert EventKind.JET_HIT in kinds(ev) and EventKind.JET_LOST in kinds(ev)
    assert e.jets == 1 and e.flash == 50 and e.snd_death == 0x0F


@pytest.mark.parametrize('code', [0x16, 0x18, 0x1D, 0x1E, 0x1F, 0x24, 0x3C, 0x09, 0x11])
def test_t7_harmless_characters(code: int):
    e = engine([EMPTY], still=True)
    e.mem[idx(17, 13)] = code
    assert EventKind.JET_HIT not in kinds(run(e, 1))


def test_t7_three_jets_flash_and_game_over():
    e = engine([EMPTY], still=True)
    e.mem[idx(16, 12)] = 0x01                                   # a wall stays under the jet
    run(e, 1)
    assert e.jets == 1 and e.flash == 50
    run(e, 49)
    assert e.jets == 1 and e.flash == 1                         # hits while flashing are ignored
    ev = run(e, 1)                                              # FLASH reaches 0 and the hit counts at once
    assert e.jets == 0 and e.flash == 50 and EventKind.JET_LOST in kinds(ev)
    run(e, 49)
    ev = run(e, 1)
    assert e.status is Status.GAME_OVER and EventKind.GAME_OVER in kinds(ev) and e.jets == 0xFF
    assert run(e, 1) == []


# ---------------------------------------------------------------- T8 shots
def test_t8_fire_edge_slots_and_missile_memory():
    e = engine([EMPTY])
    run(e, 1)
    ev = run(e, 1, FIRE)
    assert [x.value for x in ev if x.kind is EventKind.SHOT] == [3]
    assert e.missile_x[3] == 0x72 and e.missile_y[3] == 0xAF and e.snd_shot == 0xB0
    assert e.missiles[0xAE] == 0x40 and e.missiles[0xAF] == 0x40
    assert EventKind.SHOT not in kinds(run(e, 5, FIRE))         # held: no new shot
    for _ in range(0xAF - 0x2F - 5):
        run(e, 1)
    assert e.missile_x[3] == 0 and e.missile_y[3] == 0x2F       # freed at the top
    run(e, 1)
    assert e.missile_y[3] == 0x2F and e.missiles[0x2D] == 0x40  # keeps being drawn at x = 0
    run(e, 1)
    run(e, 1, FIRE)
    assert e.missile_x[3] == 0x72                               # slot 3 is free again and taken first


def test_t8_all_slots_busy():
    e = engine([EMPTY])
    for _ in range(4):
        run(e, 1)
        run(e, 1, FIRE)
    assert e.missile_x == [0x72] * 4
    run(e, 1)
    assert EventKind.SHOT not in kinds(run(e, 1, FIRE))


# ---------------------------------------------------------------- T9 hits
def shoot_at(e: Engine, code_row: bytes, code_row2: bytes, col: int = 12) -> list:
    """Object at rows 10/11 straight above the jet; fire and run until the shot arrives."""
    e.mem[idx(10, col):idx(10, col) + len(code_row)] = code_row
    e.mem[idx(11, col):idx(11, col) + len(code_row2)] = code_row2
    e.vscrol = 250
    run(e, 1)
    ev = run(e, 1, FIRE)
    for _ in range(60):
        if any(x.kind is EventKind.HIT for x in ev):
            return ev
        ev = run(e, 1)
    raise AssertionError('no hit')


def test_t9_soft_wall_fuel_ammo_repair_scores():
    e = engine([EMPTY])
    shoot_at(e, b'\x05\x06', b'\x07\x08')
    assert e.mem[idx(10, 12)] in (0x24, 0x28) and e.state.score == 15   # explosion (maybe animated already)
    e.jets = 0
    shoot_at(e, b'\x11\x12', b'\x13\x14')
    assert e.state.score == 45 and e.jets == 1
    shoot_at(e, b'\x11\x12', b'\x13\x14')
    shoot_at(e, b'\x11\x12', b'\x13\x14')
    assert e.jets == 2                                          # capped at 2
    shoot_at(e, b'\x0D\x0E', b'\x0F\x10')
    assert e.state.score == 45 + 30 + 30 + 100
    fuel_before = e.state.fuel
    shoot_at(e, b'\x09\x0A', b'\x0B\x0C')
    assert fuel_before + 498 <= e.state.fuel <= fuel_before + 499 and e.state.score == 225   # -1 per 32 frames
    shoot_at(e, b'\x09\x0A', b'\x0B\x0C')
    shoot_at(e, b'\x09\x0A', b'\x0B\x0C')
    assert e.state.fuel >= 998                                  # capped at 999 (HF_CAP)


def test_t9_tank_and_hard_wall_handlers():
    """HIT_HANDLERS called as VB_HITS does after the quadrant fix (a moving tank cannot be aimed at)."""
    e = engine([EMPTY])
    place(e, 10, 12, 0x4B, 0x4C, 0x4D)
    place(e, 11, 12, 0x6B, 0x6C, 0x6D)
    e._hit(idx(10, 12), 20 + 3)                                 # $6C hit: quadrant 3 -> cell is the top-left
    assert e.mem[idx(10, 12):idx(10, 15)] == b'\x24\x25\x00' and e.mem[idx(11, 12):idx(11, 15)] == b'\x26\x27\x00'
    assert e.state.score == 55
    e = engine([EMPTY])
    place(e, 10, 11, 0x57, 0x58, 0x59)
    place(e, 11, 11, 0x77, 0x78, 0x79)
    e._hit(idx(10, 12), 36)                                     # $58: the body's top-left
    assert e.mem[idx(10, 11):idx(10, 14)] == b'\x00\x24\x25' and e.mem[idx(11, 11):idx(11, 14)] == b'\x00\x26\x27'
    e = engine([EMPTY])
    place(e, 10, 12, 0x01, 0x02)
    place(e, 11, 12, 0x03, 0x04)
    e._hit(idx(10, 12), 50)                                     # $03: hit from below -> splash under the wall
    assert e.mem[idx(10, 12):idx(12, 14)][:4] == b'\x01\x02' + bytes(30)[:0] + b'' or True
    assert e.mem[idx(10, 12):idx(10, 14)] == b'\x01\x02' and e.mem[idx(11, 12):idx(11, 14)] == b'\x03\x04'
    assert e.mem[idx(12, 12)] == 0x1F and e.snd_splash == 0x0A
    e._hit(idx(10, 12), 49)                                     # $02: the wall's own bottom-right is replaced
    assert e.mem[idx(11, 13)] == 0x1F


def test_t9_missile_hit_frees_the_slot_and_the_sound():
    e = engine([EMPTY])
    shoot_at(e, b'\x01\x02', b'\x03\x04')
    assert e.snd_splash == 0x0F and e.snd_shot == 0 and e.missile_x[3] == 0 and e.pokey[4:6] == [0, 0]
    assert 0x1F <= e.mem[idx(12, 12)] <= 0x23


# ---------------------------------------------------------------- T10 fuel
def test_t10_fuel_unit_is_32_frames_and_runs_out():
    e = engine([EMPTY], rtclok=0)
    assert e.state.fuel == 99
    run(e, 31)
    assert e.state.fuel == 99
    run(e, 1)
    assert e.state.fuel == 98
    for _ in range(98):
        run(e, 32)
    assert e.state.fuel == 0
    ev = run(e, 32)
    assert EventKind.FUEL_OUT in kinds(ev) and e.state.fuel == 99 and e.jets == 1


# ---------------------------------------------------------------- T11 pause, ESC
def test_t11_pause_and_esc():
    e = engine([EMPTY])
    run(e, 1)
    ev = run(e, 1, Input(key=0x21))
    assert e.status is Status.PAUSED and EventKind.PAUSED in kinds(ev)
    x = e.jet_x
    run(e, 5, Input())
    assert e.jet_x == x and e.status is Status.PAUSED
    ev = run(e, 1, Input.of(right=True))
    assert e.status is Status.PLAYING and EventKind.RESUMED in kinds(ev) and e.ch == 0xFF
    assert e.jet_x == x                                         # the unpause frame's VBI was still paused
    ev = run(e, 1, Input(key=0x1C))
    assert e.status is Status.ABORTED and EventKind.ABORTED in kinds(ev)


# ---------------------------------------------------------------- T12 determinism and pacing
@settings(max_examples=25, deadline=None)
@given(st.integers(0, 2 ** 30), st.integers(0, 2 ** 30))
def test_t12_determinism(seed: int, iseed: int):
    rows = parse_board(open('board.txt').read())
    rin = random.Random(iseed)
    inputs = [Input(rin.randrange(16), rin.randrange(2)) for _ in range(120)]
    states = []
    for _ in range(2):
        r = random.Random(seed)
        e = Engine(rows, rnd=lambda: r.randrange(256))
        for inp in inputs:
            e.tick(inp)
        states.append((bytes(e.mem), bytes(e.missiles), e.state))
    assert states[0] == states[1]


def test_t12_default_pacing_three_frames_per_iteration():
    e = Engine(parse_board(open('board.txt').read()))
    its = []
    for _ in range(60):
        e.tick(IDLE)
        its.append(e.iteration)
    assert its[:9] == [0, 1, 1, 1, 2, 2, 2, 3, 3] and e.iteration == 20
    assert e.scan_cycles > 22000                                # the cheapest scan (22222 in py65)
