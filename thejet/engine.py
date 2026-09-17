"""The Jet engine -- a literal re-implementation of the main loop, SCAN and the VBI of game.asm.

The screen memory is the game state (SPEC.md §1): `mem` holds the 24 character rows of 32
bytes the original keeps from $3B43 (rows -2..21) followed by the 32-byte status line, and
every handler here writes into it with the same pointer arithmetic as the 6502 code. Each
routine names the label of game.asm it mirrors. The main loop is a generator that gives
control back whenever the original would be waiting for the vertical blank or would be
interrupted by it: the CPU time of a frame is modelled by counting the cycles of the code
paths taken (the constants beside each path are the 6502 instruction timings of game.asm)
against a per-frame budget (`Timing`, SPEC.md §7). Stdlib only, deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterator, Sequence

COLS, ROWS = 32, 24                 # 32 characters per row; rows -2..21
HUD = ROWS * COLS                   # index of the status line in `mem`
MEM_SIZE = HUD + 32
ROW_M1 = COLS                       # index of row -1 ($3B63); SCAN starts here
ROW_20 = 22 * COLS                  # $3E03: end of the scan, start of the blanked rows
SCREEN_LO = 0x43                    # low byte of SCREEN ($3B43): for the page-crossing penalties
EOL = 0x9B
BOARD_W = 16

# LOAD_ROW tables (TILE_CHARS, TILE_TL/TR/BL/BR); index 0 = empty
TILE_INDEX = {0x23: 1, 0x22: 2, 0x25: 3, 0x24: 4, 0x21: 5, 0x3C: 6, 0x3E: 7}     # # " % $ ! < >
TILE_TL = (0x00, 0x01, 0x05, 0x09, 0x0D, 0x11, 0x54, 0x48)
TILE_TR = (0x00, 0x02, 0x06, 0x0A, 0x0E, 0x12, 0x55, 0x49)
TILE_BL = (0x00, 0x03, 0x07, 0x0B, 0x0F, 0x13, 0x74, 0x68)
TILE_BR = (0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x75, 0x69)
# SCAN_CHARS[1..27] (entry 0 is never compared); the index decides the handler and the search cost
SCAN_CHARS = (0x1C, 0x48, 0x4B, 0x4E, 0x51, 0x54, 0x57, 0x5A, 0x5D, 0x7A, 0x6E,
              0x15, 0x17, 0x19, 0x1B, 0x1D, 0x1F, 0x20, 0x21, 0x22, 0x23,
              0x24, 0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C)
SCAN_INDEX = {c: k for k, c in enumerate(SCAN_CHARS) if k}
EXPL_FRAMES = (0x24, 0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C, 0x00)
# HIT_CHARS: 52 entries, i & 3 = quadrant, i // 4 = object
HIT_CHARS = (0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14,
             0x48, 0x49, 0x68, 0x69, 0x4B, 0x4C, 0x6B, 0x6C, 0x4E, 0x4F, 0x6E, 0x6F, 0x51, 0x52, 0x71, 0x72,
             0x55, 0x56, 0x75, 0x76, 0x58, 0x59, 0x78, 0x79, 0x5B, 0x5C, 0x7B, 0x7C, 0x5E, 0x5F, 0x7E, 0x7F,
             0x01, 0x02, 0x03, 0x04)
HIT_INDEX = {c: k for k, c in enumerate(HIT_CHARS)}
QUADRANT_DELTA = (0, -1, -0x20, -0x21)           # Q0..Q3: CELL -> the object's top-left
DEADLY_LIST = (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x15, 0x17, 0x19, 0x1A, 0x1B, 0x1C)
DEADLY = frozenset(DEADLY_LIST)
DEADLY_ORDER = {c: k for k, c in enumerate(DEADLY_LIST)}     # JET_PROBE searches from the end
MISSILE_MASKS = (0x01, 0x04, 0x10, 0x40)
HUD_INIT = bytes.fromhex('2675656c1a10101000' '24616d6167651a545454' '0033636f72651a101010101010')
JET_X_MIN, JET_X_MAX, JET_X_START = 0x40, 0xB9, 0x70
JET_Y, JET_PROBE_Y, MISSILE_START_Y, MISSILE_TOP = 0xB0, 0xB4, 0xB0, 0x30
FLASH_FRAMES, START_JETS, START_FUEL, FUEL_TILE, FUEL_MAX = 50, 2, 0x99, 0x499, 0x999
KEY_ESC, KEY_SPACE = 0x1C, 0x21


class Input:
    """STICK0 bits (1 = released: $0F idle, bit 0 up, bit 2 left, bit 3 right), STRIG0 (0 = pressed),
    and the OS key code left in CH (None = no key)."""
    __slots__ = ('stick', 'trig', 'key')

    def __init__(self, stick: int = 0x0F, trig: int = 1, key: int | None = None) -> None:
        self.stick, self.trig, self.key = stick & 0x0F, 1 if trig else 0, key

    @classmethod
    def of(cls, *, up: bool = False, left: bool = False, right: bool = False, fire: bool = False,
           key: int | None = None) -> 'Input':
        return cls(0x0F & ~((1 if up else 0) | (4 if left else 0) | (8 if right else 0)), 0 if fire else 1, key)


class Status(Enum):
    PLAYING = 'playing'
    PAUSED = 'paused'
    GAME_OVER = 'game_over'     # the third jet lost: FADE_OUT then the title screen
    ABORTED = 'aborted'         # ESC: FADE_OUT then the title screen


class EventKind(Enum):
    SHIFTED = 'shifted'                 # SC_SHIFT: rows moved down one character row
    ROW_LOADED = 'row_loaded'           # LOAD_ROW: value = the board row index (0 = first row of the file)
    SHOT = 'shot'                       # VB_SHOOT: value = missile slot
    HIT = 'hit'                         # a missile hit: cell = object top-left, value = HIT_CHARS index // 4
    SHELL_DROPPED = 'shell_dropped'     # TD_DROP: cell = the shell's top character
    SPLASH = 'splash'                   # SH_SPLASH: cell = the splash character
    JET_HIT = 'jet_hit'                 # JP_DIE: DEATH set by a collision
    FUEL_OUT = 'fuel_out'               # VB_FUEL_OUT: DEATH set by the fuel
    JET_LOST = 'jet_lost'               # ML_LOSE_JET
    GAME_OVER = 'game_over'             # GAME_OVER
    PAUSED = 'paused'
    RESUMED = 'resumed'
    ABORTED = 'aborted'                 # ESC
    VBI = 'vbi'                         # value = scan index at which the VBI interrupted the scan, -1 if idle


@dataclass(frozen=True)
class Event:
    kind: EventKind
    cell: int = -1
    value: int = 0


@dataclass(frozen=True)
class Timing:
    """CPU cycles the game gets per frame, SPEC.md §7 **[EST]**: `vblank` in the vertical blank
    after the OS's own routines (the game's VBI, whose cycles the engine counts, comes out of
    it), `visible` in the displayed part minus the DLI's WSYNC wait of `dli_line` cycles per
    scanline for VSCROL+1 lines. Calibrated with tools/calibrate_timing.py."""
    vblank: int = 5883
    visible: int = 18645
    dli_line: int = 37

    def frame_budget(self, vscrol: int, vbi_cycles: int) -> int:
        """Main-loop cycles between the end of one VBI and the start of the next."""
        return self.vblank - vbi_cycles + self.visible - self.dli_line * (vscrol + 1)


DEFAULT_TIMING = Timing()


@dataclass(frozen=True)
class GameState:
    frame: int                  # RTCLOK (8 bit)
    vscrol: int
    jet_x: int
    missile_x: tuple[int, ...]
    missile_y: tuple[int, ...]
    fuel: int                   # decimal value of the BCD counter
    jets: int
    score: int                  # decimal value of the BCD counter
    flash: int
    death: bool
    row: int                    # board row index the next LOAD_ROW will take
    status: Status
    iteration: int              # main-loop iterations completed
    scan_index: int             # where the scan stands (ROW_20 = not scanning)


def parse_board(text: str) -> list[str]:
    """board.txt / plansze.txt -> rows (lines starting with ';' are comments)."""
    rows = [ln.rstrip('\r\n') for ln in text.replace('\x9b', '\n').split('\n')]
    if rows and rows[-1] == '':
        rows.pop()
    return [r for r in rows if not r.startswith(';')]


def board_bytes(rows: Sequence[str]) -> bytes:
    """The file the game reads: rows joined by EOL, none after the last."""
    return bytes([EOL]).join(r.encode('latin-1') for r in rows)


def bcd_to_int(*bytes_lo_first: int) -> int:
    v, mul = 0, 1
    for b in bytes_lo_first:
        v += ((b >> 4) * 10 + (b & 0x0F)) * mul
        mul *= 100
    return v


def bcd_add(a: int, b: int) -> tuple[int, int]:
    """(a + b) in packed BCD on one byte -> (result, carry). Both inputs valid BCD."""
    lo = (a & 0x0F) + (b & 0x0F)
    carry_lo = lo > 9
    hi = (a >> 4) + (b >> 4) + (1 if carry_lo else 0)
    lo = lo - 10 if carry_lo else lo
    carry = hi > 9
    hi = hi - 10 if carry else hi
    return (hi << 4) | lo, 1 if carry else 0


def bcd_sub(a: int, b: int, borrow: int = 0) -> tuple[int, int]:
    """a - b - borrow in packed BCD -> (result, borrow out)."""
    lo = (a & 0x0F) - (b & 0x0F) - borrow
    b_lo = lo < 0
    lo = lo + 10 if b_lo else lo
    hi = (a >> 4) - (b >> 4) - (1 if b_lo else 0)
    b_hi = hi < 0
    hi = hi + 10 if b_hi else hi
    return (hi << 4) | lo, 1 if b_hi else 0


class Engine:
    """One game from GAME_INIT to the fade-out; `tick` = one PAL frame (SPEC.md §2)."""

    def __init__(self, board: Sequence[str] | bytes, *, rnd: Callable[[], int] | None = None,
                 rtclok: int = 0, timing: Timing = DEFAULT_TIMING) -> None:
        self.board = bytes(board) if isinstance(board, (bytes, bytearray)) else board_bytes(board)
        if len(self.board) < BOARD_W:                          # INIT: no board -> one blank row
            self.board = bytes(BOARD_W)
        self.rnd = rnd if rnd is not None else _default_rnd()
        self.timing = timing
        self.mem = bytearray(MEM_SIZE)
        self.mem[HUD:] = HUD_INIT
        self.missiles = bytearray(256)                          # $2B00..$2BFF
        self.pokey = [0] * 8                                    # AUDF1, AUDC1, ... AUDF4, AUDC4
        self.frame = rtclok & 0xFF                              # RTCLOK low byte
        self.stick, self.trig, self.ch = 0x0F, 1, 0xFF
        # GI_VARS
        self.vscrol = 0
        self.row_toggle = 0
        self.parity = 0
        self.flash = 0
        self.snd_shell = self.snd_splash = self.snd_shot = self.snd_death = 0
        self.jet_x = JET_X_START
        self.missile_x = [0, 0, 0, 0]
        self.missile_y = [0, 0, 0, 0]                           # GI_MISSILES: $2F then 0
        self.trig_prev = 0
        self.death = 0
        self.fuel_lo, self.fuel_hi = START_FUEL, 0
        self.jets = START_JETS
        self.score = [0, 0, 0]                                  # SCORE, SCORE_1, SCORE_2 (BCD)
        self.paused = 0
        self.status = Status.PLAYING
        self.row_ptr = len(self.board) - BOARD_W               # BOARD_END
        self.iteration = 0
        self.scan_index = ROW_20                                # where the scan stands (ROW_20 = idle)
        self.last_split = -1                                    # SC_CHAR visits before the last mid-scan VBI
        self.cycles = 0                                         # main-loop cycles used in this frame
        self.scan_cycles = 0                                    # cycle model: the last complete scan (JSR..RTS)
        self.scroll_cycles = 0                                  # cycle model: the last SCROLL (JSR..RTS)
        self.vbi_cycles = 0                                     # cycle model: the last VBI (VBI .. JMP XITVBV)
        self.iteration_start = 0                                # RTCLOK when the current iteration began
        self.record_costs = False                               # keep `scan_trace` (tools/calibrate_timing.py)
        self.scan_trace: dict[int, int] = {}                    # index -> scan cycles before its first visit
        self._events: list[Event] = []
        self._load_row()
        self._main = self._main_loop()

    # ----------------------------------------------------------------- public
    @property
    def state(self) -> GameState:
        return GameState(self.frame, self.vscrol, self.jet_x, tuple(self.missile_x), tuple(self.missile_y),
                         bcd_to_int(self.fuel_lo, self.fuel_hi), self.jets, bcd_to_int(*self.score),
                         self.flash, bool(self.death), self._row_index(self.row_ptr), self.status, self.iteration,
                         self.scan_index)

    def tick(self, inp: Input) -> list[Event]:
        """One frame: the VBI with these inputs, then the main loop until it waits or the frame is over."""
        self._events = []
        if self.status in (Status.GAME_OVER, Status.ABORTED):
            return []
        self.stick, self.trig = inp.stick, inp.trig
        if inp.key is not None:
            self.ch = inp.key
        self.frame = (self.frame + 1) & 0xFF
        self._emit(EventKind.VBI, value=self.scan_index if self.scan_index < ROW_20 else -1)
        self._vbi()
        self.cycles = 0
        try:
            next(self._main)
        except StopIteration:
            pass
        return self._events

    # ----------------------------------------------------------------- helpers
    def _emit(self, kind: EventKind, cell: int = -1, value: int = 0) -> None:
        self._events.append(Event(kind, cell, value))

    def _add_score(self, bcd: int) -> None:
        """ADD_SCORE: SCORE += A (BCD), carries through SCORE_1 and SCORE_2."""
        self.score[0], c = bcd_add(self.score[0], bcd)
        self.score[1], c = bcd_add(self.score[1], c)
        self.score[2], _ = bcd_add(self.score[2], c)

    @staticmethod
    def _xpen(index: int, y: int) -> int:
        """+1 cycle of LDA (zp),Y when the pointer's low byte plus Y crosses a page."""
        return 1 if ((SCREEN_LO + index) & 0xFF) + y >= 0x100 else 0

    # ----------------------------------------------------------------- LOAD_ROW
    def _load_row(self) -> None:
        """LOAD_ROW: the 16 cells of the row at ROW_PTR into rows -2/-1, right to left (SPEC §3.3)."""
        b, p = self.board, self.row_ptr
        if p + 15 < len(b) and b[p + 15] == EOL:               # a row is 16 bytes + EOL: step back
            p -= 1
        row = bytes(b[p + k] if 0 <= p + k < len(b) else 0 for k in range(BOARD_W))
        m = self.mem
        for cell in range(BOARD_W - 1, -1, -1):
            t = TILE_INDEX.get(row[cell], 0)
            x = 2 * cell
            if TILE_TL[t] >= 0x48 and m[x + 2] != 0:            # a tank with something on its right
                continue
            m[x], m[x + 1] = TILE_TL[t], TILE_TR[t]
            m[ROW_M1 + x], m[ROW_M1 + x + 1] = TILE_BL[t], TILE_BR[t]
        self._emit(EventKind.ROW_LOADED, value=self._row_index(p))
        p -= BOARD_W
        if p < 0:                                               # LR_WRAP: below BOARD -> the last row
            p = len(b) - BOARD_W
        self.row_ptr = p

    def _row_index(self, p: int) -> int:
        return self.board[:p].count(EOL)

    # ----------------------------------------------------------------- SCROLL
    def _scroll(self) -> int:
        """SCROLL: returns the cycles used (JSR .. RTS)."""
        self.vscrol -= 1
        cycles = 6 + 6 + 4 + 2                                  # JSR, DEC, LDA STICK0, AND
        if not self.stick & 1:                                  # stick up: twice as fast
            self.vscrol -= 1
            cycles += 2 + 6                                     # BNE not taken, DEC
        else:
            cycles += 3
        cycles += 4 + 4                                         # LDA, STA VSCROL
        if self.vscrol >= 0:
            return cycles + 2 + 3 + 6                           # BMI not taken, JMP RTS1, RTS
        self.vscrol = 7
        cycles += 3 + 2 + 4 + 4                                 # BMI, LDA #7, STA, STA VSCROL
        m = self.mem
        m[ROW_M1:ROW_20] = m[0:ROW_20 - COLS]                   # SC_COPY: rows -2..18 -> -1..19
        m[ROW_20:HUD] = bytes(2 * COLS)                         # SC_CLEAR_BOTTOM
        # SC_COPY: LDY #$1F; 32 x (21 x (LDA abs,Y 4 + STA abs,Y 5) + DEY 2 + BMI 2/3 + JMP 3); the
        # abs,Y reads cross a page when the row's low byte + Y >= $100 (+1 each)
        cycles += 2
        for y in range(0x1F, -1, -1):
            for row in range(21):                               # source rows -2..18
                lo = (SCREEN_LO + row * COLS) & 0xFF
                cycles += 4 + (1 if lo + y >= 0x100 else 0) + 5
            cycles += 2 + (3 + 3 if y else 3)                   # DEY, BMI (taken at the end) / not + JMP
        cycles += 2 + 64 * (2 + 5 + 2 + 3) - 1                  # SC_CLEAR_BOTTOM: LDY #$3F, LDA #0 .. BPL
        cycles += 4 + 2 + 4                                     # SC_TOGGLE: LDA, EOR, STA
        self.row_toggle ^= 0xFF
        self._emit(EventKind.SHIFTED)
        if self.row_toggle == 0:
            cycles += 3 + self._load_row_cycles()
            self._load_row()
            return cycles + 6                                   # RTS of LOAD_ROW
        return cycles + 2 + 6                                   # BEQ not taken, RTS

    def _load_row_cycles(self) -> int:
        """LOAD_ROW's cost is content-dependent; an average of its paths [EST] is close enough
        for the frame budget (it runs every 16 iterations)."""
        return 2 + 5 + 2 + 2 + 16 * (2 + 3 + 5 + 2 + 7 * 11 + 22 + 6 + 2 + 2 + 4 + 2 + 2) + 20

    # ----------------------------------------------------------------- SCAN
    def _scan(self) -> Iterator[None]:
        """SCAN: rows -1..19 in memory order, in place; yields when the frame's CPU time is used up."""
        m = self.mem
        i = ROW_M1
        step = 0                                                # SC_CHAR visits in this scan
        acc, mark = 0, self.cycles                              # the scan's own cycles across frames
        self.cycles += 6 + 10                                   # JSR SCAN, SCAN_PTR set-up
        deadline = self.timing.frame_budget(self.vscrol, self.vbi_cycles)
        trace = self.scan_trace = {} if self.record_costs else self.scan_trace
        while i < ROW_20:
            if self.record_costs:
                trace.setdefault(i, acc + self.cycles - mark)
            if self.cycles >= deadline:                         # the VBI interrupts here
                self.scan_index = i
                self.last_split = step
                acc += self.cycles - mark
                yield
                mark = 0                                        # `cycles` restarts from 0 after the VBI
                deadline = self.timing.frame_budget(self.vscrol, self.vbi_cycles)
            step += 1
            c = m[i]
            wrap = 4 if ((SCREEN_LO + i + 1) & 0xFF) == 0 else 0   # INC SCAN_PTR+1 on a page boundary
            if c < 0x15:
                self.cycles += 33 + wrap
                i += 1
                continue
            k = SCAN_INDEX.get(c, 0)
            self.cycles += 11 + 2 + (27 - k) * 11 + (7 if k else -1) + 22 + 6   # dispatch
            i = self._handle(i, c, k)
            self.cycles += 21 + wrap                            # SC_NEXT .. BCC SC_CHAR
            i += 1
        self.cycles += 16 - 1                                   # SC_END, last BCC not taken
        self.scan_cycles = acc + self.cycles - mark
        self.scan_index = ROW_20
        self.parity ^= 0xFF

    def _handle(self, i: int, c: int, k: int) -> int:
        """SCAN_HANDLERS[k] with SCAN_PTR = i; returns the pointer as the handler leaves it."""
        if k == 0:                                              # NEXT_CHAR: skips the next character
            self.cycles += 14
            return i + 1
        if k <= 4:
            return self._tank_r(i, c)
        if k <= 8:
            return self._tank_l(i, c)
        if k <= 10:
            return self._tank_drop(i)
        if k <= 15:
            return self._shell(i, c)
        if k <= 20:
            return self._splash(i, c)
        return self._explosion(i, c)

    def _draw_tank(self, i: int, base: int) -> None:
        """DRAW_TANK: base, base+1, base+2 at i and base+$20.. one row below (141 cycles)."""
        m = self.mem
        for k in range(3):
            m[i + k] = base + k
            m[i + 0x20 + k] = base + 0x20 + k
        self.cycles += 141

    def _tank_r(self, i: int, c: int) -> int:
        """H_TANK_R."""
        m = self.mem
        if c + 3 < 0x54:                                        # next phase in place
            self.cycles += 15 + 3
            self._draw_tank(i, c + 3)
            return i
        self.cycles += 16 + 2 + 5 + self._xpen(i, 3)
        if m[i + 3] != 0:                                       # TR_TURN
            self.cycles += 3 + 7
            self._draw_tank(i, 0x54)
            return i
        self.cycles += 2 + 2 + 5 + self._xpen(i, 0x23)
        if m[i + 0x23] != 0:
            self.cycles += 3 + 7
            self._draw_tank(i, 0x54)
            return i
        self.cycles += 2 + 18 + 38 + 7
        m[i] = m[i + 0x20] = 0                                  # TR_ADVANCE
        self._draw_tank(i + 1, 0x48)
        return i + 1

    def _tank_l(self, i: int, c: int) -> int:
        """H_TANK_L."""
        m = self.mem
        if c + 3 < 0x60:
            self.cycles += 15 + 3
            self._draw_tank(i, c + 3)
            return i
        self.cycles += 16 + 18                                  # TL_STEP: SCAN_PTR -= 1
        i -= 1
        self.cycles += 2 + 5 + 2
        if m[i] != 0:                                           # TL_TURN
            self.cycles += 1 + 45
            self._draw_tank(i + 1, 0x48)
            return i + 1
        self.cycles += 2 + 5 + self._xpen(i, 0x20) + 2
        if m[i + 0x20] != 0:
            self.cycles += 1 + 45
            self._draw_tank(i + 1, 0x48)
            return i + 1
        self.cycles += 25
        m[i + 3] = m[i + 0x23] = 0                              # TL_ADVANCE
        self._draw_tank(i, 0x54)
        return i

    def _tank_drop(self, i: int) -> int:
        """H_TANK_DROP: RANDOM & 7 == 0, the two characters below the middle column empty."""
        m = self.mem
        if self.rnd() & 7:
            self.cycles += 14
            return i
        self.cycles += 9 + 2 + 5 + self._xpen(i, 0x21) + 2 + 5 + self._xpen(i, 0x41)
        if m[i + 0x21] | m[i + 0x41]:
            self.cycles += 2 + 6
            return i
        self.cycles += 3 + 45
        m[i + 0x21], m[i + 0x41] = 0x15, 0x16                   # TD_DROP
        self.snd_shell = 1
        self._emit(EventKind.SHELL_DROPPED, i + 0x21)
        return i + 1                                            # NEXT_CHAR

    def _shell(self, i: int, c: int) -> int:
        """H_SHELL."""
        m = self.mem
        if c + 2 < 0x1E:
            self.cycles += 39
            m[i], m[i + 0x20] = c + 2, c + 3
            return i
        self.cycles += 16 + 2 + 5 + self._xpen(i, 0x40) + 2
        if m[i + 0x40] != 0:                                    # SH_SPLASH
            self.cycles += 1 + 32
            m[i + 0x20], m[i] = 0x1F, 0
            self.snd_splash = 0x0F
            self._emit(EventKind.SPLASH, i + 0x20)
            return i
        self.cycles += 38                                       # SH_MOVE
        m[i + 0x20], m[i + 0x40], m[i] = 0x15, 0x16, 0
        return i

    def _splash(self, i: int, c: int) -> int:
        """H_SPLASH."""
        if c + 1 < 0x24:
            self.cycles += 28
            self.mem[i] = c + 1
        else:
            self.cycles += 29
            self.mem[i] = 0
        return i

    def _explosion(self, i: int, c: int) -> int:
        """H_EXPLOSION: every other scan; NEXT_CHAR afterwards."""
        m = self.mem
        if self.parity:
            self.cycles += 23
            return i + 1
        f = EXPL_FRAMES.index(c)
        self.cycles += 7 + 9 + 11 * (7 - f) + 7 + 4
        if f == 6:                                              # EX_CLEAR
            self.cycles += 2 + 38 + 14
            m[i] = m[i + 1] = m[i + 0x20] = m[i + 0x21] = 0
        else:
            self.cycles += 3 + 45 + 14
            b = EXPL_FRAMES[f + 1]
            m[i], m[i + 1], m[i + 0x20], m[i + 0x21] = b, b + 1, b + 2, b + 3
        return i + 1

    # ----------------------------------------------------------------- VBI
    def _vbi(self) -> None:
        """VBI: sounds, then (unless paused) the jet, the shots, the collisions, the fuel, the HUD.
        `vbi_cycles` counts the path taken (VBI .. JMP XITVBV)."""
        cy = 13 + self._sounds()                                # VSCROL, ATRACT, the four envelopes
        if self.paused:
            self.vbi_cycles = cy + 4 + 2 + 3 + 5                # VB_PAUSED -> VBI_IDLE
            return
        cy += 4 + 2 + 3
        if not self.stick & 8:                                  # VB_STICK: right
            cy += 2 + 4 + 2 + 2
            if self.jet_x < JET_X_MAX:
                self.jet_x += 1
                cy += 2 + 6
            else:
                cy += 3
        else:
            cy += 3
        cy += 4 + 2
        if not self.stick & 4:                                  # VB_LEFT
            cy += 2 + 4 + 2
            if self.jet_x != JET_X_MIN:
                self.jet_x -= 1
                cy += 2 + 6
            else:
                cy += 3
        else:
            cy += 3
        cy += 4
        if self.trig != 0:                                      # VB_FIRE
            cy += 3
        elif self.trig_prev == 0:
            cy += 2 + 4 + 3
        else:                                                   # the trigger just went down
            cy += 2 + 4 + 2 + 2                                 # VB_SLOT
            for slot in (3, 2, 1, 0):
                if self.missile_x[slot] == 0:
                    cy += 4 + 3
                    self.missile_x[slot] = self.jet_x + 2       # VB_SHOOT
                    self.missile_y[slot] = MISSILE_START_Y
                    self.snd_shot = MISSILE_START_Y
                    cell = self._cell_addr(self.missile_x[slot], MISSILE_START_Y)
                    cy += 151 + (3 if self.mem[cell] == 0 else 5)
                    self._emit(EventKind.SHOT, cell, slot)
                    break
                cy += 11 if slot else 10
            else:
                cy += 3                                         # JMP VB_JET
        cy += 12 + 1763                                         # VB_JET, VB_MISSILES_CLEAR
        mm = self.missiles                                      # VB_MISSILES_CLEAR: y = $29..$D8
        mm[0x29:0xD9] = bytes(0xB0)
        cy += 2 - 1
        for x in (3, 2, 1, 0):                                  # VB_MISSILES
            self.missile_y[x] = (self.missile_y[x] - 1) & 0xFF
            y = self.missile_y[x]
            if y:                                               # STA MISSILES-1,Y: y = 0 lands outside
                mm[y - 1] = MISSILE_MASKS[x]
            mm[y] = MISSILE_MASKS[x]
            if y < MISSILE_TOP:
                self.missile_x[x] = 0
                self.missile_y[x] = MISSILE_TOP - 1
                cy += 61
            else:
                cy += 46
        cy += 2
        for x in (3, 2, 1, 0):                                  # VB_HITS
            cy += 2 + 3 + 2 + 4 + 4 + 2 + 4
            if self.missile_x[x] == 0:
                cy += 3 + (13 if x else 12)
                continue
            cell = self._cell_addr(self.missile_x[x], self.missile_y[x])
            cy += 2 + 2 + 86 + 2 + 5 + self._xpen(cell, 0) + 4
            c = self.mem[cell]
            k = HIT_INDEX.get(c)
            if c == 0:
                cy += 3 + (13 if x else 12)
                continue
            if k is None:
                cy += 2 + 2 + 51 * 11 + 10 + 3 + (13 if x else 12)
                continue
            cy += 2 + 2 + (51 - k) * 11 + 7 + 44                # VH_DISPATCH
            cell += QUADRANT_DELTA[k & 3]                       # quadrant fix
            cy += 6 + (6 if k & 3 == 0 else 24) + 6
            cy += self._hit(cell, k)
            self.snd_shot = 0
            self.pokey[4] = self.pokey[5] = 0                   # AUDF3, AUDC3
            self.snd_splash = 0x0F
            self.missile_x[x] = 0
            cy += 2 + 4 + 4 + 4 + 2 + 4 + 4 + 3 + 2 + 2 + 5 + (13 if x else 12)
            self._emit(EventKind.HIT, cell, k // 4)
        cell = self._cell_addr(self.jet_x, JET_PROBE_Y)        # VB_JET_HIT
        cy += 4 + 2 + 86
        for n, d in enumerate((0, 1, 0x20, 0x21)):
            cy += 2 + 6 + 5 + self._xpen(cell, d) + 2
            c = self.mem[cell + d]
            if c >= 0x48:
                cy += 3 + 12
            elif c in DEADLY:
                cy += 2 + 2 + (13 - DEADLY_ORDER[c]) * 11 + 7 + 3 + 12
            else:
                cy += 2 + 2 + 13 * 11 + 10 + 6
                continue
            self.death = 0xFF
            self._emit(EventKind.JET_HIT, cell + d)
            cy += 0                                             # JP_DIE returns; the probes go on
        cy += 3 + 2
        if self.frame & 0x1F == 0:                              # VB_FUEL: every 32 frames
            self.fuel_lo, b = bcd_sub(self.fuel_lo, 1)
            self.fuel_hi, _ = bcd_sub(self.fuel_hi, 0, b)
            cy += 2 + 26
        else:
            cy += 3
        cy += 4
        if self.fuel_hi & 0x80:                                 # VB_FUEL_OUT
            self.death = 0xFF
            self.fuel_hi, self.fuel_lo = 0, START_FUEL
            self._emit(EventKind.FUEL_OUT)
            cy += 2 + 18
        else:
            cy += 3
        hud = self.mem
        hud[HUD + 5] = 0x10 | (self.fuel_hi & 0x0F)             # VB_HUD_FUEL
        hud[HUD + 6], hud[HUD + 7] = 0x10 | (self.fuel_lo >> 4), 0x10 | (self.fuel_lo & 0x0F)
        for k in range(3):                                      # VB_HUD_JETS
            hud[HUD + 16 + k] = 0x6F if self.jets - (2 - k) >= 0 and self.jets < 0x80 else 0x54
        s = self.score                                          # VB_HUD_SCORE
        for k, b in enumerate((s[2], s[1], s[0])):
            hud[HUD + 26 + 2 * k], hud[HUD + 27 + 2 * k] = 0x10 | (b >> 4), 0x10 | (b & 0x0F)
        cy += 94 + 83 + 197 + 16                                # the three HUD fields, VB_END
        self.trig_prev = self.trig                              # VB_END
        self.vbi_cycles = cy

    def _sounds(self) -> int:
        """The four envelopes of VBI, as POKEY register writes; returns the cycles used."""
        p = self.pokey
        cy = 0
        if self.snd_shell:                                      # VB_SND_SHELL
            p[1], p[0] = self.snd_shell, 0x0A
            self.snd_shell += 1
            cy += 4 + 2 + 4 + 2 + 4 + 6 + 4 + 2
            if self.snd_shell >= 10:
                self.snd_shell = 0
                p[0] = p[1] = 0
                cy += 2 + 14
            else:
                cy += 3
        else:
            cy += 7
        if not self.snd_splash:                                 # VB_SND_SPLASH
            cy += 7
        elif not self.frame & 1:
            cy += 14
        else:
            p[3] = self.snd_splash | 0x20
            p[2] = (self.snd_splash + 0xDC) & 0xFF
            self.snd_splash -= 1
            if self.snd_splash == 0:
                p[2] = p[3] = 0
                cy += 57
            else:
                cy += 44
        if self.snd_shot:                                       # VB_SND_SHOT
            p[4] = self.snd_shot
            p[5] = (((self.snd_shot - 0x30) & 0xFF) >> 3) | 0xE0
            self.snd_shot -= 1
            if self.snd_shot == 0:
                p[4] = p[5] = 0
                cy += 48
            else:
                cy += 35
        else:
            cy += 7
        if self.frame & 3:                                      # VB_SND_DEATH: every fourth frame
            cy += 8
        elif not self.snd_death:
            cy += 14
        else:
            p[7] = self.snd_death | 0xC0
            p[6] = 0x0A
            self.snd_death -= 1
            if self.snd_death == 0:
                p[6] = p[7] = 0
                cy += 47
            else:
                cy += 34
        return cy

    @staticmethod
    def _cell_addr(x: int, y: int) -> int:
        """CELL_ADDR: player/missile coordinates -> index in `mem` (relative to row -1)."""
        return ROW_M1 + (((y - 0x29) & 0xF8) >> 3) * COLS + (((x - 0x3F) & 0xFF) >> 2)

    def _put_explosion(self, cell: int) -> None:
        m = self.mem
        m[cell], m[cell + 1], m[cell + 0x20], m[cell + 0x21] = 0x24, 0x25, 0x26, 0x27

    def _hit(self, cell: int, k: int) -> int:
        """HIT_HANDLERS[k] with CELL at the object's top-left; returns the handler's cycles."""
        m = self.mem
        obj = k // 4
        if obj == 0:                                            # HIT_SOFT
            self._put_explosion(cell)
            self._add_score(0x15)
            return 97
        if obj == 1:                                            # HIT_FUEL
            self._put_explosion(cell)
            self._add_score(0x20)
            self.fuel_lo, c = bcd_add(self.fuel_lo, FUEL_TILE & 0xFF)
            self.fuel_hi, _ = bcd_add(self.fuel_hi, (FUEL_TILE >> 8) + c)
            if self.fuel_hi >= 0x10:                            # HF_CAP
                self.fuel_hi, self.fuel_lo = 0x09, 0x99
                return 153
            return 140
        if obj == 2:                                            # HIT_AMMO
            self._put_explosion(cell)
            self.score[1], c = bcd_add(self.score[1], 1)
            self.score[2], _ = bcd_add(self.score[2], c)
            return 84
        if obj == 3:                                            # HIT_REPAIR
            self._put_explosion(cell)
            self._add_score(0x30)
            if self.jets < 2:
                self.jets += 1
                return 120
            return 115
        if obj <= 7:                                            # HIT_TANK_R
            self._put_explosion(cell)
            m[cell + 2] = m[cell + 0x22] = 0
            self._add_score(0x55)
            return 115
        if obj <= 11:                                           # HIT_TANK_L
            self._put_explosion(cell)
            m[cell - 1] = m[cell + 0x1F] = 0
            self._add_score(0x55)
            return 133
        d = 0x40 if k & 2 else 0x20                             # HIT_HARD
        m[cell + d + (k & 1)] = 0x1F
        self.snd_splash = 0x0A
        return 37

    # ----------------------------------------------------------------- MAIN_LOOP
    def _main_loop(self) -> Iterator[None]:
        while True:
            start = self.iteration_start = self.frame           # MAIN_LOOP: a VBI has just run
            if self.ch == KEY_ESC:
                self.status = Status.ABORTED
                self._emit(EventKind.ABORTED)
                return
            if self.ch == KEY_SPACE:                            # PAUSE
                self.paused = 0xFF
                self.status = Status.PAUSED
                self._emit(EventKind.PAUSED)
                while True:
                    yield
                    if self.stick != 0x0F:
                        break
                self.paused = 0
                self.ch = 0xFF
                self.status = Status.PLAYING
                self._emit(EventKind.RESUMED)
                start = self.iteration_start = self.frame
            self.scroll_cycles = self._scroll()                 # ML_FRAME
            self.cycles += self.scroll_cycles + 4 + 2 + 4 + 3 + 2 + 2 + 3   # + jet colours, A = RTCLOK + 1, PHA
            yield from self._scan()
            self.iteration += 1
            if self.frame == (start + 1) & 0xFF:                # ML_WAIT_SCAN: the scan ended in the
                yield                                           # next frame -> wait one more
            if self.flash:                                      # ML_FLASH
                self.flash -= 1
            if self.death:                                      # ML_DEATH
                self.death = 0
                if self.flash == 0:
                    if self.jets == 0:                          # GAME_OVER
                        self.jets = 0xFF
                        self.status = Status.GAME_OVER
                        self._emit(EventKind.GAME_OVER)
                        return
                    self.jets -= 1                              # ML_LOSE_JET
                    self.flash = FLASH_FRAMES
                    self.snd_death = 0x0F
                    self._emit(EventKind.JET_LOST)
            yield                                               # MAIN_LOOP: wait for the next VBI


def _default_rnd() -> Callable[[], int]:
    import random
    r = random.Random()
    return lambda: r.randrange(256)
